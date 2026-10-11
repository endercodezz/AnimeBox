from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.common import library_id_param
from backend.database.session import get_db
from backend.models import AnimeTitle, LibraryEpisode
from backend.schemas import ApiMessage, LibraryAnimeOut, LibraryEpisodeOut, LibraryStats, RescanResult
from backend.services import library, library_index

router = APIRouter(prefix="/api/library")

mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/mp4", ".m4v")


@router.get("", response_model=list[LibraryAnimeOut])
async def list_library(db: AsyncSession = Depends(get_db)):
    return await library_index.list_library(db)


@router.get("/stats", response_model=LibraryStats)
async def library_stats(db: AsyncSession = Depends(get_db)):
    return await library_index.stats(db)


@router.get("/episodes", response_model=list[LibraryEpisodeOut])
async def library_episodes(id: str = Query(..., max_length=1024), db: AsyncSession = Depends(get_db)):
    return await library_index.library_episodes(db, library_id_param(id))


@router.get("/file/{episode_id}")
async def library_file(episode_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(LibraryEpisode, episode_id)
    path = library.resolve_stored_path(row.file_path) if row else None
    if path is None or not library.is_valid_media_file(path):
        raise HTTPException(404, {"code": "file_missing", "message": "The downloaded file is missing"})
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, content_disposition_type="inline")


@router.get("/poster")
async def library_poster(id: str = Query(..., max_length=1024), db: AsyncSession = Depends(get_db)):
    anime_id = library_id_param(id)
    title = (await db.execute(select(AnimeTitle).where(AnimeTitle.external_id == anime_id))).scalar_one_or_none()
    episodes = (
        await db.execute(select(LibraryEpisode).where(LibraryEpisode.anime_external_id == anime_id).limit(5))
    ).scalars().all()
    anime_dir = library_index.anime_dir_for(title, list(episodes))
    poster = library.poster_file(anime_dir) if anime_dir else None
    if poster is None:
        raise HTTPException(404, {"code": "poster_missing", "message": "Poster not found"})
    with poster.open("rb") as handle:
        detected = library.image_type(handle.read(16))
    return FileResponse(
        poster,
        media_type=detected[0] if detected else mimetypes.guess_type(poster.name)[0] or "image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.delete("/anime", response_model=ApiMessage)
async def delete_anime(id: str = Query(..., max_length=1024), db: AsyncSession = Depends(get_db)):
    deleted = await library_index.delete_anime(db, library_id_param(id))
    if not deleted:
        exists = (
            await db.execute(select(LibraryEpisode.id).where(LibraryEpisode.anime_external_id == library_id_param(id)))
        ).first()
        if exists is None:
            raise HTTPException(404, {"code": "not_found", "message": "Title is not in the library"})
    return ApiMessage(message=f"deleted {deleted} files", detail={"deleted": deleted})


@router.delete("/episodes/{episode_id}", response_model=ApiMessage)
async def delete_episode(episode_id: int, db: AsyncSession = Depends(get_db)):
    if not await library_index.delete_episode(db, episode_id):
        raise HTTPException(404, {"code": "not_found", "message": "Episode is not in the library"})
    return ApiMessage(message="deleted")


@router.post("/rescan", response_model=RescanResult)
async def rescan(db: AsyncSession = Depends(get_db)):
    return await library_index.rescan(db)
