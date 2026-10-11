from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.config import get_settings

logger = logging.getLogger("animebox.database")


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record) -> None:  # pragma: no cover - driver hook
    if not settings.database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    # WAL lets the UI read while downloads write progress; busy_timeout avoids "database is locked".
    if settings.database_file is not None:
        cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from backend import models  # noqa: F401
    from backend.database import migrations

    db_file = settings.database_file
    if db_file is not None:
        ctx = migrations.MigrationContext(library_root=settings.library_path)
        before, after, backup = await asyncio.to_thread(migrations.upgrade, db_file, ctx)
        if backup is not None:
            logger.info("Database upgraded v%s -> v%s (backup: %s)", before, after, backup)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if db_file is not None:
        await asyncio.to_thread(migrations.stamp_latest, db_file)
