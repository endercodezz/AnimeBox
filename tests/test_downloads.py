"""Download manager: queue rules, validation, atomic finalisation, recovery, concurrency."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from conftest import write_media
from fakes import ANIME_ID, FakeRegistry
from sqlalchemy import select

import backend.providers.registry as registry_module
from backend.database.session import SessionLocal
from backend.downloader import manager as manager_module
from backend.downloader.manager import DownloadManager
from backend.models import DownloadJob, LibraryEpisode
from backend.player import sessions
from backend.providers.errors import NotFound
from backend.providers.http import media_clients
from backend.services import ffmpeg_tools, library

EPISODE_SECONDS = 1440.0


@pytest.fixture
def fake_registry(monkeypatch):
    fake = FakeRegistry()
    monkeypatch.setattr(registry_module, "_registry", fake)

    async def resolve(host, _port):
        return ["93.184.216.34"]

    monkeypatch.setattr(sessions, "_resolve", resolve)
    sessions._dns_cache.clear()
    return fake


@pytest.fixture
def ffmpeg(monkeypatch):
    """Fake ffmpeg: writes the output file and reports real-looking progress."""
    state = {"calls": [], "duration": EPISODE_SECONDS, "fail": None, "block": None}

    async def fake_download(url, dest: Path, headers=None, *, on_progress=None, hls=False):
        state["calls"].append({"url": url, "dest": dest, "hls": hls})
        if state["block"] is not None:
            await state["block"].wait()
        if state["fail"]:
            raise RuntimeError(state["fail"])
        write_media(dest, 8192)
        if on_progress:
            on_progress(ffmpeg_tools.FfmpegProgress(out_seconds=EPISODE_SECONDS / 2, total_size=4096, duration=EPISODE_SECONDS))
        return dest

    async def fake_probe(path: Path):
        return state["duration"]

    monkeypatch.setattr(ffmpeg_tools, "download_stream_with_ffmpeg", fake_download)
    monkeypatch.setattr(ffmpeg_tools, "probe_duration", fake_probe)
    monkeypatch.setattr(ffmpeg_tools, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(manager_module, "RETRY_DELAYS", (0.0, 0.0))
    return state


@pytest.fixture
def no_poster(monkeypatch):
    async def save_poster(*_args, **_kwargs):
        return None

    monkeypatch.setattr(library, "save_poster", save_poster)


async def enqueue(manager: DownloadManager, episode: int = 1, **kwargs):
    return await manager.enqueue(
        anime_id=ANIME_ID,
        anime_title="Fixture Anime",
        source="animego",
        season=1,
        episode=episode,
        episode_title=f"Episode {episode}",
        voiceover=kwargs.pop("voiceover", "AniLibria"),
        steam_deck=kwargs.pop("steam_deck", False),
        **kwargs,
    )


async def job(job_id: int) -> DownloadJob:
    async with SessionLocal() as db:
        return await db.get(DownloadJob, job_id)


async def library_rows() -> list[LibraryEpisode]:
    async with SessionLocal() as db:
        return list((await db.execute(select(LibraryEpisode))).scalars().all())


async def test_successful_hls_download_goes_through_local_proxy_and_lands_atomically(
    db_reset, fake_registry, ffmpeg, no_poster, library_root
):
    manager = DownloadManager()
    created, reason = await enqueue(manager)
    assert reason is None
    await manager._process(created.id)

    done = await job(created.id)
    assert done.status == "completed" and done.progress == 100.0 and done.error is None
    final = library_root / "Fixture Anime" / "Season 1" / "Episode 01.mp4"
    assert final.is_file()
    assert not list(library_root.rglob("*.part.*"))
    call = ffmpeg["calls"][0]
    assert call["hls"] and call["url"].startswith("http://127.0.0.1:") and "/api/media/" in call["url"]
    assert call["dest"].name == "Episode 01.part.mp4"
    rows = await library_rows()
    assert [(r.episode, r.voiceover, r.quality, r.file_path) for r in rows] == [
        (1, "AniLibria", 720, "Fixture Anime/Season 1/Episode 01.mp4")
    ]
    assert library.read_metadata(final.parent.parent)["id"] == ANIME_ID
    assert fake_registry.resolve_calls[0]["purpose"] == "download"


async def test_duplicate_requests_are_skipped(db_reset, fake_registry, ffmpeg, no_poster):
    manager = DownloadManager()
    first, _ = await enqueue(manager)
    assert (await enqueue(manager))[1] == "already_queued"
    await manager._process(first.id)
    assert (await enqueue(manager))[1] == "already_downloaded"
    replaced, reason = await enqueue(manager, replace=True, voiceover="AniDUB")
    assert reason is None and replaced is not None


async def test_incomplete_download_fails_without_library_entry(db_reset, fake_registry, ffmpeg, no_poster, library_root):
    ffmpeg["duration"] = EPISODE_SECONDS * 0.5  # truncated stream
    manager = DownloadManager()
    created, _ = await enqueue(manager)
    await manager._process(created.id)

    failed = await job(created.id)
    assert failed.status == "failed" and "incomplete" in failed.error.lower()
    assert failed.attempts == manager_module.MAX_ATTEMPTS
    assert await library_rows() == []
    assert not list(library_root.rglob("*.mp4"))
    assert not (library_root / "Fixture Anime").exists()


async def test_transient_failure_is_retried_with_fresh_resolution(db_reset, fake_registry, ffmpeg, no_poster):
    manager = DownloadManager()
    created, _ = await enqueue(manager)
    original = ffmpeg_tools.download_stream_with_ffmpeg
    attempts = {"n": 0}

    async def flaky(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("ffmpeg failed with exit code 1: HTTP error 403")
        return await original(*args, **kwargs)

    ffmpeg_tools.download_stream_with_ffmpeg = flaky
    try:
        await manager._process(created.id)
    finally:
        ffmpeg_tools.download_stream_with_ffmpeg = original
    assert (await job(created.id)).status == "completed"
    assert [c.get("refresh") for c in fake_registry.resolve_calls] == [False, True]


async def test_missing_episode_fails_immediately(db_reset, fake_registry, ffmpeg, no_poster):
    async def gone(*_a, **_k):
        raise NotFound("Episode 1 not found", source="animego", stage="episodes")

    fake_registry.resolve_stream = gone
    manager = DownloadManager()
    created, _ = await enqueue(manager)
    await manager._process(created.id)
    failed = await job(created.id)
    assert failed.status == "failed" and failed.attempts == 1


async def test_poster_failure_does_not_fail_valid_download(db_reset, fake_registry, ffmpeg, monkeypatch):
    async def broken_poster(*_args, **_kwargs):
        raise OSError("disk full while writing poster")

    monkeypatch.setattr(library, "save_poster", broken_poster)
    manager = DownloadManager()
    created, _ = await enqueue(manager)
    async with SessionLocal() as db:
        from backend.services import library_index

        await library_index.upsert_title(db, anime_id=ANIME_ID, source="animego", title="Fixture Anime", poster="https://img.example.com/p.jpg")
        await db.commit()
    await manager._process(created.id)
    done = await job(created.id)
    assert done.status == "completed"
    assert "poster" in (done.warning or "")
    assert len(await library_rows()) == 1


async def test_steam_deck_failure_keeps_original_file(db_reset, fake_registry, ffmpeg, no_poster, monkeypatch, library_root):
    async def failing_transcode(src, dest, on_progress=None):
        raise RuntimeError("libx265 missing")

    monkeypatch.setattr(ffmpeg_tools, "optimize_for_steam_deck", failing_transcode)
    manager = DownloadManager()
    created, _ = await enqueue(manager, steam_deck=True)
    await manager._process(created.id)
    done = await job(created.id)
    assert done.status == "completed" and "Steam Deck optimization failed" in done.warning
    assert (library_root / "Fixture Anime" / "Season 1" / "Episode 01.mp4").is_file()


async def test_recovery_requeues_interrupted_jobs_and_cleans_orphan_parts(db_reset, library_root):
    orphan = write_media(library_root / "Old" / "Season 1" / "Episode 03.part.mp4")
    keep_final = library_root / "Keep" / "Season 1" / "Episode 01.mp4"
    kept_part = write_media(library.partial_path(keep_final))
    (library_root / "Browsed").mkdir()
    async with SessionLocal() as db:
        db.add_all(
            [
                DownloadJob(anime_external_id=ANIME_ID, anime_title="A", source="animego", season=1, episode=1,
                            status="downloading", progress=40, bytes_done=10),
                DownloadJob(anime_external_id=ANIME_ID, anime_title="Keep", source="animevost", season=1, episode=2,
                            status="paused", progress=30, resumable=True, file_path=library.to_stored_path(keep_final)),
            ]
        )
        await db.commit()
    await DownloadManager()._recover()

    async with SessionLocal() as db:
        jobs = {j.episode: j for j in (await db.execute(select(DownloadJob))).scalars().all()}
    assert (jobs[1].status, jobs[1].progress) == ("queued", 0)
    assert (jobs[2].status, jobs[2].progress) == ("paused", 30)
    assert not orphan.exists() and kept_part.exists()
    assert not (library_root / "Browsed").exists() and not (library_root / "Old").exists()


async def test_scheduler_respects_concurrency_and_shutdown_requeues(db_reset, fake_registry, ffmpeg, no_poster):
    gate = asyncio.Event()
    ffmpeg["block"] = gate
    manager = DownloadManager()
    manager.set_concurrency(2)
    for number in (1, 2, 3):
        await enqueue(manager, episode=number)
    await manager.start()
    for _ in range(100):
        if len(manager.running_ids()) == 2:
            break
        await asyncio.sleep(0.02)
    assert len(manager.running_ids()) == 2
    await manager.stop()
    async with SessionLocal() as db:
        statuses = sorted(j.status for j in (await db.execute(select(DownloadJob))).scalars().all())
    assert statuses == ["queued", "queued", "queued"]


async def test_cancel_queued_and_retry_rules(db_reset, fake_registry):
    manager = DownloadManager()
    created, _ = await enqueue(manager)
    assert await manager.retry(created.id) is False  # only failed/cancelled can be retried
    assert await manager.cancel(created.id) is True
    assert (await job(created.id)).status == "cancelled"
    assert await manager.retry(created.id) is True
    assert (await job(created.id)).status == "queued"
    assert await manager.pause(created.id) is False  # HLS/unknown jobs are not resumable


async def test_progressive_download_resumes_with_range(db_reset, fake_registry, ffmpeg, no_poster, monkeypatch, library_root):
    payload = bytes(range(256)) * 64  # 16 KiB
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        start = int(request.headers.get("range", "bytes=0-").split("=")[1].split("-")[0])
        body = payload[start:]
        status = 206 if start else 200
        headers = {"content-length": str(len(body)), "content-type": "video/mp4"}
        if start:
            headers["content-range"] = f"bytes {start}-{len(payload) - 1}/{len(payload)}"
        return httpx.Response(status, headers=headers, stream=httpx.ByteStream(body))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(media_clients, "get", lambda _proxy: client)
    fake_registry.stream = registry_module.ResolvedVideo(type="mp4", quality=720, url="https://cdn.example.com/ep.mp4")

    final = library_root / "Fixture Anime" / "Season 1" / "Episode 01.mp4"
    write_media(library.partial_path(final), 0)
    library.partial_path(final).write_bytes(payload[:4096])
    manager = DownloadManager()
    created, _ = await enqueue(manager)
    async with SessionLocal() as db:
        row = await db.get(DownloadJob, created.id)
        row.resumable, row.file_path, row.source_url = True, library.to_stored_path(final), "https://cdn.example.com/ep.mp4"
        row.bytes_total = len(payload)
        await db.commit()
    await manager._process(created.id)

    assert (await job(created.id)).status == "completed"
    assert seen[0].headers["range"] == "bytes=4096-"
    assert final.read_bytes() == payload
