from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

import backend.config as config


def test_relative_runtime_paths_are_rooted_to_app(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "AnimeBox Portable"
    foreign_cwd = tmp_path / "launcher-cwd"
    root.mkdir()
    foreign_cwd.mkdir()
    monkeypatch.setattr(config, "ROOT_DIR", root)
    monkeypatch.chdir(foreign_cwd)

    settings = config.Settings(
        _env_file=None,
        library_path=Path("./library"),
        database_url="sqlite+aiosqlite:///./data/animebox.db",
    )

    assert settings.library_path == root / "library"
    assert Path(make_url(settings.database_url).database) == root / "data" / "animebox.db"


def test_absolute_and_memory_database_urls_are_preserved(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "ROOT_DIR", tmp_path / "portable")
    absolute = (tmp_path / "database" / "animebox.db").resolve()

    absolute_settings = config.Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{absolute.as_posix()}",
    )
    memory_settings = config.Settings(_env_file=None, database_url="sqlite+aiosqlite:///:memory:")

    assert Path(make_url(absolute_settings.database_url).database) == absolute
    assert memory_settings.database_url == "sqlite+aiosqlite:///:memory:"


def test_provider_search_timeout_is_configurable() -> None:
    assert config.Settings(_env_file=None).provider_search_timeout == 10.0
    assert config.Settings(_env_file=None, provider_search_timeout=2.5).provider_search_timeout == 2.5


@pytest.mark.parametrize("value", [0, -1])
def test_provider_search_timeout_must_be_positive(value: float) -> None:
    with pytest.raises(ValidationError):
        config.Settings(_env_file=None, provider_search_timeout=value)


def test_get_settings_creates_custom_database_parent(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "portable"
    monkeypatch.setattr(config, "ROOT_DIR", root)
    monkeypatch.setenv("LIBRARY_PATH", "./media")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./state/db/animebox.db")
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.library_path == root / "media"
        assert (root / "media").is_dir()
        assert (root / "state" / "db").is_dir()
    finally:
        config.get_settings.cache_clear()
