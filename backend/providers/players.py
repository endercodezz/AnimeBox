"""Player (video host) handling: extraction dispatch, ranking and video selection.

Extraction reuses anicli-api (MIT, https://github.com/vypivshiy/anicli-api)
decoders. AnimeBox adds:

- per-call HTTP clients so player-specific headers (e.g. Aniboom ``Referer``)
  never leak into other players or providers;
- an adapter for AnimeGO's current ``/cdn-iframe/<id>/<season>/<episode>?dubbing=``
  URLs, which anicli-api's ``CdnVideoHub`` decoder no longer matches;
- awaited variants of Yummy Anime's CVH iframe flow (upstream forgets an ``await``);
- ranking that prefers players that recently worked.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

from anicli_api.base import BaseSource
from anicli_api.player import ALL_DECODERS
from anicli_api.player.cdnvideohub import a_video_playlist_from_vk_id
from anicli_api.player.parsers.cdnvideohub_parser import CdnVideoHubAPI, PageParseCdnVideoData

from backend.providers.http import EXTRACTION_HEADERS, make_async_client, make_sync_client

logger = logging.getLogger("animebox.players")

BROWSER_TYPES = ("m3u8", "mp4", "webm")
DOWNLOAD_TYPES = ("m3u8", "mp4", "webm", "mpd")

_ANIMEGO_CDN_IFRAME = re.compile(r"^https?://(?:www\.)?animego\.\w+/cdn-iframe/(\d+)/(\d+)/(\d+)/?(?:\?.*)?$")
_YUMMY_CVH_IFRAME = re.compile(r"/iframeCVH\.html\?")

# Lower is better. Unknown players sit in the middle.
_BASE_RANK = {"kodik": 0, "aniboom": 1, "cvh": 2, "aksor": 3, "csst": 3, "libria": 0, "animevost": 0, "sibnet": 8}


def player_label(url: str) -> str:
    host = (urlsplit(url).netloc or "").lower()
    if _ANIMEGO_CDN_IFRAME.match(url) or _YUMMY_CVH_IFRAME.search(url) or "cdnvideohub" in host:
        return "cvh"
    for key in ("kodik", "aniboom", "sibnet", "aksor", "csst", "libria", "animevost", "animetop", "sovetromantica"):
        if key in host:
            return "animevost" if key == "animetop" else key
    return host.removeprefix("www.") or "direct"


@dataclass
class _HostHealth:
    failures: int = 0
    last_failure: float = 0.0
    last_success: float = 0.0


class PlayerHealth:
    """In-memory record of which players recently worked. Failures decay after 30 minutes."""

    DECAY = 30 * 60

    def __init__(self) -> None:
        self._hosts: dict[str, _HostHealth] = {}

    def success(self, label: str) -> None:
        entry = self._hosts.setdefault(label, _HostHealth())
        entry.failures = 0
        entry.last_success = time.monotonic()

    def failure(self, label: str) -> None:
        entry = self._hosts.setdefault(label, _HostHealth())
        entry.failures += 1
        entry.last_failure = time.monotonic()

    def penalty(self, label: str) -> int:
        entry = self._hosts.get(label)
        if not entry or not entry.failures:
            return 0
        if time.monotonic() - entry.last_failure > self.DECAY:
            return 0
        return 10 * min(entry.failures, 5)

    def rank(self, label: str) -> int:
        return _BASE_RANK.get(label, 5) + self.penalty(label)


player_health = PlayerHealth()


@dataclass
class PlayerSource:
    """One voiceover offered by one player."""

    voiceover: str
    url: str
    label: str
    raw: Any = field(repr=False, default=None)


def normalize_voiceover(title: str) -> str:
    title = re.sub(r"^\s*озвучка\s+", "", title or "", flags=re.IGNORECASE).strip()
    return title or "Unknown"


def voiceover_kind(title: str) -> str:
    lowered = title.casefold()
    if "субтитр" in lowered or "subtitle" in lowered or lowered in {"sub", "subs", "софтсаб"}:
        return "subtitles"
    if "оригинал" in lowered or "original" in lowered:
        return "original"
    return "dub"


def voiceover_key(title: str) -> str:
    return re.sub(r"[\s\-_.]+", "", normalize_voiceover(title).casefold())


async def _animego_cdn_iframe(url: str, proxy: str | None) -> list[Any]:
    """Adapted from anicli-api ``CdnVideoHub.a_parse`` (MIT) for AnimeGO's current URL scheme."""
    match = _ANIMEGO_CDN_IFRAME.match(url)
    if not match:
        return []
    _title_id, season, episode = (int(part) for part in match.groups())
    dubbing = (parse_qs(urlsplit(url).query).get("dubbing") or [""])[0]
    origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    async with make_async_client(proxy) as client:
        response = await client.get(url, headers={"referer": origin})
        response.raise_for_status()
        options = PageParseCdnVideoData(response.text).parse()
        result = await CdnVideoHubAPI.async_get_params_from_page(
            client, pub=options["data_publisher_id"], aggr=options["data_aggregator"], id=options["data_title_id"]
        )
        if not result.is_ok:
            raise RuntimeError("CVH catalog request failed")
        wanted = voiceover_key(dubbing)
        for item in result.value["items"]:
            if item["episode"] == episode and item["season"] == season and voiceover_key(item["voiceStudio"]) == wanted:
                return await a_video_playlist_from_vk_id(client, item["vkId"])
    return []


async def _yummy_cvh_iframe(source: Any, proxy: str | None) -> list[Any]:
    """Awaited variant of anicli-api ``yummy_anime.Source.a_get_videos`` (MIT) CVH branch."""
    cls = type(source)
    async with make_async_client(proxy) as client:
        page = await client.get(source.url)
        js_url = cls._get_js_url(urlsplit(source.url).netloc, page.text)
        anime_id, episode, dubbing_code = cls._extract_iframe_params(source.url)
        script = await client.get(js_url)
        pub_id, aggr = cls._extract_script_params(script.text)
        result = await CdnVideoHubAPI.async_get_params_from_page(client, pub=pub_id, aggr=aggr, id=anime_id)
        if not result.is_ok:
            raise RuntimeError("CVH catalog request failed")
        vkid = cls._cdnvideohub_extract_vkid_cadidate(result.value, episode, dubbing_code)
        return await a_video_playlist_from_vk_id(client, vkid)


async def _decoder(url: str, proxy: str | None) -> list[Any] | None:
    for decoder in ALL_DECODERS:
        if not decoder._compare_url(url):
            continue
        config = dict(getattr(decoder, "DEFAULT_HTTP_CONFIG", {}) or {})
        headers = {**EXTRACTION_HEADERS, **(config.pop("headers", {}) or {})}
        a_http = make_async_client(proxy, headers=headers, **config)
        s_http = make_sync_client(proxy, headers=headers, **config)
        try:
            return list(await decoder(http=s_http, a_http=a_http).a_parse(url))
        finally:
            await a_http.aclose()
            s_http.close()
    return None


async def extract_videos(source: Any, proxy: str | None) -> list[Any]:
    """Return anicli ``Video`` objects for one player source. Raises on extractor failure."""
    url = getattr(source, "url", "") or ""
    vk_id = getattr(source, "cdn_videohub_vk_id", None)
    if vk_id:
        async with make_async_client(proxy) as client:
            return list(await a_video_playlist_from_vk_id(client, vk_id))
    if _ANIMEGO_CDN_IFRAME.match(url):
        return list(await _animego_cdn_iframe(url, proxy))
    if _YUMMY_CVH_IFRAME.search(url) and hasattr(type(source), "_get_js_url"):
        return list(await _yummy_cvh_iframe(source, proxy))
    decoded = await _decoder(url, proxy)
    if decoded is not None:
        return decoded
    if type(source).a_get_videos is not BaseSource.a_get_videos:
        result = source.a_get_videos()
        while inspect.isawaitable(result):  # some upstream sources return an un-awaited coroutine
            result = await result
        return list(result or [])
    raise LookupError(f"No extractor for player {player_label(url)}")


def pick_video(videos: list[Any], quality: int, allowed_types: tuple[str, ...]) -> Any | None:
    """Closest quality not above ``quality`` (else the lowest above), preferring HLS for equal quality."""
    candidates = [v for v in videos if getattr(v, "type", None) in allowed_types and getattr(v, "url", None)]
    if not candidates:
        return None
    type_rank = {kind: i for i, kind in enumerate(allowed_types)}
    at_or_below = [v for v in candidates if int(v.quality) <= quality]
    pool = at_or_below or candidates
    target = max(int(v.quality) for v in pool) if at_or_below else min(int(v.quality) for v in pool)
    same = [v for v in pool if int(v.quality) == target]
    return min(same, key=lambda v: type_rank.get(v.type, 99))


def available_qualities(videos: list[Any], allowed_types: tuple[str, ...]) -> list[int]:
    return sorted({int(v.quality) for v in videos if v.type in allowed_types and int(v.quality) > 0}, reverse=True)


async def with_timeout(coro, timeout: float):
    return await asyncio.wait_for(coro, timeout=timeout)
