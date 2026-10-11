"""Regression tests for the 1.x "empty anime in library" bug and library/file integrity."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import write_media
from fakes import ANIME_ID, FakeRegistry
from sqlalchemy import select

import backend.providers.registry as registry_module
from backend.database.session import SessionLocal
from backend.models import AnimeTitle, LibraryEpisode
from backend.services import library


@pytest.fixture
def fake_registry(monkeypatch):
    fake = FakeRegistry()
    monkeypatch.setattr(registry_module, "_registry", fake)
    return fake


async def add_episode(anime_id: str, title: str, episode: int, root: Path, *, create_file: bool = True, size: int = 4096):
    path = library.episode_file_path(title, 1, episode, "mp4", root)
    if create_file:
        write_media(path, size)
    async with SessionLocal() as db:
        db.add(
            LibraryEpisode(
                anime_external_id=anime_id,
                season=1,
                episode=episode,
                title=f"Episode {episode}",
                file_path=library.to_stored_path(path, root),
            )
        )
        if episode == 1:
            db.add(AnimeTitle(external_id=anime_id, source="animego", title=title))
        await db.commit()
    return path


async def test_library_is_empty_initially(client):
    response = await client.get("/api/library")
    assert response.status_code == 200
    assert response.json() == []


async def test_opening_details_creates_no_directory_and_no_library_entry(client, fake_registry, library_root):
    response = await client.get("/api/anime", params={"id": ANIME_ID})
    assert response.status_code == 200
    assert response.json()["title"] == "Fixture Anime"

    assert list(library_root.iterdir()) == []  # no folder side effect
    assert (await client.get("/api/library")).json() == []

    async with SessionLocal() as db:  # catalog metadata may be cached, but never as library content
        row = (await db.execute(select(AnimeTitle).where(AnimeTitle.external_id == ANIME_ID))).scalar_one()
        assert row.folder_path is None


async def test_double_encoded_id_resolves_to_same_title(client, fake_registry):
    legacy = "animego:/anime/fixture-1"  # how 1.x frontends sent ids after decoding twice
    response = await client.get("/api/anime", params={"id": legacy})
    assert response.status_code == 200
    assert response.json()["id"] == ANIME_ID


async def test_search_and_history_do_not_populate_library(client, fake_registry, library_root):
    assert (await client.get("/api/search", params={"q": "fixture"})).status_code == 200
    saved = await client.post(
        "/api/progress", json={"anime_id": ANIME_ID, "anime_title": "Fixture Anime", "episode": 1, "progress_seconds": 30}
    )
    assert saved.status_code == 200
    assert (await client.get("/api/library")).json() == []
    assert list(library_root.iterdir()) == []


async def test_library_lists_only_titles_with_existing_valid_files(client, library_root):
    await add_episode(ANIME_ID, "Fixture Anime", 1, library_root)
    await add_episode(ANIME_ID, "Fixture Anime", 2, library_root, create_file=False)  # deleted by the user
    await add_episode("animego:%2Fanime%2Fghost-2", "Ghost", 1, library_root, create_file=False)
    await add_episode("animego:%2Fanime%2Ftiny-3", "Tiny", 1, library_root, size=10)  # truncated file

    items = (await client.get("/api/library")).json()
    assert [item["id"] for item in items] == [ANIME_ID]
    assert items[0]["episode_count"] == 1
    assert items[0]["missing_count"] == 1
    assert items[0]["size_bytes"] == 4096

    episodes = (await client.get("/api/library/episodes", params={"id": ANIME_ID})).json()
    assert [(e["episode"], e["available"]) for e in episodes] == [(1, True), (2, False)]
    assert episodes[1]["stream_url"] is None


async def test_partial_file_is_not_library_content(client, library_root):
    path = library.episode_file_path("Fixture Anime", 1, 1, "mp4", library_root)
    write_media(library.partial_path(path))
    async with SessionLocal() as db:
        db.add(
            LibraryEpisode(
                anime_external_id=ANIME_ID,
                season=1,
                episode=1,
                file_path=library.to_stored_path(library.partial_path(path), library_root),
            )
        )
        await db.commit()
    assert (await client.get("/api/library")).json() == []


async def test_missing_file_returns_404_and_existing_file_supports_range(client, library_root):
    await add_episode(ANIME_ID, "Fixture Anime", 1, library_root)
    episodes = (await client.get("/api/library/episodes", params={"id": ANIME_ID})).json()
    ranged = await client.get(episodes[0]["stream_url"], headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206
    assert ranged.headers["content-type"].startswith("video/mp4")

    library.resolve_stored_path(f"Fixture Anime/Season 1/Episode 01.mp4", library_root).unlink()
    gone = await client.get(episodes[0]["stream_url"])
    assert gone.status_code == 404
    assert (await client.get("/api/library")).json() == []


async def test_delete_anime_removes_files_rows_and_folder(client, library_root):
    path = await add_episode(ANIME_ID, "Fixture Anime", 1, library_root)
    (path.parent.parent / "poster.jpg").write_bytes(b"jpg")
    response = await client.delete("/api/library/anime", params={"id": ANIME_ID})
    assert response.status_code == 200
    assert not path.exists()
    assert not (library_root / "Fixture Anime").exists()
    assert (await client.get("/api/library")).json() == []
    assert (await client.delete("/api/library/anime", params={"id": ANIME_ID})).status_code == 404


async def test_rescan_prunes_missing_rows_and_imports_tracked_folders(client, library_root):
    await add_episode(ANIME_ID, "Fixture Anime", 1, library_root, create_file=False)
    orphan = write_media(library.episode_file_path("Other", 1, 4, "mp4", library_root))
    library.write_metadata(orphan.parent.parent, {"id": "animego:/anime/other-9", "title": "Other"})
    (library_root / "Empty Browse Folder").mkdir()  # left behind by AnimeBox 1.x

    result = (await client.post("/api/library/rescan")).json()
    assert result == {"removed_missing": 1, "imported": 1, "removed_empty_dirs": 1}
    items = (await client.get("/api/library")).json()
    assert [(i["id"], i["title"], i["episode_count"]) for i in items] == [
        ("animego:%2Fanime%2Fother-9", "Other", 1)
    ]
    assert orphan.exists()


def test_path_helpers_are_pure(library_root):
    target = library.episode_file_path("New Title", 2, 3, "mp4", library_root)
    assert target == library_root / "New Title" / "Season 2" / "Episode 03.mp4"
    assert not (library_root / "New Title").exists()


def test_legacy_relative_paths_resolve(monkeypatch, tmp_path):
    app_root = tmp_path / "app"
    root = app_root / "library"
    write_media(root / "Show" / "Season 1" / "Episode 01.mp4")
    monkeypatch.setattr(library, "ROOT_DIR", app_root)
    assert library.resolve_stored_path("library\\Show\\Season 1\\Episode 01.mp4", root).is_file()
    assert library.resolve_stored_path("Show/Season 1/Episode 01.mp4", root).is_file()
