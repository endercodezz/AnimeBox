import type {
  AnimeDetail,
  AppSettings,
  Diagnostics,
  DownloadCreateResponse,
  DownloadJob,
  HomeFeed,
  LibraryAnime,
  LibraryEpisode,
  LibraryStats,
  ProviderInfo,
  RescanResult,
  SearchResponse,
  StreamInfo,
  VoiceoverOption,
  WatchHistory,
} from './types'

/** Error raised for non-2xx API responses; carries the backend's structured detail. */
export class ApiError extends Error {
  status: number
  code: string
  stage: string | null
  source: string | null

  constructor(status: number, message: string, code = 'error', stage: string | null = null, source: string | null = null) {
    super(message)
    this.status = status
    this.code = code
    this.stage = stage
    this.source = source
  }
}

type Detail = { code?: string; message?: string; stage?: string | null; source?: string | null }

async function parseError(res: Response): Promise<ApiError> {
  let message = res.statusText || `HTTP ${res.status}`
  let code = 'error'
  let stage: string | null = null
  let source: string | null = null
  try {
    const body = await res.json()
    const detail: unknown = body?.detail ?? body
    if (typeof detail === 'string') message = detail
    else if (Array.isArray(detail)) message = detail.map((d) => d?.msg).filter(Boolean).join('; ') || message
    else if (detail && typeof detail === 'object') {
      const d = detail as Detail
      message = d.message || message
      code = d.code || code
      stage = d.stage ?? null
      source = d.source ?? null
    }
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, message, code, stage, source)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(0, 'AnimeBox не отвечает. Проверьте, что приложение запущено.', 'offline')
  }
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const q = (params: Record<string, string | number | boolean | null | undefined>) => {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== null && value !== undefined && value !== '') search.set(key, String(value))
  return search.toString()
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) })

export type ProgressPayload = {
  anime_id?: string | null
  anime_title?: string | null
  poster?: string | null
  season?: number
  episode: number
  voiceover?: string | null
  progress_seconds: number
  duration_seconds?: number | null
  local_episode_id?: number | null
}

export const api = {
  health: () => request<{ status: string; version: string }>('/api/health'),
  session: () => request<{ shutdown_token: string; shutdown_enabled: boolean; version: string }>('/api/session'),
  shutdown: async () => {
    const session = await api.session()
    return request<{ message: string }>('/api/shutdown', { method: 'POST', headers: { 'X-AnimeBox-Token': session.shutdown_token } })
  },

  providers: () => request<ProviderInfo[]>('/api/providers'),
  checkProvider: (id: string) => request<ProviderInfo>(`/api/providers/${encodeURIComponent(id)}/check`, { method: 'POST' }),
  search: (query: string, source?: string, signal?: AbortSignal) =>
    request<SearchResponse>(`/api/search?${q({ q: query, source })}`, { signal }),
  anime: (id: string, signal?: AbortSignal) => request<AnimeDetail>(`/api/anime?${q({ id })}`, { signal }),
  voiceovers: (id: string, episode: number, signal?: AbortSignal) =>
    request<VoiceoverOption[]>(`/api/anime/voiceovers?${q({ id, episode })}`, { signal }),
  resolveStream: (
    body: { anime_id: string; episode: number; voiceover?: string | null; quality?: number | null; player?: string | null; refresh?: boolean },
    signal?: AbortSignal,
  ) => request<StreamInfo>('/api/stream/resolve', { method: 'POST', ...json(body), signal }),

  createDownloads: (body: {
    anime_id: string
    season?: number
    episode?: number | null
    episodes?: number[] | null
    voiceover?: string | null
    quality?: number | null
    replace?: boolean
  }) => request<DownloadCreateResponse>('/api/downloads', { method: 'POST', ...json(body) }),
  downloads: (status: 'all' | 'active' | 'finished' = 'all', signal?: AbortSignal) =>
    request<DownloadJob[]>(`/api/downloads?${q({ status })}`, { signal }),
  downloadAction: (id: number, action: 'cancel' | 'retry' | 'pause' | 'resume') =>
    request<{ message: string }>(`/api/downloads/${id}/${action}`, { method: 'POST' }),
  removeDownload: (id: number) => request<{ message: string }>(`/api/downloads/${id}`, { method: 'DELETE' }),
  clearDownloads: () => request<{ message: string }>('/api/downloads/clear', { method: 'POST' }),

  library: (signal?: AbortSignal) => request<LibraryAnime[]>('/api/library', { signal }),
  libraryStats: () => request<LibraryStats>('/api/library/stats'),
  libraryEpisodes: (id: string, signal?: AbortSignal) => request<LibraryEpisode[]>(`/api/library/episodes?${q({ id })}`, { signal }),
  deleteLibraryAnime: (id: string) => request<{ message: string }>(`/api/library/anime?${q({ id })}`, { method: 'DELETE' }),
  deleteLibraryEpisode: (episodeId: number) => request<{ message: string }>(`/api/library/episodes/${episodeId}`, { method: 'DELETE' }),
  rescanLibrary: () => request<RescanResult>('/api/library/rescan', { method: 'POST' }),

  home: (signal?: AbortSignal) => request<HomeFeed>('/api/home', { signal }),
  history: () => request<WatchHistory[]>('/api/history'),
  animeHistory: (id: string, signal?: AbortSignal) => request<WatchHistory[]>(`/api/history/anime?${q({ id })}`, { signal }),
  deleteHistory: (entryId: number) => request<{ message: string }>(`/api/history/${entryId}`, { method: 'DELETE' }),
  clearHistory: () => request<{ message: string }>('/api/history', { method: 'DELETE' }),
  saveProgress: (body: ProgressPayload) => request<WatchHistory>('/api/progress', { method: 'POST', ...json(body) }),
  /** Fire-and-forget save that survives page unload. */
  beaconProgress: (body: ProgressPayload) => {
    const payload = JSON.stringify(body)
    if (navigator.sendBeacon?.('/api/progress', new Blob([payload], { type: 'application/json' }))) return
    void fetch('/api/progress', { method: 'POST', body: payload, headers: { 'Content-Type': 'application/json' }, keepalive: true }).catch(() => {})
  },

  settings: () => request<AppSettings>('/api/settings'),
  updateSettings: (body: Partial<AppSettings>) => request<AppSettings>('/api/settings', { method: 'PUT', ...json(body) }),
  diagnostics: () => request<Diagnostics>('/api/diagnostics'),
}

export function errorMessage(err: unknown, fallback = 'Что-то пошло не так'): string {
  if (err instanceof ApiError || err instanceof Error) return err.message || fallback
  return fallback
}

export function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError'
}
