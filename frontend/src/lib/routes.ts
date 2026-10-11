/**
 * Route builders. Anime ids already contain URL-encoded parts (e.g. `animego:%2Fanime%2Fx`);
 * they are encoded once more for the path and the router decodes them exactly once.
 * Never call decodeURIComponent on route params — that produced duplicate ids in 1.x.
 */
export const routes = {
  home: () => '/',
  search: (query?: string, source?: string) => {
    const params = new URLSearchParams()
    if (query) params.set('q', query)
    if (source) params.set('source', source)
    const qs = params.toString()
    return qs ? `/search?${qs}` : '/search'
  },
  anime: (id: string, episode?: number) => `/anime/${encodeURIComponent(id)}${episode ? `?episode=${episode}` : ''}`,
  player: (id: string, opts: { episode: number; voiceover?: string | null; local?: number | null; t?: number | null; quality?: number | null }) => {
    const params = new URLSearchParams({ episode: String(opts.episode) })
    if (opts.voiceover) params.set('voiceover', opts.voiceover)
    if (opts.local) params.set('local', String(opts.local))
    if (opts.quality) params.set('quality', String(opts.quality))
    if (opts.t && opts.t > 0) params.set('t', String(Math.floor(opts.t)))
    return `/player/${encodeURIComponent(id)}?${params}`
  },
  library: () => '/library',
  downloads: () => '/downloads',
  settings: (section?: string) => (section ? `/settings#${section}` : '/settings'),
}

export function continueTarget(item: { anime_external_id: string; episode: number; voiceover: string | null; local_episode_id: number | null }): string {
  return routes.player(item.anime_external_id, { episode: item.episode, voiceover: item.voiceover, local: item.local_episode_id })
}
