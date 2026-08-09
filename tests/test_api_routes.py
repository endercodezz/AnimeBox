from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from backend.api import routes
from backend.schemas import VoiceoverOption


@pytest.mark.asyncio
async def test_episode_voiceovers_route_is_not_shadowed_by_anime_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []

    class FakeRegistry:
        async def get_episode_voiceovers(self, anime_id: str, episode: int) -> list[VoiceoverOption]:
            calls.append((anime_id, episode))
            return [
                VoiceoverOption(
                    title="AniLibria",
                    url="https://player.example/episode-1",
                    player_host="player.example",
                    index=0,
                )
            ]

    monkeypatch.setattr(routes, "get_registry", lambda: FakeRegistry())
    app = FastAPI()
    app.include_router(routes.router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/anime/animego:fixture/episodes/1/voiceovers")

    assert response.status_code == 200
    assert response.json() == [
        {
            "title": "AniLibria",
            "url": "https://player.example/episode-1",
            "player_host": "player.example",
            "index": 0,
        }
    ]
    assert calls == [("animego:fixture", 1)]
