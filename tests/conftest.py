"""Test isolation: every backend path points into a throwaway directory.

Environment variables are set before ``backend`` is imported, because settings
and the SQLAlchemy engine are created at import time.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_ROOT = Path(tempfile.mkdtemp(prefix="animebox-tests-"))
os.environ["DATA_PATH"] = str(_ROOT / "data")
os.environ["LIBRARY_PATH"] = str(_ROOT / "library")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_ROOT / 'data' / 'animebox.db').as_posix()}"
os.environ["HTTP_PROXY"] = ""
os.environ.setdefault("LOG_LEVEL", "WARNING")

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from backend.config import get_settings  # noqa: E402


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def library_root(settings) -> Path:
    return settings.library_path


@pytest_asyncio.fixture
async def db_reset(settings):
    """Fresh schema and empty library for each test that touches state."""
    from backend.database.session import Base, engine, init_db
    from backend.player.sessions import media_sessions

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    if settings.library_path.exists():
        shutil.rmtree(settings.library_path)
    settings.library_path.mkdir(parents=True, exist_ok=True)
    await init_db()
    media_sessions._sessions.clear()
    snapshot = settings.model_dump()
    yield
    for key, value in snapshot.items():
        setattr(settings, key, value)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_reset):
    """API client against the real app routers (lifespan not started)."""
    from fastapi import FastAPI

    from backend.api import router
    from backend.player.proxy import router as media_router

    app = FastAPI()
    app.include_router(router)
    app.include_router(media_router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
        yield http


def write_media(path: Path, size: int = 4096) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * size)
    return path


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    shutil.rmtree(_ROOT, ignore_errors=True)
