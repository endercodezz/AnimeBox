import type {
  AnimeDetail,
  AppSettings,
  DownloadJob,
  LibraryAnime,
  LibraryEpisode,
  SearchResult,
  SourceInfo,
  StreamResolveResponse,
  VoiceoverOption,
  WatchHistory,
} from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || body.message || JSON.stringify(body)
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string }>('/api/health'),
  sources: () => request<SourceInfo[]>('/api/sources'),
  search: (q: string, source?: string) => {
    const params = new URLSearchParams({ q })
    if (source) params.set('source', source)
    return request<SearchResult[]>(`/api/search?${params}`)
  },
  anime: (id: string, voiceovers = false) =>
    request<AnimeDetail>(`/api/anime/${encodeURIComponent(id)}?voiceovers=${voiceovers}`),
  voiceovers: (id: string, episode: number) =>
    request<VoiceoverOption[]>(
      `/api/anime/${encodeURIComponent(id)}/episodes/${episode}/voiceovers`,
    ),
  resolveStream: (body: {
    anime_id: string
    episode: number
    voiceover?: string | null
    quality?: number | null
  }) =>
    request<StreamResolveResponse>('/api/stream/resolve', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  createDownloads: (body: {
    anime_id: string
    season?: number
    episode?: number | null
    episodes?: number[] | null
    voiceover?: string | null
    steam_deck?: boolean
  }) =>
    request<DownloadJob[]>('/api/downloads', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  downloads: () => request<DownloadJob[]>('/api/downloads'),
  cancelDownload: (id: number) =>
    request<{ message: string }>(`/api/downloads/${id}/cancel`, { method: 'POST' }),
  retryDownload: (id: number) =>
    request<{ message: string }>(`/api/downloads/${id}/retry`, { method: 'POST' }),
  library: () => request<LibraryAnime[]>('/api/library'),
  libraryEpisodes: (id: string) =>
    request<LibraryEpisode[]>(`/api/library/${encodeURIComponent(id)}/episodes`),
  libraryFileUrl: (episodeId: number) => `/api/library/file/${episodeId}`,
  history: () => request<WatchHistory[]>('/api/history'),
  saveProgress: (body: {
    anime_id?: string | null
    anime_title?: string | null
    poster?: string | null
    season?: number
    episode: number
    progress_seconds: number
    duration_seconds?: number | null
    local_episode_id?: number | null
  }) =>
    request<WatchHistory>('/api/progress', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  settings: () => request<AppSettings>('/api/settings'),
  updateSettings: (body: Partial<AppSettings>) =>
    request<AppSettings>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
}
