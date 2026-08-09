from functools import lru_cache
from pathlib import Path
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ROOT_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


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
    preferred_voiceovers: str = "Aniliberty,Animevost,AniLibria,AnimeVost"
    default_quality: int = 1080
    steam_deck_crf: int = 23
    steam_deck_height: int = 720
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    @property
    def preferred_voiceover_list(self) -> list[str]:
        return [v.strip() for v in self.preferred_voiceovers.split(",") if v.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.library_path.mkdir(parents=True, exist_ok=True)
    (ROOT_DIR / "data").mkdir(parents=True, exist_ok=True)
    return settings
