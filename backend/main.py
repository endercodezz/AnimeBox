from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router as api_router
from backend.config import PACKAGE_DIR, get_settings
from backend.database.session import init_db
from backend.downloader.manager import download_manager
from backend.player.proxy import router as proxy_router

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("animebox")

FRONTEND_DIST = PACKAGE_DIR / "frontend" / "dist"


def _frontend_index() -> Path:
    return FRONTEND_DIST / "index.html"


def _frontend_ready() -> bool:
    return _frontend_index().is_file()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    await download_manager.start()
    if _frontend_ready():
        logger.info("AnimeBox started — library=%s ui=%s", settings.library_path, FRONTEND_DIST)
    else:
        logger.warning(
            "AnimeBox started — library=%s, but frontend/dist is missing. "
            "Build UI (scripts/run.ps1 / npm run build) or open Vite on :5173.",
            settings.library_path,
        )
    yield
    await download_manager.stop()


app = FastAPI(title="AnimeBox", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins + [f"http://{settings.host}:{settings.port}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
app.include_router(proxy_router)

_assets_dir = FRONTEND_DIST / "assets"
if _assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")


async def _spa_response(full_path: str = "") -> FileResponse:
    if not _frontend_ready():
        raise HTTPException(
            status_code=503,
            detail="Frontend not built. Run scripts/run.ps1 (or: cd frontend && npm run build).",
        )
    if full_path:
        candidate = (FRONTEND_DIST / full_path).resolve()
        try:
            candidate.relative_to(FRONTEND_DIST.resolve())
        except ValueError as exc:
            raise HTTPException(404, "Not Found") from exc
        if candidate.is_file():
            return FileResponse(candidate)
    return FileResponse(_frontend_index())


@app.get("/")
async def spa_root():
    return await _spa_response("")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    # API / proxy are registered above; this only catches UI routes.
    return await _spa_response(full_path)


def run() -> None:
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
