"""Versioned, repeatable SQLite migrations.

The schema version lives in ``PRAGMA user_version``. AnimeBox 1.x databases
were created by ``create_all`` and report version 0.

Rules:

- an existing database is copied to ``<data>/backups/`` before any step runs;
- all steps of one upgrade run in a single transaction (all-or-nothing);
- every step is idempotent: it inspects the current schema/data before acting,
  so re-running it after an interrupted upgrade is safe;
- user data is never discarded. Duplicate rows produced by the 1.x id-encoding
  bug are merged, keeping the most useful record.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from backend.config import ROOT_DIR
from backend.providers.ids import safe_canonical_id

logger = logging.getLogger("animebox.migrations")

LATEST_VERSION = 1
MAX_BACKUPS = 5
CORE_TABLES = ("anime_titles", "library_episodes", "download_jobs", "watch_history", "app_settings")


@dataclass
class MigrationContext:
    library_root: Path
    app_root: Path = ROOT_DIR


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if _table_exists(conn, table) and column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _normalize_path(stored: str, ctx: MigrationContext) -> str:
    """Convert 1.x cwd-relative/absolute paths to library-relative POSIX paths where possible."""
    if not stored:
        return stored
    root = ctx.library_root.resolve()
    raw = stored.replace("\\", "/")
    candidate = Path(raw)
    looks_absolute = candidate.is_absolute() or (len(raw) > 2 and raw[1] == ":" and raw[2] == "/")
    if looks_absolute:
        try:
            return Path(raw).resolve().relative_to(root).as_posix()
        except (ValueError, OSError):
            return stored
    for base in (ctx.app_root, root):
        try:
            return (base / candidate).resolve().relative_to(root).as_posix()
        except (ValueError, OSError):
            continue
    return raw


def _resolve(stored: str, ctx: MigrationContext) -> Path:
    path = Path(stored)
    return path if path.is_absolute() else ctx.library_root / path


def _file_ok(stored: str, ctx: MigrationContext) -> bool:
    path = _resolve(stored, ctx)
    try:
        return path.is_file() and path.stat().st_size > 0 and ".part" not in path.name.lower()
    except OSError:
        return False


def _canonicalize_ids(conn: sqlite3.Connection, table: str, column: str = "anime_external_id") -> None:
    if not _table_exists(conn, table):
        return
    rows = conn.execute(f"SELECT id, {column} FROM {table}").fetchall()
    for row_id, value in rows:
        canonical = safe_canonical_id(value)
        if canonical != value:
            conn.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (canonical, row_id))


def _create_missing_tables(conn: sqlite3.Connection) -> None:
    """Partial 1.x databases: create absent tables (with the current schema) so later steps can run."""
    from sqlalchemy.dialects import sqlite
    from sqlalchemy.schema import CreateIndex, CreateTable

    from backend import models  # noqa: F401
    from backend.database.session import Base

    for table in Base.metadata.sorted_tables:
        if _table_exists(conn, table.name):
            continue
        conn.execute(str(CreateTable(table).compile(dialect=sqlite.dialect())))
        for index in table.indexes:
            conn.execute(str(CreateIndex(index, if_not_exists=True).compile(dialect=sqlite.dialect())))


def _migrate_to_v1(conn: sqlite3.Connection, ctx: MigrationContext) -> None:
    _create_missing_tables(conn)

    # 1. New columns.
    _add_column(conn, "library_episodes", "quality", "INTEGER")
    _add_column(conn, "download_jobs", "warning", "TEXT")
    _add_column(conn, "download_jobs", "quality", "INTEGER")
    _add_column(conn, "download_jobs", "player_host", "VARCHAR(256)")
    _add_column(conn, "download_jobs", "bytes_done", "INTEGER NOT NULL DEFAULT 0")
    _add_column(conn, "download_jobs", "bytes_total", "INTEGER")
    _add_column(conn, "download_jobs", "speed_bps", "FLOAT")
    _add_column(conn, "download_jobs", "attempts", "INTEGER NOT NULL DEFAULT 0")
    _add_column(conn, "download_jobs", "resumable", "BOOLEAN NOT NULL DEFAULT 0")
    _add_column(conn, "download_jobs", "finished_at", "DATETIME")
    _add_column(conn, "watch_history", "voiceover", "VARCHAR(256)")

    # 2. Canonical ids everywhere.
    _canonicalize_ids(conn, "library_episodes")
    _canonicalize_ids(conn, "download_jobs")
    _canonicalize_ids(conn, "watch_history")

    # anime_titles.external_id is UNIQUE: merge, keeping the most recently updated row.
    titles = conn.execute(
        "SELECT id, external_id, folder_path FROM anime_titles ORDER BY updated_at DESC, id DESC"
    ).fetchall()
    kept: dict[str, int] = {}
    for row_id, external_id, _folder in titles:
        canonical = safe_canonical_id(external_id)
        if canonical in kept:
            conn.execute("DELETE FROM anime_titles WHERE id=?", (row_id,))
            continue
        kept[canonical] = row_id
    for canonical, row_id in kept.items():
        conn.execute("UPDATE anime_titles SET external_id=? WHERE id=?", (canonical, row_id))

    # 3. Library-relative file paths.
    for row_id, stored in conn.execute("SELECT id, file_path FROM library_episodes").fetchall():
        normalized = _normalize_path(stored, ctx)
        if normalized != stored:
            conn.execute("UPDATE library_episodes SET file_path=? WHERE id=?", (normalized, row_id))

    for row_id, stored in conn.execute("SELECT id, folder_path FROM anime_titles WHERE folder_path IS NOT NULL").fetchall():
        normalized = _normalize_path(stored, ctx)
        if normalized != stored:
            conn.execute("UPDATE anime_titles SET folder_path=? WHERE id=?", (normalized, row_id))

    # 4. One library row per episode: prefer a row whose file exists, then the newest download.
    groups: dict[tuple, list[tuple]] = {}
    for row in conn.execute(
        "SELECT id, anime_external_id, season, episode, file_path, downloaded_at, progress_seconds "
        "FROM library_episodes"
    ).fetchall():
        groups.setdefault((row[1], row[2], row[3]), []).append(row)
    for rows in groups.values():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda r: (_file_ok(r[4], ctx), r[5] or "", r[0]), reverse=True)
        keep = rows[0]
        best_progress = max(r[6] or 0 for r in rows)
        conn.execute("UPDATE library_episodes SET progress_seconds=? WHERE id=?", (best_progress, keep[0]))
        for duplicate in rows[1:]:
            conn.execute("UPDATE watch_history SET local_episode_id=? WHERE local_episode_id=?", (keep[0], duplicate[0]))
            conn.execute("DELETE FROM library_episodes WHERE id=?", (duplicate[0],))

    # 5. One history row per episode: keep the latest progress.
    groups = {}
    for row in conn.execute(
        "SELECT id, anime_external_id, season, episode, updated_at, local_episode_id FROM watch_history"
    ).fetchall():
        groups.setdefault((row[1], row[2], row[3]), []).append(row)
    for rows in groups.values():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda r: (r[4] or "", r[0]), reverse=True)
        keep = rows[0]
        local_id = next((r[5] for r in rows if r[5]), None)
        if local_id and not keep[5]:
            conn.execute("UPDATE watch_history SET local_episode_id=? WHERE id=?", (local_id, keep[0]))
        for duplicate in rows[1:]:
            conn.execute("DELETE FROM watch_history WHERE id=?", (duplicate[0],))

    # 6. Browsing no longer implies library membership (root cause of the empty-library bug).
    conn.execute(
        "UPDATE anime_titles SET folder_path=NULL WHERE external_id NOT IN "
        "(SELECT DISTINCT anime_external_id FROM library_episodes)"
    )

    # 7. Constraints and indexes (names match backend/models).
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_library_episodes_key "
        "ON library_episodes (anime_external_id, season, episode)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_watch_history_key ON watch_history (anime_external_id, season, episode)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_watch_history_updated_at ON watch_history (updated_at)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_download_jobs_episode_key ON download_jobs (anime_external_id, season, episode)"
    )


MIGRATIONS: dict[int, Callable[[sqlite3.Connection, MigrationContext], None]] = {
    1: _migrate_to_v1,
}


def backup_database(db_path: Path, version: int) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"{db_path.stem}-v{version}-{stamp}.db"
    source = sqlite3.connect(db_path)
    try:
        dest = sqlite3.connect(target)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    backups = sorted(backup_dir.glob(f"{db_path.stem}-v*.db"), key=lambda p: p.stat().st_mtime)
    for stale in backups[:-MAX_BACKUPS]:
        stale.unlink(missing_ok=True)
    return target


def current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def has_schema(conn: sqlite3.Connection) -> bool:
    return any(_table_exists(conn, table) for table in CORE_TABLES)


def upgrade(db_path: Path, ctx: MigrationContext) -> tuple[int, int, Path | None]:
    """Upgrade an on-disk database. Returns ``(from_version, to_version, backup_path)``.

    A database without AnimeBox tables is left alone; ``init_db`` creates the
    schema and stamps it with :data:`LATEST_VERSION`.
    """
    if not db_path.exists():
        return LATEST_VERSION, LATEST_VERSION, None
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        version = current_version(conn)
        if not has_schema(conn) or version >= LATEST_VERSION:
            return version, version, None
    finally:
        conn.close()

    backup = backup_database(db_path, version)
    logger.info("Backed up database to %s before upgrading schema v%s -> v%s", backup, version, LATEST_VERSION)

    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for target in range(version + 1, LATEST_VERSION + 1):
                logger.info("Applying migration v%s", target)
                MIGRATIONS[target](conn, ctx)
            conn.execute(f"PRAGMA user_version = {LATEST_VERSION}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            logger.exception("Database migration failed; database left unchanged. Backup: %s", backup)
            raise
    finally:
        conn.close()
    return version, LATEST_VERSION, backup


def stamp_latest(db_path: Path) -> None:
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        if current_version(conn) < LATEST_VERSION:
            conn.execute(f"PRAGMA user_version = {LATEST_VERSION}")
    finally:
        conn.close()
