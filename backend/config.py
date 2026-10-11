from functools import lru_cache
from pathlib import Path
import sys

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

PACKAGE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ROOT_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def _rooted_path(path: Path) -> Path:
    return path if path.is_absolute() else (ROOT_DIR / path).resolve()


def _rooted_database_url(value: str) -> str:
    url = make_url(value)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return value
    database = Path(url.database)
    if database.is_absolute():
        return value
    return url.set(database=_rooted_path(database).as_posix()).render_as_string(hide_password=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = Field(default=8787, ge=1, le=65535)
    library_path: Path = ROOT_DIR / "library"
    data_path: Path = ROOT_DIR / "data"
    database_url: str = f"sqlite+aiosqlite:///{(ROOT_DIR / 'data' / 'animebox.db').as_posix()}"
    log_level: str = "INFO"
    http_proxy: str | None = None
    # Per-stage provider budgets. A slow provider is reported, never allowed to block others.
    provider_search_timeout: float = Field(default=10.0, gt=0)
    provider_detail_timeout: float = Field(default=25.0, gt=0)
    provider_stream_timeout: float = Field(default=25.0, gt=0)
    preferred_voiceovers: str = "AniLibria,AnimeVost,Aniliberty,Animevost"
    default_quality: int = 1080
    max_concurrent_downloads: int = Field(default=2, ge=1, le=6)
    steam_deck_crf: int = 23
    steam_deck_height: int = 720
    media_session_ttl: int = Field(default=4 * 3600, ge=60)
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    # Extra Host header values accepted besides loopback names (e.g. a LAN hostname).
    allowed_hosts: list[str] = []

    def model_post_init(self, _context: object) -> None:
        self.library_path = _rooted_path(self.library_path)
        self.data_path = _rooted_path(self.data_path)
        self.database_url = _rooted_database_url(self.database_url)

    @property
    def preferred_voiceover_list(self) -> list[str]:
        return [v.strip() for v in self.preferred_voiceovers.split(",") if v.strip()]

    @property
    def database_file(self) -> Path | None:
        url = make_url(self.database_url)
        if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
            return None
        return Path(url.database)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.library_path.mkdir(parents=True, exist_ok=True)
    settings.data_path.mkdir(parents=True, exist_ok=True)
    if settings.database_file is not None:
        settings.database_file.parent.mkdir(parents=True, exist_ok=True)
    return settings
