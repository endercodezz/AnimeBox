"""Playback progress, watch history and the home screen feed."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.common import library_id_param
from backend.database.session import get_db
from backend.models import AnimeTitle, LibraryEpisode, WatchHistory
from backend.schemas import ApiMessage, HomeOut, ProgressUpdate, WatchHistoryOut
from backend.services import library, library_index

router = APIRouter(prefix="/api")
COMPLETED_RATIO = 0.9


def _completed(progress: float, duration: float | None) -> bool:
    return bool(duration and duration > 0 and progress / duration >= COMPLETED_RATIO)


async def _decorate(db: AsyncSession, rows: list[WatchHistory]) -> list[WatchHistoryOut]:
    ids = list({row.anime_external_id for row in rows})
    titles = {}
    if ids:
        titles = {
            t.external_id: t
            for t in (await db.execute(select(AnimeTitle).where(AnimeTitle.external_id.in_(ids)))).scalars().all()
        }
    out: list[WatchHistoryOut] = []
    local_poster_cache: dict[str, bool] = {}
    for row in rows:
        item = WatchHistoryOut.model_validate(row)
        item.completed = _completed(row.progress_seconds, row.duration_seconds)
        title = titles.get(row.anime_external_id)
        if row.anime_external_id not in local_poster_cache:
            folder = library.resolve_stored_path(title.folder_path) if title and title.folder_path else None
            local_poster_cache[row.anime_external_id] = bool(folder and library.poster_file(folder))
        if local_poster_cache[row.anime_external_id]:
            item.poster = library_index.poster_endpoint(row.anime_external_id)
        elif not item.poster and title:
            item.poster = title.poster
        out.append(item)
    return out


@router.post("/progress", response_model=WatchHistoryOut)
async def save_progress(body: ProgressUpdate, db: AsyncSession = Depends(get_db)):
    anime_id = library_id_param(body.anime_id) if body.anime_id else None
    local_id = body.local_episode_id
    if local_id:
        ep = await db.get(LibraryEpisode, local_id)
        if ep is None:
            local_id = None
        else:
            ep.progress_seconds = body.progress_seconds
            if body.duration_seconds:
                ep.duration_seconds = body.duration_seconds
            if _completed(body.progress_seconds, body.duration_seconds):
                ep.completed = True
            anime_id = anime_id or ep.anime_external_id
    if not anime_id:
        raise HTTPException(400, {"code": "missing_anime_id", "message": "anime_id required"})

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
            season=body.season,
            episode=body.episode,
        )
        db.add(row)
    row.progress_seconds = body.progress_seconds
    if body.duration_seconds:
        row.duration_seconds = body.duration_seconds
    row.local_episode_id = local_id or row.local_episode_id
    if body.anime_title:
        row.anime_title = body.anime_title
    if body.poster and not body.poster.startswith("/api/"):
        row.poster = body.poster
    if body.voiceover:
        row.voiceover = body.voiceover
    await db.commit()
    await db.refresh(row)
    return (await _decorate(db, [row]))[0]


@router.get("/history", response_model=list[WatchHistoryOut])
async def history(limit: int = Query(60, ge=1, le=500), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(WatchHistory).order_by(WatchHistory.updated_at.desc(), WatchHistory.id.desc()).limit(limit))
    ).scalars().all()
    return await _decorate(db, list(rows))


@router.get("/history/anime", response_model=list[WatchHistoryOut])
async def anime_history(id: str = Query(..., max_length=1024), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(WatchHistory)
            .where(WatchHistory.anime_external_id == library_id_param(id))
            .order_by(WatchHistory.season, WatchHistory.episode)
        )
    ).scalars().all()
    return await _decorate(db, list(rows))


@router.delete("/history/{entry_id}", response_model=ApiMessage)
async def delete_history_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(WatchHistory, entry_id)
    if row is None:
        raise HTTPException(404, {"code": "not_found", "message": "History entry not found"})
    await db.delete(row)
    await db.commit()
    return ApiMessage(message="deleted")


@router.delete("/history", response_model=ApiMessage)
async def clear_history(db: AsyncSession = Depends(get_db)):
    result = await db.execute(delete(WatchHistory))
    await db.commit()
    return ApiMessage(message="cleared", detail={"deleted": result.rowcount})


@router.get("/home", response_model=HomeOut)
async def home(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(WatchHistory).order_by(WatchHistory.updated_at.desc(), WatchHistory.id.desc()).limit(200))
    ).scalars().all()
    latest_per_anime: list[WatchHistory] = []
    seen: set[str] = set()
    for row in rows:
        if row.anime_external_id in seen:
            continue
        seen.add(row.anime_external_id)
        latest_per_anime.append(row)
    decorated = await _decorate(db, latest_per_anime[:24])
    continue_watching = [item for item in decorated if not item.completed and item.progress_seconds >= 5][:12]
    library_items = await library_index.list_library(db)
    return HomeOut(
        continue_watching=continue_watching,
        recently_watched=decorated[:12],
        recently_downloaded=library_items[:12],
    )
