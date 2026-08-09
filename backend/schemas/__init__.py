from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    id: str
    title: str
    poster: str | None = None
    description: str | None = None
    year: int | None = None
    source: str


class VideoStream(BaseModel):
    type: str
    quality: int
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


class VoiceoverOption(BaseModel):
    title: str
    url: str
    player_host: str | None = None
    index: int = 0


class EpisodeInfo(BaseModel):
    title: str
    ordinal: int
    season: int = 1
    voiceovers: list[VoiceoverOption] = Field(default_factory=list)


class AnimeDetail(BaseModel):
    id: str
    title: str
    poster: str | None = None
    description: str | None = None
    year: int | None = None
    source: str
    seasons: list[int] = Field(default_factory=lambda: [1])
    episodes: list[EpisodeInfo] = Field(default_factory=list)


class DownloadRequest(BaseModel):
    anime_id: str
    season: int = 1
    episode: int | None = None
    episodes: list[int] | None = None
    voiceover: str | None = None
    steam_deck: bool = False


class DownloadJobOut(BaseModel):
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
    file_path: str | None = None
    steam_deck: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class LibraryAnimeOut(BaseModel):
    id: str
    title: str
    poster: str | None = None
    description: str | None = None
    year: int | None = None
    source: str
    episode_count: int = 0
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
    progress_seconds: float = 0
    duration_seconds: float | None = None
    completed: bool = False
    downloaded_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProgressUpdate(BaseModel):
    anime_id: str | None = None
    anime_title: str | None = None
    poster: str | None = None
    season: int = 1
    episode: int
    progress_seconds: float
    duration_seconds: float | None = None
    local_episode_id: int | None = None


class WatchHistoryOut(BaseModel):
    id: int
    anime_external_id: str
    anime_title: str
    poster: str | None = None
    season: int
    episode: int
    progress_seconds: float
    duration_seconds: float | None = None
    local_episode_id: int | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class AppSettingsOut(BaseModel):
    preferred_voiceovers: list[str]
    default_quality: int
    steam_deck_optimize: bool = False
    steam_deck_crf: int = 23
    steam_deck_height: int = 720
    default_source: str = "animego"
    http_proxy: str | None = None


class AppSettingsUpdate(BaseModel):
    preferred_voiceovers: list[str] | None = None
    default_quality: int | None = None
    steam_deck_optimize: bool | None = None
    steam_deck_crf: int | None = None
    steam_deck_height: int | None = None
    default_source: str | None = None
    http_proxy: str | None = None


class StreamResolveRequest(BaseModel):
    anime_id: str
    episode: int
    voiceover: str | None = None
    quality: int | None = None


class StreamResolveResponse(BaseModel):
    anime_title: str
    episode: int
    voiceover: str
    video: VideoStream
    proxy_url: str | None = None


class SourceInfo(BaseModel):
    id: str
    label: str


class ApiMessage(BaseModel):
    message: str
    detail: Any | None = None
