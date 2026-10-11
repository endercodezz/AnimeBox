"""Deterministic stand-ins for providers (no network in CI)."""

from __future__ import annotations

from backend.providers.errors import NotFound, StreamUnavailable
from backend.providers.health import HealthTracker
from backend.providers.registry import ResolvedStream, ResolvedVideo
from backend.schemas import AnimeDetail, EpisodeInfo, SearchResponse, SearchResult, VoiceoverOption

ANIME_ID = "animego:%2Fanime%2Ffixture-1"


class FakeRegistry:
    proxy = None
    enabled_sources = ["animego"]
    default_source = "animego"

    def __init__(self, episodes: int = 3, title: str = "Fixture Anime") -> None:
        self.title = title
        self.episodes = episodes
        self.health = HealthTracker(None)
        self.detail_calls = 0
        self.resolve_calls: list[dict] = []
        self.stream = ResolvedVideo(type="m3u8", quality=720, url="https://cdn.example.com/master.m3u8", headers={"User-Agent": "UA"})
        self.fail_stream = False

    async def get_anime(self, external_id: str) -> AnimeDetail:
        self.detail_calls += 1
        if external_id != ANIME_ID:
            raise NotFound("Anime not found", source="animego", stage="details")
        return AnimeDetail(
            id=external_id,
            title=self.title,
            poster="https://img.example.com/poster.jpg",
            description="desc",
            year=2011,
            source="animego",
            source_label="AnimeGO",
            episodes=[EpisodeInfo(title=f"Episode {i}", ordinal=i) for i in range(1, self.episodes + 1)],
        )

    async def get_episode_voiceovers(self, external_id: str, episode: int) -> list[VoiceoverOption]:
        return [VoiceoverOption(title="AniLibria", players=["kodik"], index=0)]

    async def resolve_stream(self, external_id, episode, voiceover=None, quality=None, **kwargs) -> ResolvedStream:
        self.resolve_calls.append({"episode": episode, "voiceover": voiceover, "quality": quality, **kwargs})
        if self.fail_stream:
            raise StreamUnavailable("No working stream", source="animego", stage="stream", attempts=[])
        return ResolvedStream(
            anime_title=self.title,
            episode=episode,
            voiceover=voiceover or "AniLibria",
            player="kodik",
            video=self.stream,
            qualities=[720, 480],
            browser_playable=True,
            source="animego",
        )

    async def search(self, query: str, sources=None) -> SearchResponse:
        return SearchResponse(
            query=query,
            results=[SearchResult(id=ANIME_ID, title=self.title, source="animego")],
            providers=[],
        )

    def ordered_sources(self):
        from backend.providers.catalog import SOURCES

        return list(SOURCES)

    async def aclose(self) -> None:
        return None
