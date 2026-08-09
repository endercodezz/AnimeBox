import Hls from 'hls.js'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'

export function PlayerPage() {
  const { '*': rawId = '' } = useParams()
  const animeId = decodeURIComponent(rawId)
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const episode = Number(params.get('episode') || 1)
  const season = Number(params.get('season') || 1)
  const voiceover = params.get('voiceover')
  const localId = params.get('local') ? Number(params.get('local')) : null

  const videoRef = useRef<HTMLVideoElement>(null)
  const hlsRef = useRef<Hls | null>(null)
  const lastSave = useRef(0)

  const [title, setTitle] = useState('')
  const [voice, setVoice] = useState(voiceover || '')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [poster, setPoster] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let hls: Hls | null = null

    ;(async () => {
      setLoading(true)
      setError(null)
      try {
        let src = ''
        let isHls = false
        let resumeAt = 0

        if (localId) {
          src = api.libraryFileUrl(localId)
          const eps = await api.libraryEpisodes(animeId)
          const ep = eps.find((e) => e.id === localId)
          if (ep) {
            resumeAt = ep.progress_seconds || 0
            setVoice(ep.voiceover || '')
          }
          const lib = await api.library()
          const meta = lib.find((x) => x.id === animeId)
          setTitle(meta?.title || animeId)
          setPoster(meta?.poster || null)
        } else {
          const stream = await api.resolveStream({
            anime_id: animeId,
            episode,
            voiceover,
          })
          if (cancelled) return
          setTitle(stream.anime_title)
          setVoice(stream.voiceover)
          src = stream.proxy_url || stream.video.url
          isHls = stream.video.type === 'm3u8' || src.includes('.m3u8')
          try {
            const detail = await api.anime(animeId)
            setPoster(detail.poster)
          } catch {
            /* optional */
          }
        }

        const video = videoRef.current
        if (!video || cancelled) return

        if (hlsRef.current) {
          hlsRef.current.destroy()
          hlsRef.current = null
        }

        const seekAndPlay = () => {
          if (resumeAt > 5) video.currentTime = resumeAt
          void video.play().catch(() => {})
        }

        if (isHls && Hls.isSupported()) {
          hls = new Hls({ enableWorker: true })
          hlsRef.current = hls
          hls.loadSource(src)
          hls.attachMedia(video)
          hls.on(Hls.Events.MANIFEST_PARSED, seekAndPlay)
        } else if (isHls && video.canPlayType('application/vnd.apple.mpegurl')) {
          video.src = src
          video.addEventListener('loadedmetadata', seekAndPlay, { once: true })
        } else {
          video.src = src
          video.addEventListener('loadedmetadata', seekAndPlay, { once: true })
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Не удалось открыть поток')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
      if (hls) hls.destroy()
      if (hlsRef.current) {
        hlsRef.current.destroy()
        hlsRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when stream identity changes
  }, [animeId, episode, voiceover, localId])

  async function saveProgress(force = false) {
    const video = videoRef.current
    if (!video || !Number.isFinite(video.currentTime)) return
    const now = Date.now()
    if (!force && now - lastSave.current < 5000) return
    lastSave.current = now
    try {
      await api.saveProgress({
        anime_id: animeId,
        anime_title: title || animeId,
        poster,
        season,
        episode,
        progress_seconds: video.currentTime,
        duration_seconds: Number.isFinite(video.duration) ? video.duration : null,
        local_episode_id: localId,
      })
    } catch {
      /* ignore transient */
    }
  }

  async function nextEpisode() {
    await saveProgress(true)
    const next = episode + 1
    const qs = new URLSearchParams({ episode: String(next), season: String(season) })
    if (voice) qs.set('voiceover', voice)
    navigate(`/player/${encodeURIComponent(animeId)}?${qs}`)
  }

  return (
    <div className="animate-rise mx-auto max-w-[1400px] space-y-5">
      <div className="flex flex-wrap items-center gap-4">
        <Link to={`/anime/${encodeURIComponent(animeId)}`} className="btn-secondary px-3 py-2 text-sm">← Назад</Link>
        <div className="min-w-0 flex-1">
          <p className="eyebrow">Сейчас играет</p>
          <h1 className="truncate font-display text-xl font-bold tracking-tight sm:text-3xl">{title || 'Плеер'}</h1>
          <p className="mt-1 text-sm text-fog">Серия {episode}{voice ? ` · ${voice}` : ''}{localId ? ' · Офлайн' : ''}</p>
        </div>
        <button type="button" onClick={nextEpisode} className="btn-primary px-4 py-2.5 text-sm">Следующая серия →</button>
      </div>

      {loading && <p className="rounded-xl bg-amber/8 px-4 py-3 text-sm text-violet-soft">Готовим поток…</p>}
      {error && <p className="rounded-xl border border-danger/20 bg-danger/8 px-4 py-3 text-danger">{error}</p>}

      <div className="overflow-hidden rounded-2xl bg-black ring-1 ring-white/12 shadow-[0_28px_100px_rgba(0,0,0,0.58),0_0_70px_rgba(139,92,246,0.08)]">
        <video
          ref={videoRef}
          className="aspect-video w-full bg-black"
          controls
          playsInline
          onTimeUpdate={() => void saveProgress()}
          onPause={() => void saveProgress(true)}
          onEnded={() => void nextEpisode()}
        />
      </div>
    </div>
  )
}
