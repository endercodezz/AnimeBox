"""SQLite schema.

Separation of concerns (2.0):

- ``anime_titles``      catalog metadata cache. Browsing writes here; it never implies offline content.
- ``library_episodes``  downloaded, validated media files. The offline library is derived from this table only.
- ``download_jobs``     durable download queue and history.
- ``watch_history``     playback progress for online and offline viewing.
- ``app_settings``      user preferences.

Schema changes must ship with a step in ``backend/database/migrations.py``.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base


class DownloadStatus(StrEnum):
    queued = "queued"
    resolving = "resolving"
    downloading = "downloading"
    processing = "processing"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


ACTIVE_DOWNLOAD_STATUSES = (
    DownloadStatus.queued.value,
    DownloadStatus.resolving.value,
    DownloadStatus.downloading.value,
    DownloadStatus.processing.value,
)
OPEN_DOWNLOAD_STATUSES = (*ACTIVE_DOWNLOAD_STATUSES, DownloadStatus.paused.value)


class AnimeTitle(Base):
    __tablename__ = "anime_titles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512))
    poster: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Set only once content has been downloaded into the library.
    folder_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LibraryEpisode(Base):
    __tablename__ = "library_episodes"
    __table_args__ = (
        UniqueConstraint("anime_external_id", "season", "episode", name="ux_library_episodes_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anime_external_id: Mapped[str] = mapped_column(String(512), index=True)
    season: Mapped[int] = mapped_column(Integer, default=1)
    episode: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    voiceover: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Relative to the library root when stored inside it; absolute otherwise.
    file_path: Mapped[str] = mapped_column(String(1024))
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    progress_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class DownloadJob(Base):
    __tablename__ = "download_jobs"
    __table_args__ = (Index("ix_download_jobs_episode_key", "anime_external_id", "season", "episode"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anime_external_id: Mapped[str] = mapped_column(String(512), index=True)
    anime_title: Mapped[str] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(64))
    season: Mapped[int] = mapped_column(Integer, default=1)
    episode: Mapped[int] = mapped_column(Integer)
    episode_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    voiceover: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=DownloadStatus.queued.value, index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    steam_deck: Mapped[bool] = mapped_column(Boolean, default=False)
    quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    player_host: Mapped[str | None] = mapped_column(String(256), nullable=True)
    bytes_done: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    bytes_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    speed_bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    resumable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WatchHistory(Base):
    __tablename__ = "watch_history"
    __table_args__ = (
        UniqueConstraint("anime_external_id", "season", "episode", name="ux_watch_history_key"),
        Index("ix_watch_history_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anime_external_id: Mapped[str] = mapped_column(String(512), index=True)
    anime_title: Mapped[str] = mapped_column(String(512))
    poster: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    season: Mapped[int] = mapped_column(Integer, default=1)
    episode: Mapped[int] = mapped_column(Integer)
    voiceover: Mapped[str | None] = mapped_column(String(256), nullable=True)
    progress_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    local_episode_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
