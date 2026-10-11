from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

QUALITIES = (360, 480, 720, 1080)


class SearchResult(BaseModel):
    id: str
    title: str
    poster: str | None = None
    description: str | None = None
    year: int | None = None
    source: str
    source_label: str | None = None


class ProviderSearchStatus(BaseModel):
    source: str
    label: str
    ok: bool
    count: int = 0
    latency_ms: int | None = None
    error: str | None = None
    timed_out: bool = False


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    providers: list[ProviderSearchStatus]


class VoiceoverOption(BaseModel):
    title: str
    kind: Literal["dub", "subtitles", "original"] = "dub"
    players: list[str] = Field(default_factory=list)
    index: int = 0


class EpisodeInfo(BaseModel):
    title: str
    ordinal: int
    season: int = 1


class AnimeDetail(BaseModel):
    id: str
    title: str
    poster: str | None = None
    description: str | None = None
    year: int | None = None
    source: str
    source_label: str | None = None
    seasons: list[int] = Field(default_factory=lambda: [1])
    episodes: list[EpisodeInfo] = Field(default_factory=list)


class StreamResolveRequest(BaseModel):
    anime_id: str = Field(min_length=3, max_length=1024)
    episode: int = Field(ge=0, le=100000)
    season: int = Field(default=1, ge=0, le=1000)
    voiceover: str | None = Field(default=None, max_length=256)
    quality: int | None = Field(default=None, ge=144, le=4320)
    player: str | None = Field(default=None, max_length=128)
    refresh: bool = False


class StreamResolveResponse(BaseModel):
    anime_title: str
    episode: int
    voiceover: str
    player: str
    type: str
    quality: int
    qualities: list[int] = Field(default_factory=list)
    url: str
    browser_playable: bool = True
    expires_at: float


class DownloadRequest(BaseModel):
    anime_id: str = Field(min_length=3, max_length=1024)
    season: int = Field(default=1, ge=0, le=1000)
    episode: int | None = Field(default=None, ge=0, le=100000)
    episodes: list[int] | None = Field(default=None, max_length=2000)
    voiceover: str | None = Field(default=None, max_length=256)
    quality: int | None = Field(default=None, ge=144, le=4320)
    steam_deck: bool | None = None
    # Re-download episodes that are already in the library (e.g. another voiceover).
    replace: bool = False


class DownloadJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    anime_external_id: str
    anime_title: str
    source: str
    season: int
    episode: int
    episode_title: str | None = None
    voiceover: str | None = None
    status: str
    progress: float
    error: str | None = None
    warning: str | None = None
    file_path: str | None = None
    steam_deck: bool = False
    quality: int | None = None
    player_host: str | None = None
    bytes_done: int = 0
    bytes_total: int | None = None
    speed_bps: float | None = None
    attempts: int = 0
    resumable: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    finished_at: datetime | None = None


class SkippedDownload(BaseModel):
    episode: int
    reason: Literal["already_downloaded", "already_queued"]


class DownloadCreateResponse(BaseModel):
    jobs: list[DownloadJobOut]
    skipped: list[SkippedDownload] = Field(default_factory=list)


class LibraryAnimeOut(BaseModel):
    id: str
    title: str
    poster: str | None = None
    description: str | None = None
    year: int | None = None
    source: str
    episode_count: int = 0
    missing_count: int = 0
    watched_count: int = 0
    size_bytes: int = 0
    last_downloaded_at: datetime | None = None
    folder_path: str | None = None


class LibraryEpisodeOut(BaseModel):
    id: int
    anime_external_id: str
    season: int
    episode: int
    title: str | None = None
    voiceover: str | None = None
    file_path: str
    file_size: int | None = None
    quality: int | None = None
    progress_seconds: float = 0
    duration_seconds: float | None = None
    completed: bool = False
    downloaded_at: datetime | None = None
    available: bool = True
    stream_url: str | None = None


class LibraryStats(BaseModel):
    titles: int
    episodes: int
    size_bytes: int
    library_path: str
    disk_total: int
    disk_free: int


class RescanResult(BaseModel):
    removed_missing: int
    imported: int
    removed_empty_dirs: int


class ProgressUpdate(BaseModel):
    anime_id: str | None = Field(default=None, max_length=1024)
    anime_title: str | None = Field(default=None, max_length=512)
    poster: str | None = Field(default=None, max_length=2048)
    season: int = Field(default=1, ge=0, le=1000)
    episode: int = Field(ge=0, le=100000)
    voiceover: str | None = Field(default=None, max_length=256)
    progress_seconds: float = Field(ge=0, le=7 * 24 * 3600)
    duration_seconds: float | None = Field(default=None, ge=0, le=7 * 24 * 3600)
    local_episode_id: int | None = Field(default=None, ge=1)


class WatchHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    anime_external_id: str
    anime_title: str
    poster: str | None = None
    season: int
    episode: int
    voiceover: str | None = None
    progress_seconds: float
    duration_seconds: float | None = None
    local_episode_id: int | None = None
    updated_at: datetime | None = None
    completed: bool = False


class HomeOut(BaseModel):
    continue_watching: list[WatchHistoryOut]
    recently_watched: list[WatchHistoryOut]
    recently_downloaded: list[LibraryAnimeOut]


def dedupe_casefold(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value.casefold() not in seen:
            seen.add(value.casefold())
            out.append(value)
    return out


def _validate_proxy(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return ""
    if not value.lower().startswith(("http://", "https://", "socks5://", "socks5h://")):
        raise ValueError("Proxy must start with http://, https://, socks5:// or socks5h://")
    return value


class AppSettingsOut(BaseModel):
    preferred_voiceovers: list[str]
    default_quality: int
    steam_deck_optimize: bool = False
    steam_deck_crf: int = 23
    steam_deck_height: int = 720
    default_source: str = "animego"
    enabled_sources: list[str] = Field(default_factory=list)
    http_proxy: str | None = None
    max_concurrent_downloads: int = 2
    autoplay_next: bool = True
    remember_volume: bool = True


class AppSettingsUpdate(BaseModel):
    preferred_voiceovers: list[str] | None = Field(default=None, max_length=50)
    default_quality: int | None = None
    steam_deck_optimize: bool | None = None
    steam_deck_crf: int | None = Field(default=None, ge=0, le=51)
    steam_deck_height: int | None = Field(default=None, ge=240, le=2160)
    default_source: str | None = Field(default=None, max_length=64)
    enabled_sources: list[str] | None = Field(default=None, max_length=50)
    http_proxy: str | None = Field(default=None, max_length=1024)
    max_concurrent_downloads: int | None = Field(default=None, ge=1, le=6)
    autoplay_next: bool | None = None
    remember_volume: bool | None = None

    @field_validator("default_quality")
    @classmethod
    def _quality(cls, value: int | None) -> int | None:
        if value is not None and value not in QUALITIES:
            raise ValueError(f"Quality must be one of {QUALITIES}")
        return value

    @field_validator("http_proxy")
    @classmethod
    def _proxy(cls, value: str | None) -> str | None:
        return _validate_proxy(value)

    @field_validator("preferred_voiceovers")
    @classmethod
    def _voiceovers(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [v.strip()[:128] for v in value if v and v.strip()]
        return dedupe_casefold(cleaned)


class StageOut(BaseModel):
    ok: bool
    at: float
    latency_ms: int | None = None
    error: str | None = None


class ProviderInfo(BaseModel):
    id: str
    label: str
    stable: bool
    enabled: bool
    is_default: bool
    note: str = ""
    status: Literal["ok", "degraded", "down", "partial", "unknown"]
    stages: dict[str, StageOut] = Field(default_factory=dict)
    last_check_at: float | None = None


class ApiMessage(BaseModel):
    message: str
    detail: Any | None = None
