from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.common import anime_id_param, provider_failure
from backend.database.session import get_db
from backend.downloader.manager import download_manager
from backend.models import OPEN_DOWNLOAD_STATUSES, DownloadJob
from backend.providers import decode_external_id, get_registry
from backend.schemas import ApiMessage, DownloadCreateResponse, DownloadJobOut, DownloadRequest, SkippedDownload
from backend.services import library_index
from backend.services.settings import get_app_settings

router = APIRouter(prefix="/api/downloads")


@router.post("", response_model=DownloadCreateResponse)
async def create_downloads(body: DownloadRequest, db: AsyncSession = Depends(get_db)):
    anime_id = anime_id_param(body.anime_id)
    try:
        detail = await get_registry().get_anime(anime_id)
    except Exception as exc:  # noqa: BLE001
        provider_failure(exc, "Loading title")

    known = {e.ordinal: e for e in detail.episodes}
    if body.episodes:
        wanted = list(dict.fromkeys(body.episodes))
    elif body.episode is not None:
        wanted = [body.episode]
    else:
        wanted = list(known)
    missing = [n for n in wanted if n not in known]
    if missing:
        raise HTTPException(404, {"code": "not_found", "message": f"Episodes not found: {missing[:10]}"})
    if not wanted:
        raise HTTPException(400, {"code": "no_episodes", "message": "No episodes to download"})

    await library_index.upsert_title(
        db,
        anime_id=anime_id,
        source=detail.source,
        title=detail.title,
        poster=detail.poster,
        description=detail.description,
        year=detail.year,
    )
    await db.commit()

    settings = await get_app_settings(db)
    steam_deck = settings.steam_deck_optimize if body.steam_deck is None else body.steam_deck
    source, _ = decode_external_id(anime_id)
    jobs: list[DownloadJob] = []
    skipped: list[SkippedDownload] = []
    for number in wanted:
        job, reason = await download_manager.enqueue(
            anime_id=anime_id,
            anime_title=detail.title,
            source=source,
            season=body.season,
            episode=number,
            episode_title=known[number].title,
            voiceover=body.voiceover,
            steam_deck=steam_deck,
            quality=body.quality,
            replace=body.replace,
        )
        if job is not None:
            jobs.append(job)
        else:
            skipped.append(SkippedDownload(episode=number, reason=reason))  # type: ignore[arg-type]
    return DownloadCreateResponse(jobs=[DownloadJobOut.model_validate(j) for j in jobs], skipped=skipped)


@router.get("", response_model=list[DownloadJobOut])
async def list_downloads(
    status: Literal["all", "active", "finished"] = "all",
    limit: int = Query(300, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
):
    query = select(DownloadJob)
    if status == "active":
        query = query.where(DownloadJob.status.in_(OPEN_DOWNLOAD_STATUSES))
    elif status == "finished":
        query = query.where(DownloadJob.status.not_in(OPEN_DOWNLOAD_STATUSES))
    rows = (await db.execute(query.order_by(DownloadJob.id.desc()).limit(limit))).scalars().all()
    return rows


def _command(ok: bool, message: str, failure: str) -> ApiMessage:
    if not ok:
        raise HTTPException(409, {"code": "invalid_state", "message": failure})
    return ApiMessage(message=message)


@router.post("/{job_id}/cancel", response_model=ApiMessage)
async def cancel_download(job_id: int):
    return _command(await download_manager.cancel(job_id), "cancelled", "Job not found or already finished")


@router.post("/{job_id}/retry", response_model=ApiMessage)
async def retry_download(job_id: int):
    return _command(await download_manager.retry(job_id), "requeued", "Only failed or cancelled jobs can be retried")


@router.post("/{job_id}/pause", response_model=ApiMessage)
async def pause_download(job_id: int):
    return _command(
        await download_manager.pause(job_id), "paused", "Only active direct-file downloads support pausing"
    )


@router.post("/{job_id}/resume", response_model=ApiMessage)
async def resume_download(job_id: int):
    return _command(await download_manager.resume(job_id), "resumed", "Job is not paused")


@router.delete("/{job_id}", response_model=ApiMessage)
async def remove_download(job_id: int):
    return _command(await download_manager.remove(job_id), "removed", "Active jobs cannot be removed; cancel first")


@router.post("/clear", response_model=ApiMessage)
async def clear_finished():
    removed = await download_manager.clear_finished()
    return ApiMessage(message=f"removed {removed} finished jobs", detail={"removed": removed})
