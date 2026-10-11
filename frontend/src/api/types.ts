export type SearchResult = {
  id: string
  title: string
  poster: string | null
  description: string | null
  year: number | null
  source: string
  source_label: string | null
}

export type ProviderSearchStatus = {
  source: string
  label: string
  ok: boolean
  count: number
  latency_ms: number | null
  error: string | null
  timed_out: boolean
}

export type SearchResponse = {
  query: string
  results: SearchResult[]
  providers: ProviderSearchStatus[]
}

export type VoiceoverKind = 'dub' | 'subtitles' | 'original'

export type VoiceoverOption = {
  title: string
  kind: VoiceoverKind
  players: string[]
  index: number
}

export type EpisodeInfo = { title: string; ordinal: number; season: number }

export type AnimeDetail = {
  id: string
  title: string
  poster: string | null
  description: string | null
  year: number | null
  source: string
  source_label: string | null
  seasons: number[]
  episodes: EpisodeInfo[]
}

export type StreamInfo = {
  anime_title: string
  episode: number
  voiceover: string
  player: string
  type: string
  quality: number
  qualities: number[]
  url: string
  browser_playable: boolean
  expires_at: number
}

export type DownloadStatus =
  | 'queued'
  | 'resolving'
  | 'downloading'
  | 'processing'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type DownloadJob = {
  id: number
  anime_external_id: string
  anime_title: string
  source: string
  season: number
  episode: number
  episode_title: string | null
  voiceover: string | null
  status: DownloadStatus
  progress: number
  error: string | null
  warning: string | null
  file_path: string | null
  steam_deck: boolean
  quality: number | null
  player_host: string | null
  bytes_done: number
  bytes_total: number | null
  speed_bps: number | null
  attempts: number
  resumable: boolean
  created_at: string | null
  updated_at: string | null
  finished_at: string | null
}

export type DownloadCreateResponse = {
  jobs: DownloadJob[]
  skipped: { episode: number; reason: 'already_downloaded' | 'already_queued' }[]
}

export type LibraryAnime = {
  id: string
  title: string
  poster: string | null
  description: string | null
  year: number | null
  source: string
  episode_count: number
  missing_count: number
  watched_count: number
  size_bytes: number
  last_downloaded_at: string | null
  folder_path: string | null
}

export type LibraryEpisode = {
  id: number
  anime_external_id: string
  season: number
  episode: number
  title: string | null
  voiceover: string | null
  file_path: string
  file_size: number | null
  quality: number | null
  progress_seconds: number
  duration_seconds: number | null
  completed: boolean
  downloaded_at: string | null
  available: boolean
  stream_url: string | null
}

export type LibraryStats = {
  titles: number
  episodes: number
  size_bytes: number
  library_path: string
  disk_total: number
  disk_free: number
}

export type WatchHistory = {
  id: number
  anime_external_id: string
  anime_title: string
  poster: string | null
  season: number
  episode: number
  voiceover: string | null
  progress_seconds: number
  duration_seconds: number | null
  local_episode_id: number | null
  updated_at: string | null
  completed: boolean
}

export type HomeFeed = {
  continue_watching: WatchHistory[]
  recently_watched: WatchHistory[]
  recently_downloaded: LibraryAnime[]
}

export type AppSettings = {
  preferred_voiceovers: string[]
  default_quality: number
  steam_deck_optimize: boolean
  steam_deck_crf: number
  steam_deck_height: number
  default_source: string
  enabled_sources: string[]
  http_proxy: string | null
  max_concurrent_downloads: number
  autoplay_next: boolean
  remember_volume: boolean
}

export type ProviderStatus = 'ok' | 'degraded' | 'down' | 'partial' | 'unknown'

export type StageResult = { ok: boolean; at: number; latency_ms: number | null; error: string | null }

export type ProviderInfo = {
  id: string
  label: string
  stable: boolean
  enabled: boolean
  is_default: boolean
  note: string
  status: ProviderStatus
  stages: Partial<Record<'search' | 'details' | 'episodes' | 'voiceovers' | 'stream', StageResult>>
  last_check_at: number | null
}

export type Diagnostics = {
  version: string
  python: string
  platform: string
  frozen: boolean
  ffmpeg: { path: string | null; version: string | null }
  paths: { library: string; data: string; database: string }
  disk: { total: number; used: number; free: number }
  network: { proxy: string | null }
  runtime: { media_sessions: number; running_downloads: number; max_concurrent_downloads: number }
}

export type RescanResult = { removed_missing: number; imported: number; removed_empty_dirs: number }
