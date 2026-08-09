from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.session import get_db
from backend.downloader.manager import download_manager
from backend.models import AnimeTitle, DownloadJob, LibraryEpisode, WatchHistory
from backend.player.proxy import store_headers
from backend.providers import decode_external_id, get_registry
from backend.schemas import (
    AnimeDetail,
    ApiMessage,
    AppSettingsOut,
    AppSettingsUpdate,
    DownloadJobOut,
    DownloadRequest,
    EpisodeInfo,
    LibraryAnimeOut,
    LibraryEpisodeOut,
    ProgressUpdate,
    SearchResult,
    SourceInfo,
    StreamResolveRequest,
    StreamResolveResponse,
    VoiceoverOption,
    WatchHistoryOut,
)
from backend.services import library
from backend.services.settings import get_app_settings, update_app_settings

logger = logging.getLogger("animebox.api")
router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/session")
async def session():
    from backend.main import SHUTDOWN_TOKEN, shutdown_enabled

    return {"shutdown_token": SHUTDOWN_TOKEN, "shutdown_enabled": shutdown_enabled()}


@router.post("/shutdown", response_model=ApiMessage)
async def shutdown(x_animebox_token: str = Header(...)):
    from backend.main import request_shutdown

    if not request_shutdown(x_animebox_token):
        raise HTTPException(403, "Invalid shutdown token")
    return ApiMessage(message="AnimeBox is shutting down")


@router.get("/sources", response_model=list[SourceInfo])
async def list_sources():
    reg = get_registry()
    return [SourceInfo(id=s, label=s) for s in reg.available_sources()]


@router.get("/search", response_model=list[SearchResult])
async def search(
    q: str = Query(..., min_length=1),
    source: str | None = None,
):
    reg = get_registry()
    sources = [source] if source else None
    try:
        return await reg.search(q, sources=sources)
    except Exception as exc:
        logger.exception("search failed")
        raise HTTPException(502, f"Search failed: {exc}") from exc


@router.get("/anime/{anime_id:path}", response_model=AnimeDetail)
async def anime_detail(anime_id: str, voiceovers: bool = False, db: AsyncSession = Depends(get_db)):
    reg = get_registry()
    try:
        detail = await reg.get_anime(anime_id, include_voiceovers=voiceovers)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        logger.exception("anime detail failed")
        raise HTTPException(502, f"Failed to load anime: {exc}") from exc

    # Upsert title metadata
    row = (await db.execute(select(AnimeTitle).where(AnimeTitle.external_id == anime_id))).scalar_one_or_none()
    if row is None:
        db.add(
            AnimeTitle(
                external_id=anime_id,
                source=detail.source,
                title=detail.title,
                poster=detail.poster,
                description=detail.description,
                year=detail.year,
                folder_path=str(library.anime_dir(detail.title)),
            )
        )
    else:
        row.title = detail.title
        row.poster = detail.poster
        row.description = detail.description
        row.year = detail.year
    await db.commit()
    return detail


@router.get("/anime/{anime_id:path}/episodes/{episode}/voiceovers", response_model=list[VoiceoverOption])
async def episode_voiceovers(anime_id: str, episode: int):
    reg = get_registry()
    try:
        return await reg.get_episode_voiceovers(anime_id, episode)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/stream/resolve", response_model=StreamResolveResponse)
async def resolve_stream(body: StreamResolveRequest):
    reg = get_registry()
    try:
        stream = await reg.resolve_stream(
            body.anime_id,
            body.episode,
            voiceover=body.voiceover,
            quality=body.quality,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        logger.exception("resolve stream failed")
        raise HTTPException(502, str(exc)) from exc

    hid = store_headers(stream.video.headers) if stream.video.headers else None
    from urllib.parse import quote

    proxy_url = f"/api/proxy/stream?url={quote(stream.video.url, safe='')}"
    if hid:
        proxy_url += f"&hid={hid}"
    return StreamResolveResponse(
        anime_title=stream.anime_title,
        episode=stream.episode,
        voiceover=stream.voiceover,
        video=stream.video,
        proxy_url=proxy_url,
    )


@router.post("/downloads", response_model=list[DownloadJobOut])
async def create_downloads(body: DownloadRequest, db: AsyncSession = Depends(get_db)):
    reg = get_registry()
    try:
        detail = await reg.get_anime(body.anime_id)
    except Exception as exc:
        raise HTTPException(404, str(exc)) from exc

    source, _ = decode_external_id(body.anime_id)
    episodes = body.episodes or ([body.episode] if body.episode is not None else [e.ordinal for e in detail.episodes])
    if not episodes:
        raise HTTPException(400, "No episodes to download")

    settings = await get_app_settings(db)
    steam = body.steam_deck or settings.steam_deck_optimize
    jobs: list[DownloadJob] = []
    for ep_num in episodes:
        ep_meta = next((e for e in detail.episodes if e.ordinal == ep_num), None)
        job = await download_manager.enqueue(
            anime_id=body.anime_id,
            anime_title=detail.title,
            source=source,
            season=body.season,
            episode=ep_num,
            episode_title=ep_meta.title if ep_meta else f"Episode {ep_num}",
            voiceover=body.voiceover,
            steam_deck=steam,
        )
        jobs.append(job)
    return jobs


@router.get("/downloads", response_model=list[DownloadJobOut])
async def list_downloads(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(DownloadJob).order_by(DownloadJob.id.desc()).limit(200))).scalars().all()
    return rows


@router.post("/downloads/{job_id}/cancel", response_model=ApiMessage)
async def cancel_download(job_id: int):
    ok = await download_manager.cancel(job_id)
    if not ok:
        raise HTTPException(404, "Job not found or not cancellable")
    return ApiMessage(message="cancelled")


@router.post("/downloads/{job_id}/retry", response_model=ApiMessage)
async def retry_download(job_id: int):
    ok = await download_manager.retry(job_id)
    if not ok:
        raise HTTPException(404, "Job not found")
    return ApiMessage(message="requeued")


@router.get("/library/file/{episode_id}")
async def library_file(episode_id: int, db: AsyncSession = Depends(get_db)):
    ep = await db.get(LibraryEpisode, episode_id)
    if not ep or not Path(ep.file_path).exists():
        raise HTTPException(404, "File not found")
    path = Path(ep.file_path)
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, content_disposition_type="inline")


@router.get("/library/{anime_id:path}/poster")
async def library_poster(anime_id: str, db: AsyncSession = Depends(get_db)):
    title = (await db.execute(select(AnimeTitle).where(AnimeTitle.external_id == anime_id))).scalar_one_or_none()
    candidates: list[Path] = []
    if title and title.folder_path:
        candidates.append(Path(title.folder_path) / "poster.jpg")
    first = (
        await db.execute(
            select(LibraryEpisode).where(LibraryEpisode.anime_external_id == anime_id).limit(1)
        )
    ).scalar_one_or_none()
    if first:
        candidates.append(Path(first.file_path).parent.parent / "poster.jpg")
    poster = next((path for path in candidates if path.is_file()), None)
    if not poster:
        raise HTTPException(404, "Poster not found")
    return FileResponse(poster, media_type=mimetypes.guess_type(poster.name)[0] or "image/jpeg")


@router.get("/library", response_model=list[LibraryAnimeOut])
async def list_library(db: AsyncSession = Depends(get_db)):
    titles = (await db.execute(select(AnimeTitle).order_by(AnimeTitle.updated_at.desc()))).scalars().all()
    # Also include titles that only exist via downloaded episodes
    ep_ids = (
        await db.execute(select(LibraryEpisode.anime_external_id).distinct())
    ).scalars().all()
    known = {t.external_id for t in titles}
    out: list[LibraryAnimeOut] = []
    for t in titles:
        count = (
            await db.execute(
                select(func.count()).select_from(LibraryEpisode).where(LibraryEpisode.anime_external_id == t.external_id)
            )
        ).scalar_one()
        if count == 0 and t.folder_path and not Path(t.folder_path).exists():
            continue
        out.append(
            LibraryAnimeOut(
                id=t.external_id,
                title=t.title,
                poster=f"/api/library/{quote(t.external_id, safe='')}/poster"
                if t.folder_path and (Path(t.folder_path) / "poster.jpg").is_file()
                else t.poster,
                description=t.description,
                year=t.year,
                source=t.source,
                episode_count=count,
                folder_path=t.folder_path,
            )
        )
    for eid in ep_ids:
        if eid in known:
            continue
        count = (
            await db.execute(
                select(func.count()).select_from(LibraryEpisode).where(LibraryEpisode.anime_external_id == eid)
            )
        ).scalar_one()
        first = (
            await db.execute(select(LibraryEpisode).where(LibraryEpisode.anime_external_id == eid).limit(1))
        ).scalar_one()
        out.append(
            LibraryAnimeOut(
                id=eid,
                title=Path(first.file_path).parts[-3] if len(Path(first.file_path).parts) >= 3 else eid,
                poster=None,
                description=None,
                year=None,
                source=decode_external_id(eid)[0] if ":" in eid else "local",
                episode_count=count,
                folder_path=str(Path(first.file_path).parent.parent),
            )
        )
    return out


@router.get("/library/{anime_id:path}/episodes", response_model=list[LibraryEpisodeOut])
async def library_episodes(anime_id: str, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(LibraryEpisode)
            .where(LibraryEpisode.anime_external_id == anime_id)
            .order_by(LibraryEpisode.season, LibraryEpisode.episode)
        )
    ).scalars().all()
    return rows


@router.post("/progress", response_model=WatchHistoryOut)
async def save_progress(body: ProgressUpdate, db: AsyncSession = Depends(get_db)):
    anime_id = body.anime_id
    if body.local_episode_id:
        ep = await db.get(LibraryEpisode, body.local_episode_id)
        if ep:
            ep.progress_seconds = body.progress_seconds
            ep.duration_seconds = body.duration_seconds
            if body.duration_seconds and body.progress_seconds / body.duration_seconds > 0.9:
                ep.completed = True
            anime_id = anime_id or ep.anime_external_id

    if not anime_id:
        raise HTTPException(400, "anime_id required")

    row = (
        await db.execute(
            select(WatchHistory).where(
                WatchHistory.anime_external_id == anime_id,
                WatchHistory.season == body.season,
                WatchHistory.episode == body.episode,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = WatchHistory(
            anime_external_id=anime_id,
            anime_title=body.anime_title or anime_id,
            poster=body.poster,
            season=body.season,
            episode=body.episode,
            progress_seconds=body.progress_seconds,
            duration_seconds=body.duration_seconds,
            local_episode_id=body.local_episode_id,
        )
        db.add(row)
    else:
        row.progress_seconds = body.progress_seconds
        row.duration_seconds = body.duration_seconds
        row.local_episode_id = body.local_episode_id or row.local_episode_id
        if body.anime_title:
            row.anime_title = body.anime_title
        if body.poster:
            row.poster = body.poster
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/history", response_model=list[WatchHistoryOut])
async def history(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(WatchHistory).order_by(WatchHistory.updated_at.desc()).limit(50))).scalars().all()
    out: list[WatchHistoryOut] = []
    for row in rows:
        item = WatchHistoryOut.model_validate(row)
        title = (
            await db.execute(select(AnimeTitle).where(AnimeTitle.external_id == row.anime_external_id))
        ).scalar_one_or_none()
        if title and title.folder_path and (Path(title.folder_path) / "poster.jpg").is_file():
            item.poster = f"/api/library/{quote(row.anime_external_id, safe='')}/poster"
        out.append(item)
    return out


@router.get("/settings", response_model=AppSettingsOut)
async def settings_get(db: AsyncSession = Depends(get_db)):
    return await get_app_settings(db)


@router.put("/settings", response_model=AppSettingsOut)
async def settings_put(body: AppSettingsUpdate, db: AsyncSession = Depends(get_db)):
    return await update_app_settings(db, body)
