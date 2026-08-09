export type SearchResult = {
  id: string
  title: string
  poster: string | null
  description: string | null
  year: number | null
  source: string
}

export type VoiceoverOption = {
  title: string
  url: string
  player_host: string | null
  index: number
}

export type EpisodeInfo = {
  title: string
  ordinal: number
  season: number
  voiceovers: VoiceoverOption[]
}

export type AnimeDetail = {
  id: string
  title: string
  poster: string | null
  description: string | null
  year: number | null
  source: string
  seasons: number[]
  episodes: EpisodeInfo[]
}

export type DownloadJob = {
  id: number
  anime_external_id: string
  anime_title: string
  source: string
  season: number
  episode: number
  episode_title: string | null
  voiceover: string | null
  status: string
  progress: number
  error: string | null
  file_path: string | null
  steam_deck: boolean
  created_at: string | null
  updated_at: string | null
}

export type LibraryAnime = {
  id: string
  title: string
  poster: string | null
  description: string | null
  year: number | null
  source: string
  episode_count: number
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
  progress_seconds: number
  duration_seconds: number | null
  completed: boolean
  downloaded_at: string | null
}

export type WatchHistory = {
  id: number
  anime_external_id: string
  anime_title: string
  poster: string | null
  season: number
  episode: number
  progress_seconds: number
  duration_seconds: number | null
  local_episode_id: number | null
  updated_at: string | null
}

export type AppSettings = {
  preferred_voiceovers: string[]
  default_quality: number
  steam_deck_optimize: boolean
  steam_deck_crf: number
  steam_deck_height: number
  default_source: string
  http_proxy: string | null
}

export type StreamResolveResponse = {
  anime_title: string
  episode: number
  voiceover: string
  video: {
    type: string
    quality: number
    url: string
    headers: Record<string, string>
  }
  proxy_url: string | null
}

export type SourceInfo = {
  id: string
  label: string
}
