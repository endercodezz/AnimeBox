import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import type { AnimeDetail, LibraryEpisode, VoiceoverOption } from '../api/types'

export function AnimePage() {
  const { '*': rawId = '' } = useParams()
  const id = decodeURIComponent(rawId)
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const localMode = params.get('local') === '1'

  const [detail, setDetail] = useState<AnimeDetail | null>(null)
  const [localEps, setLocalEps] = useState<LibraryEpisode[]>([])
  const [voiceMap, setVoiceMap] = useState<Record<number, VoiceoverOption[]>>({})
  const [selectedVoice, setSelectedVoice] = useState<Record<number, string>>({})
  const [loadingVoices, setLoadingVoices] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        if (localMode) {
          const [lib, eps] = await Promise.all([api.library(), api.libraryEpisodes(id)])
          if (cancelled) return
          const meta = lib.find((x) => x.id === id)
          setLocalEps(eps)
          setDetail({
            id,
            title: meta?.title || id,
            poster: meta?.poster || null,
            description: meta?.description || null,
            year: meta?.year || null,
            source: meta?.source || 'local',
            seasons: [...new Set(eps.map((e) => e.season))],
            episodes: eps.map((e) => ({
              title: e.title || `Episode ${e.episode}`,
              ordinal: e.episode,
              season: e.season,
              voiceovers: [],
            })),
          })
        } else {
          const data = await api.anime(id)
          if (!cancelled) setDetail(data)
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Не удалось загрузить')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [id, localMode])

  const episodes = useMemo(() => detail?.episodes || [], [detail])

  async function loadVoiceovers(ep: number) {
    if (voiceMap[ep]) return voiceMap[ep]
    setLoadingVoices(ep)
    try {
      const list = await api.voiceovers(id, ep)
      setVoiceMap((m) => ({ ...m, [ep]: list }))
      if (list[0] && !selectedVoice[ep]) {
        setSelectedVoice((s) => ({ ...s, [ep]: list[0].title }))
      }
      return list
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Озвучки недоступны')
      return []
    } finally {
      setLoadingVoices(null)
    }
  }

  async function downloadEpisode(ep: number) {
    setBusy(true)
    setMessage(null)
    try {
      await loadVoiceovers(ep)
      const voice = selectedVoice[ep]
      await api.createDownloads({
        anime_id: id,
        episode: ep,
        voiceover: voice || null,
      })
      setMessage(`Эпизод ${ep} добавлен в очередь`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки')
    } finally {
      setBusy(false)
    }
  }

  async function downloadSeason() {
    if (!detail) return
    setBusy(true)
    setMessage(null)
    try {
      await api.createDownloads({
        anime_id: id,
        episodes: detail.episodes.map((e) => e.ordinal),
      })
      setMessage('Сезон добавлен в очередь загрузок')
      navigate('/downloads')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки')
    } finally {
      setBusy(false)
    }
  }

  function playEpisode(ep: number, localId?: number) {
    const voice = selectedVoice[ep]
    const qs = new URLSearchParams({ episode: String(ep) })
    if (voice) qs.set('voiceover', voice)
    if (localId) qs.set('local', String(localId))
    navigate(`/player/${encodeURIComponent(id)}?${qs}`)
  }

  if (error && !detail) {
    return <p className="text-danger">{error}</p>
  }
  if (!detail) {
    return <p className="text-fog">Загрузка тайтла…</p>
  }

  return (
    <div className="animate-rise space-y-9">
      <section className="surface relative isolate overflow-hidden rounded-[28px] p-5 sm:p-8 lg:p-10">
        {detail.poster && <img src={detail.poster} alt="" className="absolute inset-0 -z-20 h-full w-full scale-110 object-cover opacity-20 blur-2xl" />}
        <div className="absolute inset-0 -z-10 bg-[linear-gradient(90deg,rgba(8,7,13,0.99)_15%,rgba(8,7,13,0.9)_60%,rgba(23,17,38,0.75))]" />
        <div className="grid gap-7 sm:grid-cols-[180px_1fr] lg:grid-cols-[230px_1fr] lg:gap-10">
          <div className="mx-auto w-full max-w-[220px] overflow-hidden rounded-2xl bg-ink-3 shadow-[0_30px_80px_rgba(0,0,0,0.5)] ring-1 ring-white/12 sm:mx-0">
            {detail.poster ? <img src={detail.poster} alt="" className="aspect-[2/3] w-full object-cover" /> : <div className="flex aspect-[2/3] items-center justify-center font-display text-6xl text-white/15">{detail.title.slice(0, 1)}</div>}
          </div>
          <div className="flex flex-col justify-center space-y-5">
            <div><p className="eyebrow">{[detail.source, detail.year].filter(Boolean).join(' · ')}</p><h1 className="mt-2 max-w-4xl font-display text-4xl font-extrabold leading-tight tracking-[-0.045em] sm:text-5xl lg:text-6xl">{detail.title}</h1></div>
            {detail.description && <p className="max-w-3xl text-sm leading-7 text-fog sm:text-base">{detail.description}</p>}
            {!localMode && <div className="flex flex-wrap gap-3"><button type="button" disabled={busy} onClick={downloadSeason} className="btn-primary">↓ Скачать сезон</button><Link to="/downloads" className="btn-secondary">Очередь загрузок</Link></div>}
            {localMode && <span className="w-fit rounded-full bg-ok/12 px-3 py-1 text-xs font-bold text-ok">Доступно офлайн</span>}
            {message && <p className="text-sm font-bold text-ok">✓ {message}</p>}
            {error && <p className="text-sm text-danger">{error}</p>}
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-end justify-between"><div><p className="eyebrow">Сезон 1</p><h2 className="section-title">Серии</h2></div><span className="text-sm text-fog">{episodes.length} эп.</span></div>
        <ul className="surface divide-y divide-white/6 overflow-hidden rounded-2xl">
          {episodes.map((ep) => {
            const local = localEps.find((l) => l.episode === ep.ordinal && l.season === ep.season)
            const voices = voiceMap[ep.ordinal] || []
            return (
              <li key={`${ep.season}-${ep.ordinal}`} className="space-y-3 p-4 transition hover:bg-white/[0.025] sm:p-5">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-white/5 font-display text-sm font-extrabold text-violet-soft">{String(ep.ordinal).padStart(2, '0')}</div>
                  <div className="min-w-0 flex-1">
                    <p className="font-bold">{ep.title}</p>
                    {local && <p className="mt-1 text-xs font-semibold text-ok">● Офлайн · {local.voiceover || 'озвучка неизвестна'}</p>}
                  </div>
                  <button type="button" onClick={() => playEpisode(ep.ordinal, local?.id)} className="btn-primary px-4 py-2 text-sm">▶ Смотреть</button>
                  {!localMode && (
                    <>
                      <button type="button" onClick={() => loadVoiceovers(ep.ordinal)} className="btn-secondary px-3 py-2 text-sm">{loadingVoices === ep.ordinal ? 'Загрузка…' : 'Озвучки'}</button>
                      <button type="button" disabled={busy} onClick={() => downloadEpisode(ep.ordinal)} className="btn-secondary border-amber/20 px-3 py-2 text-sm text-violet-soft">↓ Скачать</button>
                    </>
                  )}
                </div>
                {voices.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {voices.map((v) => (
                      <label
                        key={`${v.index}-${v.title}`}
                        className={[
                          'cursor-pointer rounded-full px-3 py-1 text-xs ring-1 transition',
                          selectedVoice[ep.ordinal] === v.title
                            ? 'bg-amber/20 text-violet-soft ring-amber/50'
                            : 'bg-black/20 text-fog ring-white/10 hover:bg-white/5 hover:text-paper',
                        ].join(' ')}
                      >
                        <input
                          type="radio"
                          className="sr-only"
                          name={`voice-${ep.ordinal}`}
                          checked={selectedVoice[ep.ordinal] === v.title}
                          onChange={() =>
                            setSelectedVoice((s) => ({ ...s, [ep.ordinal]: v.title }))
                          }
                        />
                        {v.title}
                        {v.player_host ? ` · ${v.player_host}` : ''}
                      </label>
                    ))}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      </section>
    </div>
  )
}
