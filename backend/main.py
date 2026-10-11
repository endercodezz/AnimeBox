from __future__ import annotations

import asyncio
import logging
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend import __version__
from backend.api import router as api_router
from backend.config import PACKAGE_DIR, get_settings
from backend.database.session import SessionLocal, init_db
from backend.downloader.manager import download_manager
from backend.player.proxy import router as media_router

settings = get_settings()


class _RedactSecrets(logging.Filter):
    """Mask credentials in proxy URLs and signed query parameters before they reach logs."""

    _patterns = (
        (re.compile(r"(\w+://)[^/\s:@]+:[^/\s@]+@"), r"\1***:***@"),
        (re.compile(r"((?:token|sig|signature|key|hash)=)[^&\s]+", re.IGNORECASE), r"\1***"),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        redacted = message
        for pattern, replacement in self._patterns:
            redacted = pattern.sub(replacement, redacted)
        if redacted != message:
            record.msg, record.args = redacted, ()
        return True


def configure_logging(level: str | None = None) -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=getattr(logging, (level or settings.log_level).upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
    for handler in root.handlers:
        if not any(isinstance(f, _RedactSecrets) for f in handler.filters):
            handler.addFilter(_RedactSecrets())
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anicli-api").setLevel(logging.ERROR)


configure_logging()
logger = logging.getLogger("animebox")

FRONTEND_DIST = PACKAGE_DIR / "frontend" / "dist"
SHUTDOWN_TOKEN = secrets.token_urlsafe(32)
_shutdown_event: asyncio.Event | None = None
_shutdown_enabled = False


def enable_shutdown() -> None:
    global _shutdown_enabled
    _shutdown_enabled = True


def shutdown_enabled() -> bool:
    return _shutdown_enabled


def request_shutdown(token: str) -> bool:
    if not _shutdown_enabled or not secrets.compare_digest(token, SHUTDOWN_TOKEN):
        return False
    if _shutdown_event is not None:
        _shutdown_event.set()
    return True


async def wait_for_shutdown() -> None:
    while _shutdown_event is None:
        await asyncio.sleep(0.05)
    await _shutdown_event.wait()


def _frontend_index() -> Path:
    return FRONTEND_DIST / "index.html"


def _frontend_ready() -> bool:
    return _frontend_index().is_file()


def allowed_hosts() -> list[str]:
    hosts = {"127.0.0.1", "localhost", "::1", "[::1]", *settings.allowed_hosts}
    if settings.host not in ("0.0.0.0", "::"):
        hosts.add(settings.host)
    return sorted(hosts)


async def _apply_saved_settings() -> None:
    from backend.services.settings import apply_runtime, get_app_settings

    async with SessionLocal() as db:
        await apply_runtime(await get_app_settings(db), network_changed=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _shutdown_event
    _shutdown_event = asyncio.Event()
    await init_db()
    await _apply_saved_settings()
    download_manager.local_base_url = f"http://127.0.0.1:{settings.port}"
    await download_manager.start()
    if _frontend_ready():
        logger.info("AnimeBox %s started — library=%s", __version__, settings.library_path)
    else:
        logger.warning(
            "AnimeBox %s started — library=%s, but frontend/dist is missing. "
            "Build the UI (scripts/run.* or: cd frontend && npm run build) or open Vite on :5173.",
            __version__,
            settings.library_path,
        )
    try:
        yield
    finally:
        await download_manager.stop()
        from backend.providers import get_registry
        from backend.providers.http import media_clients

        await get_registry().aclose()
        await media_clients.aclose()
        # Closing the last connection checkpoints the WAL into animebox.db, so copying
        # only the .db file (e.g. when moving a portable folder) never loses recent data.
        from backend.database.session import engine

        await engine.dispose()
        _shutdown_event = None


app = FastAPI(title="AnimeBox", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Range", "X-AnimeBox-Token"],
)
# Rejects requests whose Host is not this machine: blocks DNS-rebinding pages from driving the API.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())
app.include_router(api_router)
app.include_router(media_router)

_assets_dir = FRONTEND_DIST / "assets"
if _assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")


async def _spa_response(full_path: str = "") -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(404, {"code": "not_found", "message": "Unknown API endpoint"})
    if not _frontend_ready():
        raise HTTPException(
            status_code=503,
            detail="Frontend not built. Run scripts/run.ps1 / scripts/run.sh (or: cd frontend && npm run build).",
        )
    if full_path:
        candidate = (FRONTEND_DIST / full_path).resolve()
        try:
            candidate.relative_to(FRONTEND_DIST.resolve())
        except ValueError as exc:
            raise HTTPException(404, "Not Found") from exc
        if candidate.is_file():
            return FileResponse(candidate)
    return FileResponse(_frontend_index(), headers={"Cache-Control": "no-cache"})


@app.get("/", include_in_schema=False)
async def spa_root():
    return await _spa_response("")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa(full_path: str):
    # API and media routers are registered first; this only catches UI routes.
    return await _spa_response(full_path)


def run() -> None:
    import uvicorn

    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
