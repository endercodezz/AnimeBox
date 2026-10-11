"""HTTP API behaviour: progress persistence, error mapping, validation, host protection."""

from __future__ import annotations

import httpx
import pytest
from fakes import ANIME_ID, FakeRegistry

import backend.providers.registry as registry_module
from backend.downloader.manager import download_manager
from backend.providers.errors import ProviderTimeout


@pytest.fixture
def fake_registry(monkeypatch):
    fake = FakeRegistry()
    monkeypatch.setattr(registry_module, "_registry", fake)
    return fake


async def test_online_progress_is_saved_and_restorable(client):
    body = {
        "anime_id": "animego:/anime/fixture-1",  # legacy spelling is canonicalised
        "anime_title": "Fixture Anime",
        "episode": 3,
        "voiceover": "AniLibria",
        "progress_seconds": 615.5,
        "duration_seconds": 1440,
    }
    assert (await client.post("/api/progress", json=body)).status_code == 200
    body["progress_seconds"] = 700
    saved = (await client.post("/api/progress", json=body)).json()
    assert saved["anime_external_id"] == ANIME_ID and saved["progress_seconds"] == 700 and not saved["completed"]

    restored = (await client.get("/api/history/anime", params={"id": ANIME_ID})).json()
    assert [(h["episode"], h["progress_seconds"], h["voiceover"]) for h in restored] == [(3, 700, "AniLibria")]

    home = (await client.get("/api/home")).json()
    assert [h["episode"] for h in home["continue_watching"]] == [3]
    assert home["recently_downloaded"] == []


async def test_finished_episode_leaves_continue_watching(client):
    await client.post("/api/progress", json={"anime_id": ANIME_ID, "episode": 1, "progress_seconds": 1400, "duration_seconds": 1440})
    home = (await client.get("/api/home")).json()
    assert home["continue_watching"] == []
    assert home["recently_watched"][0]["completed"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"anime_id": ANIME_ID, "episode": 1, "progress_seconds": -5},
        {"anime_id": ANIME_ID, "episode": -1, "progress_seconds": 5},
        {"episode": 1, "progress_seconds": 5},
    ],
)
async def test_progress_validation(client, payload):
    assert (await client.post("/api/progress", json=payload)).status_code in (400, 422)


async def test_invalid_ids_are_rejected(client, fake_registry):
    response = await client.get("/api/anime", params={"id": "no-colon"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_id"


async def test_provider_errors_map_to_structured_responses(client, fake_registry):
    missing = await client.get("/api/anime", params={"id": "animego:%2Fanime%2Funknown"})
    assert missing.status_code == 404 and missing.json()["detail"]["stage"] == "details"

    async def slow(_id):
        raise ProviderTimeout("details timed out after 25s", source="animego", stage="details")

    fake_registry.get_anime = slow
    timeout = await client.get("/api/anime", params={"id": ANIME_ID})
    assert timeout.status_code == 504
    assert timeout.json()["detail"] == {
        "code": "provider_timeout",
        "message": "details timed out after 25s",
        "source": "animego",
        "stage": "details",
    }


async def test_stream_resolve_returns_scoped_media_url(client, fake_registry):
    response = await client.post("/api/stream/resolve", json={"anime_id": ANIME_ID, "episode": 2, "voiceover": "AniLibria"})
    assert response.status_code == 200
    data = response.json()
    assert data["url"].startswith("/api/media/") and "cdn.example.com" not in data["url"]
    assert data["player"] == "kodik" and data["qualities"] == [720, 480]

    fake_registry.fail_stream = True
    failed = await client.post("/api/stream/resolve", json={"anime_id": ANIME_ID, "episode": 2})
    assert failed.status_code == 502 and failed.json()["detail"]["code"] == "stream_unavailable"


async def test_download_api_queues_season_and_reports_skips(client, fake_registry, monkeypatch):
    monkeypatch.setattr(download_manager, "_wakeup", __import__("asyncio").Event())
    first = (await client.post("/api/downloads", json={"anime_id": ANIME_ID, "episodes": [1, 2]})).json()
    assert [j["episode"] for j in first["jobs"]] == [1, 2] and first["skipped"] == []
    season = (await client.post("/api/downloads", json={"anime_id": ANIME_ID})).json()
    assert [j["episode"] for j in season["jobs"]] == [3]
    assert {s["episode"]: s["reason"] for s in season["skipped"]} == {1: "already_queued", 2: "already_queued"}

    bad = await client.post("/api/downloads", json={"anime_id": ANIME_ID, "episodes": [99]})
    assert bad.status_code == 404
    active = (await client.get("/api/downloads", params={"status": "active"})).json()
    assert len(active) == 3
    # Queuing never makes a title appear in the offline library.
    assert (await client.get("/api/library")).json() == []


async def test_settings_validation_and_roundtrip(client):
    current = (await client.get("/api/settings")).json()
    assert current["default_source"] == "animego" and "animego" in current["enabled_sources"]

    assert (await client.put("/api/settings", json={"default_quality": 999})).status_code == 422
    assert (await client.put("/api/settings", json={"http_proxy": "javascript:alert(1)"})).status_code == 422
    assert (await client.put("/api/settings", json={"enabled_sources": ["hdrezka"]})).status_code == 422
    assert (await client.put("/api/settings", json={"max_concurrent_downloads": 50})).status_code == 422

    updated = await client.put(
        "/api/settings",
        json={"default_quality": 720, "preferred_voiceovers": ["AniDUB", " AniDUB ", "AniLibria"], "max_concurrent_downloads": 3},
    )
    assert updated.status_code == 200
    data = updated.json()
    assert data["default_quality"] == 720
    assert data["preferred_voiceovers"] == ["AniDUB", "AniLibria"]
    assert data["max_concurrent_downloads"] == 3


async def test_providers_are_listed_with_honest_status(client):
    providers = (await client.get("/api/providers")).json()
    assert providers[0]["id"] == "animego"
    assert all(p["status"] in {"unknown", "partial", "ok", "degraded", "down"} for p in providers)
    assert "hdrezka" not in {p["id"] for p in providers}


async def test_main_app_rejects_foreign_host_headers(db_reset):
    from backend.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
        assert (await http.get("/api/health")).json()["version"] == "2.0.0"
        rebinding = await http.get("/api/session", headers={"Host": "attacker.example:8787"})
        assert rebinding.status_code == 400
        assert (await http.get("/api/does-not-exist")).status_code == 404
