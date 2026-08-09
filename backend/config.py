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
    port: int = 8787
    library_path: Path = ROOT_DIR / "library"
    database_url: str = f"sqlite+aiosqlite:///{(ROOT_DIR / 'data' / 'animebox.db').as_posix()}"
    log_level: str = "INFO"
    http_proxy: str | None = None
    provider_search_timeout: float = Field(default=10.0, gt=0)
    preferred_voiceovers: str = "Aniliberty,Animevost,AniLibria,AnimeVost"
    default_quality: int = 1080
    steam_deck_crf: int = 23
    steam_deck_height: int = 720
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    def model_post_init(self, _context: object) -> None:
        self.library_path = _rooted_path(self.library_path)
        self.database_url = _rooted_database_url(self.database_url)

    @property
    def preferred_voiceover_list(self) -> list[str]:
        return [v.strip() for v in self.preferred_voiceovers.split(",") if v.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.library_path.mkdir(parents=True, exist_ok=True)
    database_url = make_url(settings.database_url)
    if database_url.drivername.startswith("sqlite") and database_url.database and database_url.database != ":memory:":
        Path(database_url.database).parent.mkdir(parents=True, exist_ok=True)
    return settings
