"""Schema migration from AnimeBox 1.x (user_version 0) databases."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from conftest import write_media

from backend.database import migrations

V0_SCHEMA = """
CREATE TABLE anime_titles (id INTEGER NOT NULL, external_id VARCHAR(512) NOT NULL, source VARCHAR(64) NOT NULL,
  title VARCHAR(512) NOT NULL, poster VARCHAR(1024), description TEXT, year INTEGER, folder_path VARCHAR(1024),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  PRIMARY KEY (id));
CREATE UNIQUE INDEX ix_anime_titles_external_id ON anime_titles (external_id);
CREATE TABLE library_episodes (id INTEGER NOT NULL, anime_external_id VARCHAR(512) NOT NULL, season INTEGER NOT NULL,
  episode INTEGER NOT NULL, title VARCHAR(512), voiceover VARCHAR(256), file_path VARCHAR(1024) NOT NULL,
  file_size INTEGER, downloaded_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, progress_seconds FLOAT NOT NULL,
  duration_seconds FLOAT, completed BOOLEAN NOT NULL, PRIMARY KEY (id));
CREATE TABLE download_jobs (id INTEGER NOT NULL, anime_external_id VARCHAR(512) NOT NULL, anime_title VARCHAR(512) NOT NULL,
  source VARCHAR(64) NOT NULL, season INTEGER NOT NULL, episode INTEGER NOT NULL, episode_title VARCHAR(512),
  voiceover VARCHAR(256), source_url VARCHAR(2048), status VARCHAR(32) NOT NULL, progress FLOAT NOT NULL, error TEXT,
  file_path VARCHAR(1024), steam_deck BOOLEAN NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY (id));
CREATE TABLE watch_history (id INTEGER NOT NULL, anime_external_id VARCHAR(512) NOT NULL, anime_title VARCHAR(512) NOT NULL,
  poster VARCHAR(1024), season INTEGER NOT NULL, episode INTEGER NOT NULL, progress_seconds FLOAT NOT NULL,
  duration_seconds FLOAT, local_episode_id INTEGER, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY (id));
CREATE TABLE app_settings ("key" VARCHAR(128) NOT NULL, value TEXT NOT NULL, PRIMARY KEY ("key"));
"""


@pytest.fixture
def legacy_db(tmp_path: Path) -> tuple[Path, migrations.MigrationContext]:
    app_root = tmp_path / "app"
    library_root = app_root / "library"
    write_media(library_root / "Show" / "Season 1" / "Episode 01.mp4")
    (library_root / "Browsed Only").mkdir(parents=True)
    db = app_root / "data" / "animebox.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.executescript(V0_SCHEMA)
    conn.executemany(
        "INSERT INTO anime_titles (id, external_id, source, title, folder_path, updated_at) VALUES (?,?,?,?,?,?)",
        [
            (1, "animego:%2Fanime%2Fshow-1", "animego", "Show", "library\\Show", "2026-01-01"),
            (2, "animego:/anime/show-1", "animego", "Show (newer)", "library\\Show", "2026-02-01"),
            (3, "anilibria:id%3A9", "anilibria", "Browsed Only", "library\\Browsed Only", "2026-01-01"),
        ],
    )
    conn.executemany(
        "INSERT INTO library_episodes (id, anime_external_id, season, episode, file_path, progress_seconds, completed, downloaded_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        [
            (1, "animego:%2Fanime%2Fshow-1", 1, 1, "library\\Show\\Season 1\\Episode 01.mp4", 100, 0, "2026-01-01"),
            (2, "animego:/anime/show-1", 1, 1, "library\\Show\\Season 1\\Episode 01.mkv", 300, 0, "2026-03-01"),
        ],
    )
    conn.executemany(
        "INSERT INTO watch_history (id, anime_external_id, anime_title, season, episode, progress_seconds, local_episode_id, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        [
            (1, "animego:%2Fanime%2Fshow-1", "Show", 1, 1, 50, 2, "2026-01-01"),
            (2, "animego:/anime/show-1", "Show", 1, 1, 400, None, "2026-04-01"),
        ],
    )
    conn.execute(
        "INSERT INTO download_jobs (anime_external_id, anime_title, source, season, episode, status, progress, steam_deck)"
        " VALUES ('animego:/anime/show-1', 'Show', 'animego', 1, 2, 'downloading', 40, 0)"
    )
    conn.execute("INSERT INTO app_settings VALUES ('default_quality', '720')")
    conn.commit()
    conn.close()
    return db, migrations.MigrationContext(library_root=library_root, app_root=app_root)


def rows(db: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_upgrade_merges_duplicates_and_preserves_user_data(legacy_db):
    db, ctx = legacy_db
    before, after, backup = migrations.upgrade(db, ctx)

    assert (before, after) == (0, migrations.LATEST_VERSION)
    assert backup is not None and backup.is_file()
    assert rows(backup, "SELECT count(*) FROM anime_titles") == [(3,)]  # untouched copy

    assert rows(db, "SELECT external_id, title, folder_path FROM anime_titles ORDER BY id") == [
        ("animego:%2Fanime%2Fshow-1", "Show (newer)", "Show"),
        ("anilibria:id%3A9", "Browsed Only", None),  # browsing no longer means "in library"
    ]
    # The row whose file exists wins over the newer row pointing at a missing file; best progress kept.
    assert rows(db, "SELECT id, file_path, progress_seconds FROM library_episodes") == [
        (1, "Show/Season 1/Episode 01.mp4", 300.0)
    ]
    assert rows(db, "SELECT anime_external_id, progress_seconds, local_episode_id FROM watch_history") == [
        ("animego:%2Fanime%2Fshow-1", 400.0, 1)
    ]
    assert rows(db, "SELECT anime_external_id, status, bytes_done, attempts FROM download_jobs") == [
        ("animego:%2Fanime%2Fshow-1", "downloading", 0, 0)
    ]
    assert rows(db, "SELECT * FROM app_settings") == [("default_quality", "720")]
    assert rows(db, "PRAGMA user_version") == [(migrations.LATEST_VERSION,)]


def test_upgrade_is_repeatable(legacy_db):
    db, ctx = legacy_db
    migrations.upgrade(db, ctx)
    snapshot = rows(db, "SELECT * FROM library_episodes")
    assert migrations.upgrade(db, ctx) == (migrations.LATEST_VERSION, migrations.LATEST_VERSION, None)
    assert rows(db, "SELECT * FROM library_episodes") == snapshot


def test_unique_index_prevents_duplicate_episode_rows(legacy_db):
    db, ctx = legacy_db
    migrations.upgrade(db, ctx)
    conn = sqlite3.connect(db)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO library_episodes (anime_external_id, season, episode, file_path, progress_seconds, completed)"
            " VALUES ('animego:%2Fanime%2Fshow-1', 1, 1, 'x.mp4', 0, 0)"
        )
    conn.close()


def test_failed_migration_rolls_back_and_keeps_backup(legacy_db, monkeypatch):
    db, ctx = legacy_db
    original = rows(db, "SELECT * FROM anime_titles ORDER BY id")

    def explode(conn, _ctx):
        conn.execute("UPDATE anime_titles SET title='broken'")
        raise RuntimeError("boom")

    monkeypatch.setitem(migrations.MIGRATIONS, 1, explode)
    with pytest.raises(RuntimeError):
        migrations.upgrade(db, ctx)
    assert rows(db, "SELECT * FROM anime_titles ORDER BY id") == original
    assert rows(db, "PRAGMA user_version") == [(0,)]
    assert list((db.parent / "backups").glob("*.db"))


def test_fresh_or_missing_database_is_left_for_create_all(tmp_path):
    ctx = migrations.MigrationContext(library_root=tmp_path / "library")
    assert migrations.upgrade(tmp_path / "missing.db", ctx)[2] is None
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    assert migrations.upgrade(empty, ctx) == (0, 0, None)
    assert not (tmp_path / "backups").exists()


def test_partial_legacy_database_gets_missing_tables(tmp_path):
    db = tmp_path / "partial.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE anime_titles (id INTEGER PRIMARY KEY, external_id VARCHAR(512) NOT NULL UNIQUE,"
        " source VARCHAR(64) NOT NULL, title VARCHAR(512) NOT NULL, poster TEXT, description TEXT, year INTEGER,"
        " folder_path TEXT, created_at DATETIME, updated_at DATETIME)"
    )
    conn.execute("INSERT INTO anime_titles (external_id, source, title) VALUES ('animego:/anime/x-1', 'animego', 'X')")
    conn.commit()
    conn.close()

    migrations.upgrade(db, migrations.MigrationContext(library_root=tmp_path / "library"))

    tables = {row[0] for row in rows(db, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(migrations.CORE_TABLES) <= tables
    assert rows(db, "SELECT external_id FROM anime_titles") == [("animego:%2Fanime%2Fx-1",)]
