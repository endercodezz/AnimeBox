"""Provider layer — thin adapters over anicli-api (MIT).

Inspired by Hakuneko connector registry and ani-cli-ru extractor loading.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from anicli_api._http import HTTPAsync, HTTPSync
from anicli_api.tools.helpers import get_video_by_quality

from backend.config import ROOT_DIR, Settings, get_settings
from backend.schemas import AnimeDetail, EpisodeInfo, SearchResult, VideoStream, VoiceoverOption

logger = logging.getLogger("animebox.providers")

DEFAULT_SOURCES = ("animego", "anilibria", "animevost", "yummy_anime")
CACHE_TTL = 12 * 3600
CACHE_DIR = ROOT_DIR / "data" / "search_cache"


@dataclass
class ResolvedStream:
    anime_title: str
    episode: int
    voiceover: str
    video: VideoStream
    source_url: str


@dataclass
class CachedSearch:
    source: str
    url: str
    title: str
    thumbnail: str
    payload: dict[str, Any]
    saved_at: float


def encode_external_id(source: str, key: str) -> str:
    return f"{source}:{quote(key, safe='')}"


def decode_external_id(external_id: str) -> tuple[str, str]:
    source, _, rest = external_id.partition(":")
    if not source or not rest:
        raise ValueError(f"Invalid anime id: {external_id}")
    return source, unquote(rest)


def _stable_key(source: str, item: Any) -> str:
    url = getattr(item, "url", "") or ""
    data = getattr(item, "data", None)
    if url and url != "_":
        return url
    if isinstance(data, dict):
        for k in ("id", "slug_url", "slug", "anime_id"):
            if data.get(k) is not None:
                return f"id:{data[k]}"
    return f"title:{getattr(item, 'title', 'unknown')}"


def _payload_from_item(item: Any) -> dict[str, Any]:
    data = getattr(item, "data", None)
    if isinstance(data, dict):
        return data
    raw = getattr(item, "raw_json", None)
    if isinstance(raw, dict):
        return {"raw_json": raw}
    return {}


@lru_cache(maxsize=1)
def list_source_modules() -> list[str]:
    import anicli_api.source as pkg

    path = Path(pkg.__path__[0])
    return sorted(p.stem for p in path.glob("*.py") if not p.name.startswith("_"))


def _http_clients(settings: Settings):
    kwargs: dict[str, Any] = {}
    if settings.http_proxy:
        kwargs["proxy"] = settings.http_proxy
    return HTTPSync(**kwargs) if kwargs else HTTPSync(), HTTPAsync(**kwargs) if kwargs else HTTPAsync()


def load_extractor(source_name: str, settings: Settings | None = None):
    settings = settings or get_settings()
    module_name = source_name.replace("-", "_")
    module = importlib.import_module(f"anicli_api.source.{module_name}")
    sync_http, async_http = _http_clients(settings)
    return module.Extractor(http_client=sync_http, http_async_client=async_http), module


def _guess_year(anime: Any) -> int | None:
    raw = getattr(anime, "raw_json", None) or {}
    if isinstance(raw, dict):
        for key in ("datePublished", "year", "aired_on"):
            val = raw.get(key)
            if isinstance(val, str):
                m = re.search(r"(19|20)\d{2}", val)
                if m:
                    return int(m.group(0))
            if isinstance(val, int) and 1900 < val < 2100:
                return val
    data = getattr(anime, "data", None)
    if isinstance(data, dict):
        for key in ("year", "season", "aired_on", "releaseDate"):
            val = data.get(key)
            if isinstance(val, int) and 1900 < val < 2100:
                return val
            if isinstance(val, str):
                m = re.search(r"(19|20)\d{2}", val)
                if m:
                    return int(m.group(0))
            if isinstance(val, dict) and "year" in val:
                try:
                    return int(val["year"])
                except (TypeError, ValueError):
                    pass
    return None


def _player_host(url: str) -> str | None:
    try:
        return urlparse(url).netloc or None
    except Exception:
        return None


def _pick_video(videos: list[Any], quality: int) -> Any:
    """Pick closest quality, preferring HLS over DASH for browser compatibility."""
    closest = get_video_by_quality(videos, quality)
    same_quality = [video for video in videos if int(video.quality) == int(closest.quality)]
    format_priority = {"m3u8": 0, "mp4": 1, "webm": 2, "mpd": 3}
    return min(same_quality, key=lambda video: format_priority.get(video.type, 99))


class SearchCache:
    def __init__(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._mem: dict[str, CachedSearch] = {}

    def _path(self, external_id: str) -> Path:
        safe = re.sub(r"[^\w.-]+", "_", external_id)[:180]
        return CACHE_DIR / f"{safe}.json"

    def put(self, external_id: str, entry: CachedSearch) -> None:
        self._mem[external_id] = entry
        try:
            self._path(external_id).write_text(
                json.dumps(
                    {
                        "source": entry.source,
                        "url": entry.url,
                        "title": entry.title,
                        "thumbnail": entry.thumbnail,
                        "payload": entry.payload,
                        "saved_at": entry.saved_at,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("Failed to persist search cache: %s", exc)

    def get(self, external_id: str) -> CachedSearch | None:
        now = time.time()
        entry = self._mem.get(external_id)
        if entry and now - entry.saved_at <= CACHE_TTL:
            return entry
        path = self._path(external_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            entry = CachedSearch(
                source=raw["source"],
                url=raw["url"],
                title=raw["title"],
                thumbnail=raw.get("thumbnail") or "",
                payload=raw.get("payload") or {},
                saved_at=float(raw.get("saved_at") or 0),
            )
            if now - entry.saved_at > CACHE_TTL:
                return None
            self._mem[external_id] = entry
            return entry
        except Exception:
            return None


class ProviderRegistry:
    """Hakuneko-inspired registry wrapping anicli-api extractors."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache = SearchCache()

    def available_sources(self) -> list[str]:
        modules = set(list_source_modules())
        ordered = [s for s in DEFAULT_SOURCES if s in modules]
        ordered.extend(sorted(modules - set(ordered)))
        return ordered

    async def search(self, query: str, sources: list[str] | None = None) -> list[SearchResult]:
        sources = sources or list(DEFAULT_SOURCES)
        batches = await asyncio.gather(
            *[self._search_one(source, query) for source in sources],
            return_exceptions=True,
        )
        results: list[SearchResult] = []
        seen: set[str] = set()
        for batch in batches:
            if isinstance(batch, Exception):
                logger.warning("Search failed: %s", batch)
                continue
            for item in batch:
                key = f"{item.source}:{item.title.lower()}"
                if key in seen:
                    continue
                seen.add(key)
                results.append(item)
        return results

    async def _search_one(self, source: str, query: str) -> list[SearchResult]:
        extractor, _module = load_extractor(source, self.settings)
        found = await extractor.a_search(query)
        out: list[SearchResult] = []
        for item in found:
            key = _stable_key(source, item)
            external_id = encode_external_id(source, key)
            self.cache.put(
                external_id,
                CachedSearch(
                    source=source,
                    url=item.url,
                    title=item.title,
                    thumbnail=item.thumbnail or "",
                    payload=_payload_from_item(item),
                    saved_at=time.time(),
                ),
            )
            out.append(
                SearchResult(
                    id=external_id,
                    title=item.title,
                    poster=item.thumbnail or None,
                    description=None,
                    year=None,
                    source=source,
                )
            )
        return out

    def _build_search_obj(self, entry: CachedSearch) -> Any:
        extractor, module = load_extractor(entry.source, self.settings)
        kwargs = {"http": extractor.http, "http_async": extractor.http_async}
        search_cls = module.Search
        fields = getattr(search_cls, "__attrs_attrs__", None)
        init_kwargs: dict[str, Any] = {
            "title": entry.title,
            "thumbnail": entry.thumbnail,
            "url": entry.url,
            **kwargs,
        }
        if fields:
            names = {a.name for a in fields}
            if "data" in names and entry.payload:
                init_kwargs["data"] = entry.payload
        return search_cls(**init_kwargs)

    async def _resolve_search(self, external_id: str) -> Any:
        entry = self.cache.get(external_id)
        if entry is None:
            source, key = decode_external_id(external_id)
            # Best-effort rebuild for URL-based sources (AnimeGo etc.)
            if key.startswith("title:"):
                raise LookupError("Search cache expired; search again")
            url = key if not key.startswith("id:") else "_"
            entry = CachedSearch(
                source=source,
                url=url,
                title=key.split("/")[-1].replace("-", " "),
                thumbnail="",
                payload={"id": int(key.split(":", 1)[1])} if key.startswith("id:") and key.split(":")[1].isdigit() else {},
                saved_at=time.time(),
            )
            if entry.url == "_" and not entry.payload:
                raise LookupError("Search cache expired; search again")
        try:
            return self._build_search_obj(entry)
        except Exception as exc:
            logger.warning("Rebuild search failed (%s), trying re-search: %s", external_id, exc)
            extractor, _ = load_extractor(entry.source, self.settings)
            hits = await extractor.a_search(entry.title)
            for hit in hits:
                if _stable_key(entry.source, hit) == decode_external_id(external_id)[1] or hit.url == entry.url:
                    return hit
            if hits:
                return hits[0]
            raise LookupError(f"Anime not found for id={external_id}") from exc

    async def get_anime(self, external_id: str, include_voiceovers: bool = False) -> AnimeDetail:
        search_obj = await self._resolve_search(external_id)
        anime = await search_obj.a_get_anime()
        episodes_raw = await anime.a_get_episodes()
        episodes: list[EpisodeInfo] = []
        for ep in episodes_raw:
            voiceovers: list[VoiceoverOption] = []
            if include_voiceovers:
                try:
                    sources_list = await ep.a_get_sources()
                    voiceovers = [
                        VoiceoverOption(
                            title=src.title,
                            url=src.url,
                            player_host=_player_host(src.url),
                            index=i,
                        )
                        for i, src in enumerate(sources_list)
                    ]
                except Exception as exc:
                    logger.warning("Failed to load sources for ep %s: %s", ep.ordinal, exc)
            episodes.append(
                EpisodeInfo(
                    title=ep.title,
                    ordinal=int(ep.ordinal),
                    season=1,
                    voiceovers=voiceovers,
                )
            )

        source, _ = decode_external_id(external_id)
        return AnimeDetail(
            id=external_id,
            title=anime.title,
            poster=anime.thumbnail or None,
            description=anime.description or None,
            year=_guess_year(anime),
            source=source,
            seasons=[1],
            episodes=episodes,
        )

    async def get_episode_voiceovers(self, external_id: str, episode: int) -> list[VoiceoverOption]:
        search_obj = await self._resolve_search(external_id)
        anime = await search_obj.a_get_anime()
        episodes = await anime.a_get_episodes()
        ep = next((e for e in episodes if int(e.ordinal) == episode), None)
        if ep is None:
            raise LookupError(f"Episode {episode} not found")
        sources_list = await ep.a_get_sources()
        return [
            VoiceoverOption(
                title=src.title,
                url=src.url,
                player_host=_player_host(src.url),
                index=i,
            )
            for i, src in enumerate(sources_list)
        ]

    def pick_voiceover(
        self,
        options: list[VoiceoverOption],
        preferred: str | None = None,
        preferred_list: list[str] | None = None,
    ) -> VoiceoverOption:
        if not options:
            raise LookupError("No voiceovers available")
        if preferred:
            for opt in options:
                if preferred.lower() in opt.title.lower():
                    return opt
        prefs = preferred_list or self.settings.preferred_voiceover_list
        for pref in prefs:
            for opt in options:
                if pref.lower() in opt.title.lower():
                    return opt
        return options[0]

    async def resolve_stream(
        self,
        external_id: str,
        episode: int,
        voiceover: str | None = None,
        quality: int | None = None,
    ) -> ResolvedStream:
        search_obj = await self._resolve_search(external_id)
        anime_obj = await search_obj.a_get_anime()
        episodes = await anime_obj.a_get_episodes()
        ep = next((e for e in episodes if int(e.ordinal) == episode), None)
        if ep is None:
            raise LookupError(f"Episode {episode} not found")
        sources_list = await ep.a_get_sources()
        options = [
            VoiceoverOption(title=s.title, url=s.url, player_host=_player_host(s.url), index=i)
            for i, s in enumerate(sources_list)
        ]
        chosen = self.pick_voiceover(options, preferred=voiceover)
        src_obj = sources_list[chosen.index]
        videos = await src_obj.a_get_videos()
        if not videos:
            raise LookupError("No video streams found")
        q = quality or self.settings.default_quality
        best = _pick_video(videos, q)
        return ResolvedStream(
            anime_title=anime_obj.title,
            episode=episode,
            voiceover=chosen.title,
            source_url=chosen.url,
            video=VideoStream(
                type=best.type,
                quality=int(best.quality),
                url=best.url,
                headers=dict(best.headers or {}),
            ),
        )


_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
