"""Provider registry — orchestrates anicli-api (MIT) extractors.

Inspired by HakuNeko's connector registry and ani-cli-ru's source selection flow.

Pipeline per title: search -> details -> episodes -> voiceovers (players) -> stream.
Each stage has its own timeout, records provider health, and raises a typed
:mod:`backend.providers.errors` exception. A failing provider never blocks the
others: search fans out concurrently and reports per-provider status.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from backend.config import Settings, get_settings
from backend.providers import players
from backend.providers.cache import CachedSearch, SearchCache, TTLCache
from backend.providers.catalog import DEFAULT_SOURCE, SOURCE_BY_ID, SOURCES, SourceSpec, default_enabled_sources
from backend.providers.errors import (
    CacheExpired,
    NotFound,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
    StreamUnavailable,
)
from backend.providers.health import HealthTracker
from backend.providers.http import DEFAULT_USER_AGENT, SourceClients
from backend.providers.ids import decode_external_id, encode_external_id
from backend.schemas import (
    AnimeDetail,
    EpisodeInfo,
    ProviderSearchStatus,
    SearchResponse,
    SearchResult,
    VoiceoverOption,
)

logger = logging.getLogger("animebox.providers")

DETAIL_TTL = 15 * 60
SOURCES_TTL = 10 * 60
MAX_AUTO_VOICEOVER_GROUPS = 4


@dataclass
class ResolvedVideo:
    type: str
    quality: int
    url: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class ResolvedStream:
    anime_title: str
    episode: int
    voiceover: str
    player: str
    video: ResolvedVideo
    qualities: list[int]
    browser_playable: bool
    source: str


@dataclass
class VoiceoverGroup:
    title: str
    players: list[players.PlayerSource]


def _stable_key(item: Any) -> str:
    """Key scheme kept identical to 1.x so existing ids keep resolving."""
    url = getattr(item, "url", "") or ""
    data = getattr(item, "data", None)
    if url and url != "_":
        return url
    if isinstance(data, dict):
        for key in ("id", "slug_url", "slug", "anime_id"):
            if data.get(key) is not None:
                return f"id:{data[key]}"
    return f"title:{getattr(item, 'title', 'unknown')}"


def _payload(item: Any) -> dict[str, Any]:
    data = getattr(item, "data", None)
    if isinstance(data, dict):
        return data
    raw = getattr(item, "raw_json", None)
    return {"raw_json": raw} if isinstance(raw, dict) else {}


def _year(anime: Any) -> int | None:
    def from_value(value: Any) -> int | None:
        if isinstance(value, int) and 1900 < value < 2100:
            return value
        if isinstance(value, str):
            match = re.search(r"(19|20)\d{2}", value)
            return int(match.group(0)) if match else None
        if isinstance(value, dict) and "year" in value:
            return from_value(value["year"])
        return None

    for container, keys in (
        (getattr(anime, "raw_json", None), ("datePublished", "year", "aired_on")),
        (getattr(anime, "data", None), ("year", "season", "aired_on", "releaseDate")),
    ):
        if isinstance(container, dict):
            for key in keys:
                found = from_value(container.get(key))
                if found:
                    return found
    return None


def _ordinal(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _short_error(exc: BaseException) -> str:
    text = str(exc).strip() or type(exc).__name__
    return text.splitlines()[0][:300]


class AnicliProvider:
    """Adapter for one anicli-api source module, with its own HTTP session."""

    def __init__(self, spec: SourceSpec, proxy: str | None) -> None:
        self.spec = spec
        self.clients = SourceClients(proxy)
        self._module: Any = None

    @property
    def module(self) -> Any:
        if self._module is None:
            try:
                self._module = importlib.import_module(f"anicli_api.source.{self.spec.module}")
            except Exception as exc:  # noqa: BLE001 - surface as provider failure
                raise ProviderUnavailable(f"{self.spec.label} failed to load: {exc}", source=self.spec.id) from exc
        return self._module

    def extractor(self) -> Any:
        return self.module.Extractor(http_client=self.clients.sync, http_async_client=self.clients.async_)

    def build_search(self, entry: CachedSearch) -> Any:
        search_cls = self.module.Search
        kwargs: dict[str, Any] = {
            "title": entry.title,
            "thumbnail": entry.thumbnail,
            "url": entry.url,
            "http": self.clients.sync,
            "http_async": self.clients.async_,
        }
        fields = {a.name for a in getattr(search_cls, "__attrs_attrs__", ())}
        if "data" in fields:
            if not entry.payload:
                raise CacheExpired("Search data expired; search again", source=self.spec.id, stage="details")
            kwargs["data"] = entry.payload
        return search_cls(**kwargs)

    async def aclose(self) -> None:
        await self.clients.aclose()


class ProviderRegistry:
    def __init__(self, settings: Settings | None = None, *, health: HealthTracker | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache = SearchCache(self.settings.data_path / "search_cache")
        self.health = health or HealthTracker(self.settings.data_path / "provider_health.json")
        self.enabled_sources: list[str] = default_enabled_sources()
        self.default_source: str = DEFAULT_SOURCE
        self._providers: dict[str, AnicliProvider] = {}
        self._anime_cache: TTLCache[Any] = TTLCache(DETAIL_TTL)
        self._episodes_cache: TTLCache[list[Any]] = TTLCache(DETAIL_TTL)
        self._sources_cache: TTLCache[list[players.PlayerSource]] = TTLCache(SOURCES_TTL, max_items=512)
        self._title_hints: dict[str, str] = {}

    # ------------------------------------------------------------------ setup
    @property
    def proxy(self) -> str | None:
        return self.settings.http_proxy or None

    def provider(self, source: str) -> AnicliProvider:
        spec = SOURCE_BY_ID.get(source)
        if spec is None:
            raise ProviderUnavailable(f"Unknown source '{source}'", source=source)
        provider = self._providers.get(source)
        if provider is None:
            provider = AnicliProvider(spec, self.proxy)
            self._providers[source] = provider
        return provider

    async def apply_network_settings(self) -> None:
        """Recreate sessions after the proxy changed (cached objects hold old clients)."""
        old, self._providers = self._providers, {}
        self._anime_cache.clear()
        self._episodes_cache.clear()
        self._sources_cache.clear()
        for provider in old.values():
            await provider.aclose()

    def configure(self, *, enabled_sources: list[str] | None = None, default_source: str | None = None) -> None:
        if enabled_sources is not None:
            self.enabled_sources = [s for s in enabled_sources if s in SOURCE_BY_ID] or [DEFAULT_SOURCE]
        if default_source and default_source in SOURCE_BY_ID:
            self.default_source = default_source

    def ordered_sources(self) -> list[SourceSpec]:
        enabled = set(self.enabled_sources)
        return sorted(SOURCES, key=lambda s: (s.id != self.default_source, s.id not in enabled, not s.stable))

    def remember_title(self, external_id: str, title: str | None) -> None:
        if title:
            self._title_hints[external_id] = title

    async def aclose(self) -> None:
        for provider in self._providers.values():
            await provider.aclose()
        self._providers = {}

    # ----------------------------------------------------------------- stages
    async def _stage(self, source: str, stage: str, coro, timeout: float):
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
        except TimeoutError as exc:
            self.health.record(source, stage, False, int(timeout * 1000), f"timed out after {timeout:.0f}s")
            raise ProviderTimeout(f"{stage} timed out after {timeout:.0f}s", source=source, stage=stage) from exc
        except NotFound as exc:
            # A title/episode that does not exist is not a provider fault.
            exc.source, exc.stage = exc.source or source, exc.stage or stage
            raise
        except ProviderError as exc:
            self.health.record(source, stage, False, int((time.monotonic() - started) * 1000), exc.message)
            exc.source, exc.stage = exc.source or source, exc.stage or stage
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - extractor internals vary wildly
            self.health.record(source, stage, False, int((time.monotonic() - started) * 1000), _short_error(exc))
            logger.warning("%s %s failed: %s", source, stage, _short_error(exc))
            raise ProviderError(f"{stage} failed: {_short_error(exc)}", source=source, stage=stage) from exc
        self.health.record(source, stage, True, int((time.monotonic() - started) * 1000))
        return result

    # ----------------------------------------------------------------- search
    async def search(self, query: str, sources: list[str] | None = None) -> SearchResponse:
        query = query.strip()
        sources = [s for s in (sources or self.enabled_sources) if s in SOURCE_BY_ID]
        if not sources:
            raise ProviderUnavailable("No enabled sources")
        statuses: list[ProviderSearchStatus] = []

        async def run(source: str) -> list[SearchResult]:
            started = time.monotonic()
            label = SOURCE_BY_ID[source].label
            try:
                found = await self._search_one(source, query)
            except ProviderError as exc:
                statuses.append(
                    ProviderSearchStatus(
                        source=source,
                        label=label,
                        ok=False,
                        latency_ms=int((time.monotonic() - started) * 1000),
                        error=exc.message,
                        timed_out=isinstance(exc, ProviderTimeout),
                    )
                )
                return []
            statuses.append(
                ProviderSearchStatus(
                    source=source,
                    label=label,
                    ok=True,
                    count=len(found),
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
            )
            return found

        batches = await asyncio.gather(*(run(source) for source in sources))
        results: list[SearchResult] = []
        seen: set[str] = set()
        for batch in batches:
            for item in batch:
                if item.id in seen:
                    continue
                seen.add(item.id)
                results.append(item)
        order = {source: i for i, source in enumerate(sources)}
        statuses.sort(key=lambda s: order.get(s.source, 99))
        return SearchResponse(query=query, results=results, providers=statuses)

    async def _search_one(self, source: str, query: str) -> list[SearchResult]:
        provider = self.provider(source)

        async def call() -> list[Any]:
            return list(await provider.extractor().a_search(query))

        found = await self._stage(source, "search", call(), self.settings.provider_search_timeout)
        out: list[SearchResult] = []
        for item in found:
            title = (getattr(item, "title", "") or "").strip()
            if not title:
                continue
            external_id = encode_external_id(source, _stable_key(item))
            self.cache.put(
                external_id,
                CachedSearch(
                    source=source,
                    url=getattr(item, "url", "") or "",
                    title=title,
                    thumbnail=getattr(item, "thumbnail", "") or "",
                    payload=_payload(item),
                    saved_at=time.time(),
                ),
            )
            self.remember_title(external_id, title)
            out.append(
                SearchResult(
                    id=external_id,
                    title=title,
                    poster=getattr(item, "thumbnail", None) or None,
                    source=source,
                    source_label=provider.spec.label,
                )
            )
        return out

    # ------------------------------------------------------------ resolution
    async def _research(self, external_id: str, title: str) -> Any:
        """Search again by title and accept only the exact same provider key (never a lookalike)."""
        source, key = decode_external_id(external_id)
        provider = self.provider(source)
        hits = await asyncio.wait_for(provider.extractor().a_search(title), self.settings.provider_search_timeout)
        for hit in hits:
            if _stable_key(hit) == key:
                self.cache.put(
                    external_id,
                    CachedSearch(source, getattr(hit, "url", "") or "", hit.title, hit.thumbnail or "", _payload(hit), time.time()),
                )
                return hit
        raise CacheExpired("Title not found by provider any more; search again", source=source, stage="details")

    async def _search_object(self, external_id: str) -> Any:
        source, key = decode_external_id(external_id)
        provider = self.provider(source)
        entry = self.cache.get(external_id)
        if entry is None and (key.startswith("/") or key.startswith("http")):
            # URL keys (AnimeGO, Yummy) can be rebuilt without cached data.
            slug = key.rstrip("/").split("/")[-1]
            entry = CachedSearch(source, key, self._title_hints.get(external_id) or slug.replace("-", " "), "", {}, time.time())
        if entry is not None:
            try:
                return provider.build_search(entry)
            except CacheExpired:
                pass
            except ProviderUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.info("Rebuilding search object for %s failed: %s", external_id, exc)
        title = (entry.title if entry else None) or self._title_hints.get(external_id)
        if not title:
            raise CacheExpired("Search data expired; search for the title again", source=source, stage="details")
        return await self._research(external_id, title)

    async def _anime(self, external_id: str) -> Any:
        cached = self._anime_cache.get(external_id)
        if cached is not None:
            return cached
        source, _ = decode_external_id(external_id)

        async def load() -> Any:
            search_obj = await self._search_object(external_id)
            try:
                return await search_obj.a_get_anime()
            except Exception as first:  # noqa: BLE001 - stale payload -> one exact re-search
                title = self._title_hints.get(external_id) or getattr(search_obj, "title", None)
                if not title:
                    raise first
                hit = await self._research(external_id, title)
                return await hit.a_get_anime()

        anime = await self._stage(source, "details", load(), self.settings.provider_detail_timeout)
        self._anime_cache.set(external_id, anime)
        return anime

    async def _episodes(self, external_id: str) -> list[Any]:
        cached = self._episodes_cache.get(external_id)
        if cached is not None:
            return cached
        source, _ = decode_external_id(external_id)
        anime = await self._anime(external_id)

        async def load() -> list[Any]:
            return list(await anime.a_get_episodes())

        episodes = await self._stage(source, "episodes", load(), self.settings.provider_detail_timeout)
        self._episodes_cache.set(external_id, episodes)
        return episodes

    async def get_anime(self, external_id: str) -> AnimeDetail:
        source, _ = decode_external_id(external_id)
        spec = self.provider(source).spec
        anime = await self._anime(external_id)
        episodes_raw = await self._episodes(external_id)
        episodes: list[EpisodeInfo] = []
        seen: set[int] = set()
        for ep in episodes_raw:
            ordinal = _ordinal(getattr(ep, "ordinal", None))
            if ordinal is None or ordinal in seen:
                continue
            seen.add(ordinal)
            episodes.append(EpisodeInfo(title=(getattr(ep, "title", "") or f"Episode {ordinal}").strip(), ordinal=ordinal))
        episodes.sort(key=lambda e: e.ordinal)
        title = (getattr(anime, "title", "") or self._title_hints.get(external_id) or "Untitled").strip()
        self.remember_title(external_id, title)
        return AnimeDetail(
            id=external_id,
            title=title,
            poster=getattr(anime, "thumbnail", None) or None,
            description=(getattr(anime, "description", "") or "").strip() or None,
            year=_year(anime),
            source=source,
            source_label=spec.label,
            seasons=[1],
            episodes=episodes,
        )

    async def _episode(self, external_id: str, episode: int) -> Any:
        for ep in await self._episodes(external_id):
            if _ordinal(getattr(ep, "ordinal", None)) == episode:
                return ep
        source, _ = decode_external_id(external_id)
        raise NotFound(f"Episode {episode} not found", source=source, stage="episodes")

    async def _player_sources(self, external_id: str, episode: int, refresh: bool = False) -> list[players.PlayerSource]:
        key = (external_id, episode)
        if not refresh:
            cached = self._sources_cache.get(key)
            if cached is not None:
                return cached
        source, _ = decode_external_id(external_id)
        ep = await self._episode(external_id, episode)

        async def load() -> list[Any]:
            return list(await ep.a_get_sources())

        raw = await self._stage(source, "voiceovers", load(), self.settings.provider_detail_timeout)
        result = [
            players.PlayerSource(
                voiceover=players.normalize_voiceover(getattr(src, "title", "")),
                url=getattr(src, "url", "") or "",
                label=players.player_label(getattr(src, "url", "") or ""),
                raw=src,
            )
            for src in raw
        ]
        self._sources_cache.set(key, result)
        return result

    @staticmethod
    def group_voiceovers(sources: list[players.PlayerSource]) -> "OrderedDict[str, VoiceoverGroup]":
        groups: OrderedDict[str, VoiceoverGroup] = OrderedDict()
        for src in sources:
            key = players.voiceover_key(src.voiceover)
            group = groups.setdefault(key, VoiceoverGroup(title=src.voiceover, players=[]))
            group.players.append(src)
        return groups

    async def get_episode_voiceovers(self, external_id: str, episode: int) -> list[VoiceoverOption]:
        groups = self.group_voiceovers(await self._player_sources(external_id, episode))
        return [
            VoiceoverOption(
                title=group.title,
                kind=players.voiceover_kind(group.title),  # type: ignore[arg-type]
                players=list(dict.fromkeys(p.label for p in group.players)),
                index=i,
            )
            for i, group in enumerate(groups.values())
        ]

    def _ordered_groups(self, groups: "OrderedDict[str, VoiceoverGroup]", preferred: str | None) -> list[VoiceoverGroup]:
        all_groups = list(groups.values())
        if preferred:
            wanted = players.voiceover_key(preferred)
            exact = [g for k, g in groups.items() if k == wanted]
            if exact:
                return exact
            partial = [g for k, g in groups.items() if wanted and (wanted in k or k in wanted)]
            if partial:
                return partial[:1]
            return []
        ranked: list[VoiceoverGroup] = []
        for pref in self.settings.preferred_voiceover_list:
            pref_key = players.voiceover_key(pref)
            for key, group in groups.items():
                if pref_key and pref_key in key and group not in ranked:
                    ranked.append(group)
        ranked.extend(g for g in all_groups if g not in ranked)
        return ranked

    async def resolve_stream(
        self,
        external_id: str,
        episode: int,
        voiceover: str | None = None,
        quality: int | None = None,
        *,
        player: str | None = None,
        purpose: str = "play",
        refresh: bool = False,
    ) -> ResolvedStream:
        source, _ = decode_external_id(external_id)
        allowed = players.BROWSER_TYPES if purpose == "play" else players.DOWNLOAD_TYPES
        wanted_quality = quality or self.settings.default_quality
        anime = await self._anime(external_id)
        attempts: list[dict] = []

        for attempt in range(2):  # second pass refreshes stale player lists once
            sources = await self._player_sources(external_id, episode, refresh=refresh or attempt > 0)
            groups = self._ordered_groups(self.group_voiceovers(sources), voiceover)
            if not groups:
                raise NotFound(f"Voiceover '{voiceover}' is not available for episode {episode}", source=source, stage="voiceovers")
            for group in groups[:MAX_AUTO_VOICEOVER_GROUPS]:
                ranked = sorted(
                    group.players,
                    key=lambda p: (p.label != player if player else False, players.player_health.rank(p.label)),
                )
                for candidate in ranked:
                    started = time.monotonic()
                    try:
                        videos = await asyncio.wait_for(
                            players.extract_videos(candidate.raw, self.proxy), self.settings.provider_stream_timeout
                        )
                        chosen = players.pick_video(videos, wanted_quality, allowed)
                        if chosen is None:
                            kinds = sorted({getattr(v, "type", "?") for v in videos})
                            raise LookupError(
                                f"no {'browser-playable ' if purpose == 'play' else ''}streams (got {', '.join(kinds) or 'none'})"
                            )
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001 - try the next player
                        players.player_health.failure(candidate.label)
                        message = "timed out" if isinstance(exc, TimeoutError) else _short_error(exc)
                        attempts.append({"voiceover": group.title, "player": candidate.label, "error": message})
                        logger.info("%s ep%s %s/%s failed: %s", source, episode, group.title, candidate.label, message)
                        continue
                    players.player_health.success(candidate.label)
                    self.health.record(source, "stream", True, int((time.monotonic() - started) * 1000))
                    headers = {str(k): str(v) for k, v in (getattr(chosen, "headers", None) or {}).items()}
                    if not any(k.lower() == "user-agent" for k in headers):
                        headers["User-Agent"] = DEFAULT_USER_AGENT
                    return ResolvedStream(
                        anime_title=getattr(anime, "title", "") or "",
                        episode=episode,
                        voiceover=group.title,
                        player=candidate.label,
                        video=ResolvedVideo(type=chosen.type, quality=int(chosen.quality), url=chosen.url, headers=headers),
                        qualities=players.available_qualities(videos, allowed),
                        browser_playable=chosen.type in players.BROWSER_TYPES,
                        source=source,
                    )
            if refresh:
                break

        summary = "; ".join(f"{a['voiceover']}/{a['player']}: {a['error']}" for a in attempts[-6:])
        self.health.record(source, "stream", False, None, summary or "no players")
        raise StreamUnavailable(
            f"No working stream for episode {episode}" + (f" ({summary})" if summary else ""),
            source=source,
            stage="stream",
            attempts=attempts,
        )

    def pick_voiceover_title(self, options: list[VoiceoverOption], preferred: str | None = None) -> str | None:
        if not options:
            return None
        groups = OrderedDict((players.voiceover_key(o.title), VoiceoverGroup(o.title, [])) for o in options)
        ordered = self._ordered_groups(groups, preferred)
        return ordered[0].title if ordered else None

    # ------------------------------------------------------------ diagnostics
    async def check(self, source: str) -> None:
        """Run the full pipeline against a known title. Results land in ``self.health``."""
        spec = SOURCE_BY_ID.get(source)
        if spec is None:
            raise ProviderUnavailable(f"Unknown source '{source}'", source=source)
        from backend.providers.errors import STAGES

        for stage in STAGES:  # stale results must not survive a new check
            self.health.get(source).stages.pop(stage, None)
        try:
            found = await self._search_one(source, spec.check_query)
            if not found:
                # Search works but the reference title is missing from this catalog: inconclusive, not a failure.
                latency = self.health.get(source).stages.get("search")
                self.health.record(
                    source,
                    "search",
                    True,
                    latency.latency_ms if latency else None,
                    f"проверочный тайтл «{spec.check_query}» не найден — остальные этапы не проверены",
                )
                return
            external_id = found[0].id
            self._anime_cache.pop(external_id)
            self._episodes_cache.pop(external_id)
            detail = await self.get_anime(external_id)
            if not detail.episodes:
                self.health.record(source, "voiceovers", False, None, "title has no episodes")
                return
            first = detail.episodes[0].ordinal
            await self._player_sources(external_id, first, refresh=True)
            stream = await self.resolve_stream(external_id, first, refresh=True)
            await self._probe_media(source, stream)
        except ProviderError:
            pass  # already recorded per stage
        finally:
            self.health.mark_checked(source)

    async def _probe_media(self, source: str, stream: ResolvedStream) -> None:
        """Fetch the first bytes of the resolved stream through the shared media client."""
        from backend.providers.http import media_clients

        client = media_clients.get(self.proxy)
        started = time.monotonic()
        try:
            response = await client.get(
                stream.video.url,
                headers={**stream.video.headers, "Range": "bytes=0-2047"},
                follow_redirects=True,
                timeout=15,
            )
            if response.status_code >= 400:
                raise ProviderError(f"media host answered HTTP {response.status_code} ({urlsplit(stream.video.url).netloc})")
        except ProviderError as exc:
            self.health.record(source, "stream", False, int((time.monotonic() - started) * 1000), exc.message)
        except Exception as exc:  # noqa: BLE001
            self.health.record(source, "stream", False, int((time.monotonic() - started) * 1000), _short_error(exc))


_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
