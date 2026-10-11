"""Health, session/shutdown, settings and diagnostics."""

from __future__ import annotations

import asyncio
import platform
import sys

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend import __version__
from backend.config import get_settings
from backend.database.session import get_db
from backend.downloader.manager import download_manager
from backend.player.sessions import media_sessions
from backend.providers.http import redact_proxy
from backend.schemas import ApiMessage, AppSettingsOut, AppSettingsUpdate
from backend.services import ffmpeg_tools, library
from backend.services.settings import get_app_settings, update_app_settings

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"status": "ok", "version": __version__}


@router.get("/session")
async def session():
    from backend.main import SHUTDOWN_TOKEN, shutdown_enabled

    return {"shutdown_token": SHUTDOWN_TOKEN, "shutdown_enabled": shutdown_enabled(), "version": __version__}


@router.post("/shutdown", response_model=ApiMessage)
async def shutdown(x_animebox_token: str = Header(...)):
    from backend.main import request_shutdown

    if not request_shutdown(x_animebox_token):
        raise HTTPException(403, {"code": "invalid_token", "message": "Invalid shutdown token"})
    return ApiMessage(message="AnimeBox is shutting down")


@router.get("/settings", response_model=AppSettingsOut)
async def settings_get(db: AsyncSession = Depends(get_db)):
    return await get_app_settings(db)


@router.put("/settings", response_model=AppSettingsOut)
async def settings_put(body: AppSettingsUpdate, db: AsyncSession = Depends(get_db)):
    try:
        return await update_app_settings(db, body)
    except ValueError as exc:
        raise HTTPException(422, {"code": "invalid_settings", "message": str(exc)}) from exc


async def _ffmpeg_version(path: str | None) -> str | None:
    if not path:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            path, "-version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return out.decode("utf-8", errors="ignore").splitlines()[0] if out else None
    except (OSError, TimeoutError):
        return None


@router.get("/diagnostics")
async def diagnostics(db: AsyncSession = Depends(get_db)):
    cfg = get_settings()
    app_settings = await get_app_settings(db)
    ffmpeg = ffmpeg_tools.ffmpeg_path()
    usage = library.disk_usage(cfg.library_path)
    return {
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "frozen": bool(getattr(sys, "frozen", False)),
        "ffmpeg": {"path": ffmpeg, "version": await _ffmpeg_version(ffmpeg)},
        "paths": {
            "library": str(cfg.library_path),
            "data": str(cfg.data_path),
            "database": str(cfg.database_file) if cfg.database_file else cfg.database_url,
        },
        "disk": usage,
        "network": {"proxy": redact_proxy(app_settings.http_proxy)},
        "runtime": {
            "media_sessions": len(media_sessions),
            "running_downloads": len(download_manager.running_ids()),
            "max_concurrent_downloads": app_settings.max_concurrent_downloads,
        },
    }
