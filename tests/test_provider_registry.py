"""Provider engine: isolation of failures, player fallback, exact cache recovery, health."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from backend.config import Settings
from backend.providers import players
from backend.providers.errors import CacheExpired, NotFound, StreamUnavailable
from backend.providers.health import HealthTracker, SourceHealth, StageResult
from backend.providers.ids import canonical_id, decode_external_id, encode_external_id
from backend.providers.registry import AnicliProvider, ProviderRegistry


def make_registry(tmp_path, **overrides) -> ProviderRegistry:
    settings = Settings(
        _env_file=None,
        data_path=tmp_path / "data",
        library_path=tmp_path / "library",
        database_url="sqlite+aiosqlite:///:memory:",
        **overrides,
    )
    return ProviderRegistry(settings, health=HealthTracker(None))


@dataclass
class Hit:
    title: str
    url: str
    thumbnail: str = ""


class FakeExtractor:
    def __init__(self, behaviour):
        self.behaviour = behaviour

    async def a_search(self, query):
        return await self.behaviour(query)


@pytest.fixture
def extractors(monkeypatch):
    table: dict[str, object] = {}
    monkeypatch.setattr(AnicliProvider, "extractor", lambda self: FakeExtractor(table[self.spec.id]))
    return table


async def test_search_returns_fast_results_when_another_provider_hangs(tmp_path, extractors):
    registry = make_registry(tmp_path, provider_search_timeout=0.05)
    cancelled = asyncio.Event()

    async def fast(_q):
        return [Hit("K-On!", "/anime/k-on-1")]

    async def hang(_q):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    extractors.update(animego=fast, anilibria=hang)
    response = await asyncio.wait_for(registry.search("k-on", sources=["animego", "anilibria"]), timeout=1)

    assert [(r.source, r.title) for r in response.results] == [("animego", "K-On!")]
    status = {p.source: p for p in response.providers}
    assert status["animego"].ok and status["animego"].count == 1
    assert not status["anilibria"].ok and status["anilibria"].timed_out
    assert cancelled.is_set()
    assert registry.health.get("anilibria").stages["search"].ok is False


async def test_search_keeps_results_when_another_provider_raises(tmp_path, extractors):
    registry = make_registry(tmp_path)

    async def fast(_q):
        return [Hit("K-On!", "/anime/k-on-1"), Hit("K-On!", "/anime/k-on-1")]

    async def broken(_q):
        raise RuntimeError("HTTP 403 from provider")

    extractors.update(animego=fast, animevost=broken)
    response = await registry.search("k-on", sources=["animego", "animevost"])
    assert len(response.results) == 1  # same id deduplicated
    failed = next(p for p in response.providers if p.source == "animevost")
    assert "403" in failed.error


async def test_unknown_sources_are_ignored_and_not_crashing(tmp_path, extractors):
    registry = make_registry(tmp_path)

    async def fast(_q):
        return []

    extractors.update(animego=fast)
    response = await registry.search("x", sources=["animego", "not-a-source"])
    assert [p.source for p in response.providers] == ["animego"]


async def test_cache_recovery_never_returns_a_lookalike_title(tmp_path, extractors):
    registry = make_registry(tmp_path)

    async def lookalikes(_q):
        return [Hit("Steins;Gate 0", "/anime/steins-gate-0-2"), Hit("Steins;Gate Movie", "/anime/steins-gate-movie-3")]

    extractors.update(anilibria=lookalikes)
    external_id = encode_external_id("anilibria", "id:762")
    registry.remember_title(external_id, "Steins;Gate")
    with pytest.raises(CacheExpired):
        await registry._search_object(external_id)


def _source(voiceover: str, label: str) -> players.PlayerSource:
    return players.PlayerSource(voiceover=voiceover, url=f"https://{label}.example/{voiceover}", label=label, raw=label)


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    registry = make_registry(tmp_path)
    sources = [_source("AniLibria", "cvh"), _source("AniLibria", "kodik"), _source("SHIZA", "sibnet")]
    behaviour: dict[str, object] = {}
    calls: list[str] = []

    async def fake_anime(_id):
        return SimpleNamespace(title="Fixture")

    async def fake_sources(_id, _episode, refresh=False):
        return sources

    async def fake_extract(raw, _proxy):
        calls.append(raw)
        result = behaviour.get(raw, [])
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(registry, "_anime", fake_anime)
    monkeypatch.setattr(registry, "_player_sources", fake_sources)
    monkeypatch.setattr(players, "extract_videos", fake_extract)
    monkeypatch.setattr(players, "player_health", players.PlayerHealth())
    return registry, behaviour, calls


def video(kind: str, quality: int, url: str = "https://cdn.example/v"):
    return SimpleNamespace(type=kind, quality=quality, url=url, headers={})


async def test_stream_falls_back_to_next_player_of_same_voiceover(pipeline):
    registry, behaviour, calls = pipeline
    behaviour["kodik"] = []  # a broken player returns nothing (AnimeGO cdn-iframe did this in 1.x)
    behaviour["cvh"] = [video("m3u8", 720), video("m3u8", 480)]

    stream = await registry.resolve_stream("animego:%2Fanime%2Fx", 1, voiceover="AniLibria", quality=1080)
    assert calls == ["kodik", "cvh"]
    assert (stream.voiceover, stream.player, stream.video.quality) == ("AniLibria", "cvh", 720)
    assert stream.qualities == [720, 480]
    assert stream.video.headers["User-Agent"]  # consistent client identity is always attached

    calls.clear()  # the failed player is demoted for the next request
    await registry.resolve_stream("animego:%2Fanime%2Fx", 1, voiceover="AniLibria")
    assert calls == ["cvh"]


async def test_explicit_voiceover_never_silently_switches(pipeline):
    registry, behaviour, _calls = pipeline
    behaviour["sibnet"] = RuntimeError("timeout")
    behaviour["kodik"] = [video("m3u8", 720)]
    with pytest.raises(StreamUnavailable) as info:
        await registry.resolve_stream("animego:%2Fanime%2Fx", 1, voiceover="SHIZA")
    assert info.value.attempts and all(a["voiceover"] == "SHIZA" for a in info.value.attempts)


async def test_unknown_voiceover_is_not_found(pipeline):
    registry, _behaviour, _calls = pipeline
    with pytest.raises(NotFound):
        await registry.resolve_stream("animego:%2Fanime%2Fx", 1, voiceover="Does Not Exist")


async def test_auto_voiceover_uses_preferences_then_falls_back(pipeline):
    registry, behaviour, _calls = pipeline
    registry.settings.preferred_voiceovers = "SHIZA,AniLibria"
    behaviour["sibnet"] = RuntimeError("dead")
    behaviour["kodik"] = [video("m3u8", 720)]
    stream = await registry.resolve_stream("animego:%2Fanime%2Fx", 1)
    assert stream.voiceover == "AniLibria"


async def test_dash_only_player_is_not_offered_for_browser_playback(pipeline):
    registry, behaviour, _calls = pipeline
    behaviour["cvh"] = [video("mpd", 1080)]
    behaviour["kodik"] = RuntimeError("down")
    with pytest.raises(StreamUnavailable):
        await registry.resolve_stream("animego:%2Fanime%2Fx", 1, voiceover="AniLibria")
    download = await registry.resolve_stream("animego:%2Fanime%2Fx", 1, voiceover="AniLibria", purpose="download")
    assert download.video.type == "mpd" and download.browser_playable is False


def test_player_ranking_demotes_recent_failures():
    health = players.PlayerHealth()
    assert health.rank("kodik") < health.rank("cvh")
    health.failure("kodik")
    assert health.rank("kodik") > health.rank("cvh")
    health.success("kodik")
    assert health.rank("kodik") == 0


def test_pick_video_prefers_hls_and_closest_lower_quality():
    videos = [video("mpd", 1080), video("m3u8", 1080), video("mp4", 720), video("m3u8", 360)]
    assert players.pick_video(videos, 1080, players.BROWSER_TYPES).type == "m3u8"
    assert players.pick_video(videos, 720, players.BROWSER_TYPES).quality == 720
    assert players.pick_video(videos, 240, players.BROWSER_TYPES).quality == 360  # lowest above when nothing below
    assert players.pick_video([video("mpd", 1080)], 1080, players.BROWSER_TYPES) is None


@pytest.mark.parametrize(
    ("url", "label"),
    [
        ("https://animego.me/cdn-iframe/9253/1/1?dubbing=AnilibriaTV", "cvh"),
        ("https://kodikplayer.com/seria/1/abc/720p", "kodik"),
        ("https://aniboom.one/embed/x?episode=1", "aniboom"),
        ("https://video.sibnet.ru/shell.php?videoid=1", "sibnet"),
        ("https://player.example.org/e/1", "player.example.org"),
    ],
)
def test_player_labels(url, label):
    assert players.player_label(url) == label


def test_voiceover_normalisation():
    assert players.normalize_voiceover("Озвучка AniLibria") == "AniLibria"
    assert players.voiceover_key("СВ-Дубль") == players.voiceover_key("св дубль")
    assert players.voiceover_kind("Субтитры") == "subtitles"
    assert players.voiceover_kind("AniDUB") == "dub"


def test_health_status_requires_every_stage():
    health = SourceHealth()
    assert health.status == "unknown"
    health.stages["search"] = StageResult(ok=True, at=0)
    assert health.status == "partial"
    for stage in ("details", "episodes", "voiceovers", "stream"):
        health.stages[stage] = StageResult(ok=True, at=0)
    assert health.status == "ok"
    health.stages["stream"] = StageResult(ok=False, at=0, error="403")
    assert health.status == "degraded"
    health.stages["search"] = StageResult(ok=False, at=0)
    assert health.status == "down"


def test_health_persists(tmp_path):
    path = tmp_path / "health.json"
    HealthTracker(path).record("animego", "search", True, 120)
    assert HealthTracker(path).get("animego").stages["search"].latency_ms == 120


def test_ids_are_canonical():
    assert canonical_id("animego:/anime/x-1") == canonical_id("animego:%2Fanime%2Fx-1") == "animego:%2Fanime%2Fx-1"
    assert decode_external_id("anilibria:id%3A762") == ("anilibria", "id:762")
    with pytest.raises(ValueError):
        decode_external_id("no-colon")
    with pytest.raises(ValueError):
        decode_external_id("../etc:passwd")


def test_excluded_and_unknown_modules_are_not_exposed():
    from backend.providers.catalog import EXCLUDED_MODULES, SOURCE_BY_ID

    assert "hdrezka" in EXCLUDED_MODULES and "hdrezka" not in SOURCE_BY_ID
    assert SOURCE_BY_ID["animego"].stable and SOURCE_BY_ID["animego"].enabled_by_default
