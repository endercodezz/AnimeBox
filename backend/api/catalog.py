"""Search, title details, voiceovers, stream resolution, provider diagnostics."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.common import anime_id_param, provider_failure
from backend.config import get_settings
from backend.database.session import get_db
from backend.player.sessions import media_sessions
from backend.providers import get_registry
from backend.providers.catalog import SOURCE_BY_ID, SOURCES
from backend.providers.errors import ProviderError, ProviderUnavailable
from backend.schemas import (
    AnimeDetail,
    ProviderInfo,
    SearchResponse,
    StageOut,
    StreamResolveRequest,
    StreamResolveResponse,
    VoiceoverOption,
)
from backend.services import library_index

router = APIRouter(prefix="/api")
CHECK_TIMEOUT = 150


def _provider_info(source: str) -> ProviderInfo:
    registry = get_registry()
    spec = SOURCE_BY_ID[source]
    health = registry.health.get(source)
    return ProviderInfo(
        id=spec.id,
        label=spec.label,
        stable=spec.stable,
        enabled=spec.id in registry.enabled_sources,
        is_default=spec.id == registry.default_source,
        note=spec.note,
        status=health.status,  # type: ignore[arg-type]
        stages={name: StageOut(**vars(result)) for name, result in health.stages.items()},
        last_check_at=health.last_check_at,
    )


@router.get("/providers", response_model=list[ProviderInfo])
async def list_providers():
    return [_provider_info(spec.id) for spec in get_registry().ordered_sources()]


@router.post("/providers/{source}/check", response_model=ProviderInfo)
async def check_provider(source: str):
    if source not in SOURCE_BY_ID:
        raise HTTPException(404, {"code": "unknown_source", "message": f"Unknown source '{source}'"})
    try:
        await asyncio.wait_for(get_registry().check(source), timeout=CHECK_TIMEOUT)
    except TimeoutError:
        pass  # stage timeouts were recorded individually
    return _provider_info(source)


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, max_length=200),
    source: str | None = Query(None, max_length=64),
):
    registry = get_registry()
    if source and source not in SOURCE_BY_ID:
        raise HTTPException(400, {"code": "unknown_source", "message": f"Unknown source '{source}'"})
    try:
        return await registry.search(q, sources=[source] if source else None)
    except ProviderUnavailable as exc:
        provider_failure(exc, "Search")


@router.get("/anime", response_model=AnimeDetail)
async def anime_detail(id: str = Query(..., min_length=3, max_length=1024), db: AsyncSession = Depends(get_db)):
    anime_id = anime_id_param(id)
    registry = get_registry()
    try:
        detail = await registry.get_anime(anime_id)
    except Exception as exc:  # noqa: BLE001
        provider_failure(exc, "Loading title")
    # Catalog metadata only. Library membership is decided by downloaded files, never here.
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
    return detail


@router.get("/anime/voiceovers", response_model=list[VoiceoverOption])
async def episode_voiceovers(
    id: str = Query(..., min_length=3, max_length=1024),
    episode: int = Query(..., ge=0, le=100000),
):
    anime_id = anime_id_param(id)
    try:
        return await get_registry().get_episode_voiceovers(anime_id, episode)
    except Exception as exc:  # noqa: BLE001
        provider_failure(exc, "Loading voiceovers")


@router.post("/stream/resolve", response_model=StreamResolveResponse)
async def resolve_stream(body: StreamResolveRequest):
    anime_id = anime_id_param(body.anime_id)
    registry = get_registry()
    try:
        stream = await registry.resolve_stream(
            anime_id,
            body.episode,
            voiceover=body.voiceover,
            quality=body.quality,
            player=body.player,
            purpose="play",
            refresh=body.refresh,
        )
    except ProviderError as exc:
        provider_failure(exc, "Resolving stream")
    except Exception as exc:  # noqa: BLE001
        provider_failure(exc, "Resolving stream")
    session = media_sessions.create(stream.video.headers, registry.proxy, ttl=get_settings().media_session_ttl)
    return StreamResolveResponse(
        anime_title=stream.anime_title,
        episode=stream.episode,
        voiceover=stream.voiceover,
        player=stream.player,
        type=stream.video.type,
        quality=stream.video.quality,
        qualities=stream.qualities,
        url=session.url_for(stream.video.url),
        browser_playable=stream.browser_playable,
        expires_at=session.expires_at,
    )


__all__ = ["router", "SOURCES"]
