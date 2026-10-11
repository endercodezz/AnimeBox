import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { AppSettings, VoiceoverOption } from '../api/types'
import { Icon } from '../components/icons'
import { Button, ButtonLink, IconButton, Spinner } from '../components/ui'
import { cx } from '../lib/cx'
import { formatTime } from '../lib/format'
import { getPrefs, setPrefs } from '../lib/prefs'
import { canonicalId } from '../lib/ids'
import { routes } from '../lib/routes'
import { useResource } from '../lib/useResource'
import { PlayerMenu, type MenuItem } from './player/Menu'
import { useSource } from './player/useSource'

type PlayerEpisode = { ordinal: number; title: string; localId: number | null; localUrl: string | null; progress: number; duration: number | null }

type PlayerContext = {
  title: string
  poster: string | null
  episodes: PlayerEpisode[]
  settings: AppSettings | null
}

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2]
const SAVE_EVERY_MS = 10_000

async function loadContext(id: string, offline: boolean, signal: AbortSignal): Promise<PlayerContext> {
  const settings = await api.settings().catch(() => null)
  if (offline) {
    const [episodes, library] = await Promise.all([api.libraryEpisodes(id, signal), api.library(signal).catch(() => [])])
    const meta = library.find((x) => x.id === id)
    return {
      title: meta?.title || 'Офлайн',
      poster: meta?.poster ?? null,
      settings,
      episodes: episodes
        .filter((e) => e.available)
        .map((e) => ({
          ordinal: e.episode,
          title: e.title || `Серия ${e.episode}`,
          localId: e.id,
          localUrl: e.stream_url,
          progress: e.progress_seconds,
          duration: e.duration_seconds,
        })),
    }
  }
  const [detail, history, local] = await Promise.all([
    api.anime(id, signal),
    api.animeHistory(id, signal).catch(() => []),
    api.libraryEpisodes(id, signal).catch(() => []),
  ])
  const hist = new Map(history.map((h) => [h.episode, h]))
  const loc = new Map(local.filter((e) => e.available).map((e) => [e.episode, e]))
  return {
    title: detail.title,
    poster: detail.poster,
    settings,
    episodes: detail.episodes.map((e) => ({
      ordinal: e.ordinal,
      title: e.title,
      localId: loc.get(e.ordinal)?.id ?? null,
      localUrl: loc.get(e.ordinal)?.stream_url ?? null,
      progress: hist.get(e.ordinal)?.progress_seconds ?? 0,
      duration: hist.get(e.ordinal)?.duration_seconds ?? null,
    })),
  }
}

export function PlayerPage() {
  const { id: rawId = '' } = useParams()
  const id = canonicalId(rawId)
  const [params] = useSearchParams()
  const offline = Boolean(Number(params.get('local')))
  const ctx = useResource((signal) => loadContext(id, offline, signal), [id, offline])

  if (ctx.error) {
    return (
      <div className="grid min-h-screen place-items-center bg-black px-6 text-center">
        <div className="max-w-md">
          <Icon name="alert" size={32} className="mx-auto text-danger" />
          <h1 className="mt-4 text-xl font-bold">Плеер не открылся</h1>
          <p className="mt-2 text-fog">{errorMessage(ctx.error)}</p>
          <div className="mt-6 flex justify-center gap-2">
            <Button icon="retry" onClick={ctx.reload}>
              Повторить
            </Button>
            <ButtonLink to={routes.anime(id)} variant="primary">
              К тайтлу
            </ButtonLink>
          </div>
        </div>
      </div>
    )
  }
  if (!ctx.data) {
    return (
      <div className="grid min-h-screen place-items-center bg-black">
        <Spinner size={36} className="text-violet-hi" />
      </div>
    )
  }
  return <PlayerStage animeId={id} ctx={ctx.data} />
}

function PlayerStage({ animeId, ctx }: { animeId: string; ctx: PlayerContext }) {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const episode = Number(params.get('episode') || ctx.episodes[0]?.ordinal || 1)
  const localId = Number(params.get('local')) || null
  const voiceoverParam = params.get('voiceover')
  const qualityParam = Number(params.get('quality')) || null
  const tParam = Number(params.get('t')) || 0

  const current = ctx.episodes.find((e) => e.ordinal === episode)
  const localEntry = localId ? ctx.episodes.find((e) => e.localId === localId) : undefined
  const index = ctx.episodes.findIndex((e) => e.ordinal === episode)
  const nextEp = index >= 0 ? ctx.episodes[index + 1] : undefined
  const prevEp = index > 0 ? ctx.episodes[index - 1] : undefined

  const videoRef = useRef<HTMLVideoElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)

  const startAt = useCallback(() => {
    if (tParam > 0) return tParam
    const saved = localEntry?.progress ?? current?.progress ?? 0
    const duration = localEntry?.duration ?? current?.duration ?? null
    if (saved < 5) return 0
    if (duration && saved > duration - 20) return 0 // finished last time: start over
    return saved
  }, [tParam, localEntry, current])

  const { state, retry, setLevel, setAudioTrack, setSubtitleTrack } = useSource(
    videoRef,
    {
      animeId,
      episode,
      voiceover: voiceoverParam,
      quality: qualityParam,
      localId,
      localUrl: localEntry?.localUrl ?? null,
    },
    startAt,
  )

  // ---------------------------------------------------------------- media state
  const [playing, setPlaying] = useState(false)
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [buffered, setBuffered] = useState(0)
  const [waiting, setWaiting] = useState(false)
  const [rate, setRate] = useState(1)
  const [volume, setVolumeState] = useState(() => (getPrefs().volume ?? 1))
  const [muted, setMutedState] = useState(() => getPrefs().muted ?? false)
  const [fullscreen, setFullscreen] = useState(false)
  const [nativeSubs, setNativeSubs] = useState<{ id: number; label: string }[]>([])
  const [nativeSub, setNativeSub] = useState(-1)
  const [menu, setMenu] = useState<null | 'voice' | 'quality' | 'speed' | 'audio' | 'subs'>(null)
  const [drawer, setDrawer] = useState(false)
  const [idle, setIdle] = useState(false)
  const [countdown, setCountdown] = useState<number | null>(null)
  const [hoverTime, setHoverTime] = useState<{ x: number; t: number } | null>(null)
  const remember = ctx.settings?.remember_volume ?? true

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    video.volume = remember ? volume : 1
    video.muted = remember ? muted : false
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial sync only
  }, [])

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    const sync = () => {
      setPlaying(!video.paused && !video.ended)
      setTime(video.currentTime)
      setDuration(Number.isFinite(video.duration) ? video.duration : 0)
      try {
        const ranges = video.buffered
        let end = 0
        for (let i = 0; i < ranges.length; i += 1) if (ranges.start(i) <= video.currentTime + 0.5) end = Math.max(end, ranges.end(i))
        setBuffered(end)
      } catch {
        /* buffered unavailable */
      }
    }
    const onWaiting = () => setWaiting(true)
    const onPlaying = () => setWaiting(false)
    const onVolume = () => {
      setVolumeState(video.volume)
      setMutedState(video.muted)
      if (remember) setPrefs({ volume: video.volume, muted: video.muted })
    }
    const onTracks = () => {
      const tracks = Array.from(video.textTracks).map((t, i) => ({ id: i, label: t.label || t.language || `Субтитры ${i + 1}` }))
      setNativeSubs(tracks)
    }
    const events = ['timeupdate', 'play', 'pause', 'durationchange', 'progress', 'seeked', 'ended', 'loadedmetadata']
    events.forEach((e) => video.addEventListener(e, sync))
    video.addEventListener('waiting', onWaiting)
    video.addEventListener('playing', onPlaying)
    video.addEventListener('canplay', onPlaying)
    video.addEventListener('volumechange', onVolume)
    video.addEventListener('loadedmetadata', onTracks)
    video.playbackRate = rate
    return () => {
      events.forEach((e) => video.removeEventListener(e, sync))
      video.removeEventListener('waiting', onWaiting)
      video.removeEventListener('playing', onPlaying)
      video.removeEventListener('canplay', onPlaying)
      video.removeEventListener('volumechange', onVolume)
      video.removeEventListener('loadedmetadata', onTracks)
    }
  }, [remember, rate])

  // ------------------------------------------------------------- progress saving
  const voiceForSave = state.stream?.voiceover ?? voiceoverParam
  const saveInfo = useRef({ animeId, episode, localId, title: ctx.title, poster: ctx.poster, voice: voiceForSave })
  saveInfo.current = { animeId, episode, localId, title: ctx.title, poster: ctx.poster, voice: voiceForSave }
  const lastSaved = useRef(0)
  // Last position of the *current* episode, tracked from events. The <video> element itself is reset by the
  // source hook when leaving an episode, so the final save must not read it.
  const position = useRef<{ t: number; d: number | null }>({ t: 0, d: null })

  const save = useCallback(
    (mode: 'normal' | 'beacon' = 'normal', info = saveInfo.current, pos = position.current) => {
      if (!Number.isFinite(pos.t) || pos.t < 1) return
      lastSaved.current = Date.now()
      const payload = {
        anime_id: info.animeId,
        anime_title: info.title,
        poster: info.poster,
        episode: info.episode,
        voiceover: info.voice,
        progress_seconds: pos.t,
        duration_seconds: pos.d,
        local_episode_id: info.localId,
      }
      if (mode === 'beacon') api.beaconProgress(payload)
      else void api.saveProgress(payload).catch(() => {})
    },
    [],
  )

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    position.current = { t: 0, d: null }
    // Bind every save in this effect to the episode it was created for.
    const info = () => ({ ...saveInfo.current, animeId, episode, localId })
    let active = true
    const track = () => {
      if (!active || video.readyState === 0 || !Number.isFinite(video.currentTime)) return
      position.current = { t: video.currentTime, d: Number.isFinite(video.duration) ? video.duration : null }
    }
    const onTime = () => {
      track()
      if (!video.paused && Date.now() - lastSaved.current > SAVE_EVERY_MS) save('normal', info())
    }
    const onPause = () => {
      if (!active) return
      track()
      save('normal', info())
    }
    const onHide = () => save('beacon', info())
    const onVisibility = () => document.visibilityState === 'hidden' && save('beacon', info())
    video.addEventListener('timeupdate', onTime)
    video.addEventListener('pause', onPause)
    video.addEventListener('seeked', onPause)
    window.addEventListener('pagehide', onHide)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      const final = { ...position.current }
      active = false
      save('beacon', info(), final) // leaving the episode (navigation, episode switch, unmount)
      video.removeEventListener('timeupdate', onTime)
      video.removeEventListener('pause', onPause)
      video.removeEventListener('seeked', onPause)
      window.removeEventListener('pagehide', onHide)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [save, animeId, episode, localId])

  // ------------------------------------------------------------------ navigation
  const goTo = useCallback(
    (target: PlayerEpisode | undefined) => {
      if (!target) return
      setCountdown(null)
      navigate(
        routes.player(animeId, {
          episode: target.ordinal,
          local: localId ? target.localId : null,
          voiceover: localId ? null : state.stream?.voiceover ?? voiceoverParam,
        }),
        { replace: true },
      )
    },
    [navigate, animeId, localId, state.stream?.voiceover, voiceoverParam],
  )

  function replaceParams(patch: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(patch)) {
      if (value === null) next.delete(key)
      else next.set(key, value)
    }
    setParams(next, { replace: true })
  }

  // Autoplay next episode (only when one exists).
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    const onEnded = () => {
      save()
      if (nextEp && (ctx.settings?.autoplay_next ?? true)) setCountdown(5)
    }
    video.addEventListener('ended', onEnded)
    return () => video.removeEventListener('ended', onEnded)
  }, [nextEp, ctx.settings, save])

  useEffect(() => {
    if (countdown === null) return
    if (countdown <= 0) {
      goTo(nextEp)
      return
    }
    const timer = window.setTimeout(() => setCountdown((c) => (c === null ? null : c - 1)), 1000)
    return () => window.clearTimeout(timer)
  }, [countdown, goTo, nextEp])

  useEffect(() => setCountdown(null), [episode])

  // --------------------------------------------------------------------- controls
  const togglePlay = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    if (video.paused || video.ended) void video.play().catch(() => {})
    else video.pause()
  }, [])
  const seekBy = useCallback((delta: number) => {
    const video = videoRef.current
    if (!video || !Number.isFinite(video.duration)) return
    video.currentTime = Math.max(0, Math.min(video.duration - 0.5, video.currentTime + delta))
  }, [])
  const setVolume = useCallback((value: number) => {
    const video = videoRef.current
    if (!video) return
    video.volume = Math.max(0, Math.min(1, value))
    if (video.volume > 0) video.muted = false
  }, [])
  const toggleMute = useCallback(() => {
    const video = videoRef.current
    if (video) video.muted = !video.muted
  }, [])
  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {})
    else void stageRef.current?.requestFullscreen?.().catch(() => {})
  }, [])
  const changeRate = useCallback((value: number) => {
    setRate(value)
    if (videoRef.current) videoRef.current.playbackRate = value
  }, [])

  useEffect(() => {
    const onChange = () => setFullscreen(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  // Hide controls while playing and idle.
  const idleTimer = useRef<number | undefined>(undefined)
  const wake = useCallback(() => {
    setIdle(false)
    window.clearTimeout(idleTimer.current)
    idleTimer.current = window.setTimeout(() => setIdle(true), 2800)
  }, [])
  useEffect(() => () => window.clearTimeout(idleTimer.current), [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' && (target as HTMLInputElement).type !== 'range')) return
      if (target?.isContentEditable || event.ctrlKey || event.metaKey || event.altKey) return
      if (menu && event.key !== 'Escape') return
      const video = videoRef.current
      let handled = true
      switch (event.key) {
        case ' ':
        case 'k':
        case 'л':
          togglePlay()
          break
        case 'ArrowLeft':
          seekBy(-5)
          break
        case 'ArrowRight':
          seekBy(5)
          break
        case 'j':
        case 'о':
          seekBy(-10)
          break
        case 'l':
        case 'д':
          seekBy(10)
          break
        case 'ArrowUp':
          setVolume((video?.volume ?? 1) + 0.05)
          break
        case 'ArrowDown':
          setVolume((video?.volume ?? 1) - 0.05)
          break
        case 'm':
        case 'ь':
          toggleMute()
          break
        case 'f':
        case 'а':
          toggleFullscreen()
          break
        case 'N':
        case 'Т':
          goTo(nextEp)
          break
        case 'P':
        case 'З':
          goTo(prevEp)
          break
        case '>':
        case 'Ю':
          changeRate(SPEEDS[Math.min(SPEEDS.length - 1, SPEEDS.indexOf(rate) + 1)] ?? rate)
          break
        case '<':
        case 'Б':
          changeRate(SPEEDS[Math.max(0, SPEEDS.indexOf(rate) - 1)] ?? rate)
          break
        case 'Escape':
          if (drawer) setDrawer(false)
          else if (countdown !== null) setCountdown(null)
          else handled = false
          break
        default:
          if (/^[0-9]$/.test(event.key) && video && Number.isFinite(video.duration)) video.currentTime = (Number(event.key) / 10) * video.duration
          else handled = false
      }
      if (handled) {
        event.preventDefault()
        wake()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menu, drawer, countdown, rate, togglePlay, seekBy, setVolume, toggleMute, toggleFullscreen, goTo, nextEp, prevEp, changeRate, wake])

  // ------------------------------------------------------------------------- menus
  const voiceovers = useResource((signal) => api.voiceovers(animeId, episode, signal), [animeId, episode, menu === 'voice'], menu === 'voice' && !localId)
  const voiceItems: MenuItem[] = (voiceovers.data ?? []).map((v: VoiceoverOption) => ({
    key: v.title,
    label: v.title,
    hint: `${v.kind === 'subtitles' ? 'субтитры · ' : ''}${v.players.join(', ')}`,
    active: (state.stream?.voiceover ?? voiceoverParam) === v.title,
    onSelect: () => replaceParams({ voiceover: v.title, quality: null, t: String(Math.floor(videoRef.current?.currentTime ?? 0)) }),
  }))

  const qualityItems: MenuItem[] =
    state.levels.length > 1
      ? [
          { key: 'auto', label: 'Авто', active: state.level === -1, onSelect: () => setLevel(-1) },
          ...[...state.levels].reverse().map((l) => ({ key: String(l.id), label: l.label, active: state.level === l.id, onSelect: () => setLevel(l.id) })),
        ]
      : (state.stream?.qualities ?? []).map((q) => ({
          key: String(q),
          label: `${q}p`,
          active: state.stream?.quality === q,
          onSelect: () => replaceParams({ quality: String(q), t: String(Math.floor(videoRef.current?.currentTime ?? 0)) }),
        }))

  const subtitleTracks = state.subtitleTracks.length ? state.subtitleTracks : nativeSubs
  const subtitleActive = state.subtitleTracks.length ? state.subtitleTrack : nativeSub
  const selectSubtitle = (trackId: number) => {
    if (state.subtitleTracks.length) setSubtitleTrack(trackId)
    else {
      const video = videoRef.current
      if (video) Array.from(video.textTracks).forEach((t, i) => (t.mode = i === trackId ? 'showing' : 'disabled'))
      setNativeSub(trackId)
    }
  }

  const busy = state.phase === 'resolving' || state.phase === 'loading' || state.phase === 'recovering' || (waiting && state.phase === 'ready')
  const showChrome = !playing || !idle || menu !== null || drawer || state.phase === 'error'
  const progressPct = duration ? (time / duration) * 100 : 0
  const bufferedPct = duration ? (buffered / duration) * 100 : 0
  const isOnline = !localId
  const status = useMemo(() => {
    if (state.phase === 'resolving') return 'Ищем рабочий плеер…'
    if (state.phase === 'recovering') return 'Восстанавливаем поток…'
    if (state.phase === 'loading') return 'Загружаем видео…'
    return 'Буферизация…'
  }, [state.phase])

  return (
    <div
      ref={stageRef}
      className={cx('relative h-[100dvh] w-full overflow-hidden bg-black text-paper select-none', !showChrome && 'cursor-none')}
      onPointerMove={wake}
      onPointerDown={wake}
    >
      <video
        ref={videoRef}
        className="absolute inset-0 h-full w-full bg-black object-contain"
        playsInline
        preload="auto"
        poster={ctx.poster ?? undefined}
        onClick={() => {
          if (menu) return
          togglePlay()
        }}
        onDoubleClick={toggleFullscreen}
      />

      {busy && state.phase !== 'error' && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <div className="flex flex-col items-center gap-3">
            <Spinner size={40} className="text-violet-hi" />
            <p className="text-[0.88rem] text-paper/80 [text-shadow:0_1px_8px_rgba(0,0,0,0.8)]">{status}</p>
          </div>
        </div>
      )}

      {state.phase === 'error' && (
        <div className="absolute inset-0 z-10 grid place-items-center bg-black/75 px-6">
          <div className="max-w-lg text-center" role="alert">
            <Icon name="alert" size={30} className="mx-auto text-danger" />
            <h2 className="mt-3 text-lg font-bold">Видео не воспроизводится</h2>
            <p className="mt-2 text-[0.92rem] leading-6 text-paper/75">{state.error}</p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              <Button variant="primary" icon="retry" onClick={() => retry(true)}>
                Повторить
              </Button>
              {isOnline && (
                <Button icon="mic" onClick={() => setMenu('voice')}>
                  Другая озвучка
                </Button>
              )}
              {isOnline && current?.localId && (
                <Button icon="offline" onClick={() => navigate(routes.player(animeId, { episode, local: current.localId }), { replace: true })}>
                  Смотреть скачанную
                </Button>
              )}
              <ButtonLink to={routes.anime(animeId, episode)}>К тайтлу</ButtonLink>
            </div>
          </div>
        </div>
      )}

      {countdown !== null && nextEp && (
        <div className="glass absolute bottom-28 right-4 z-20 w-[min(340px,calc(100%-32px))] rounded-2xl border border-white/10 p-4 shadow-[0_20px_60px_rgba(0,0,0,0.6)] sm:right-8">
          <p className="eyebrow">Следующая серия через {countdown} с</p>
          <p className="mt-1.5 truncate font-bold">
            {nextEp.ordinal}. {nextEp.title}
          </p>
          <div className="mt-3 flex gap-2">
            <Button variant="primary" size="sm" icon="play" onClick={() => goTo(nextEp)}>
              Смотреть
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setCountdown(null)}>
              Отмена
            </Button>
          </div>
        </div>
      )}

      {/* Top bar */}
      <div className={cx('absolute inset-x-0 top-0 z-10 bg-gradient-to-b from-black/80 to-transparent px-3 pb-10 pt-3 transition-opacity duration-300 sm:px-6', showChrome ? 'opacity-100' : 'pointer-events-none opacity-0')}>
        <div className="flex items-center gap-3">
          <Link
            to={routes.anime(animeId, episode)}
            aria-label="Назад к тайтлу"
            className="grid size-10 shrink-0 place-items-center rounded-xl text-paper hover:bg-white/10"
          >
            <Icon name="arrowLeft" size={22} />
          </Link>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[0.98rem] font-bold">{ctx.title}</p>
            <p className="truncate text-[0.8rem] text-paper/70">
              Серия {episode}
              {current?.title && current.title !== `Episode ${episode}` && current.title !== `Серия ${episode}` ? ` · ${current.title}` : ''}
              {state.stream ? ` · ${state.stream.voiceover} · ${state.stream.player}` : ''}
              {localId ? ' · офлайн' : ''}
            </p>
          </div>
          <IconButton icon="list" label="Список серий" onClick={() => setDrawer((v) => !v)} active={drawer} className="text-paper" />
        </div>
      </div>

      {/* Bottom controls */}
      <div className={cx('absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-black/90 via-black/50 to-transparent px-3 pb-3 pt-16 transition-opacity duration-300 sm:px-6 sm:pb-5', showChrome ? 'opacity-100' : 'pointer-events-none opacity-0')}>
        <div className="relative">
          {hoverTime && (
            <span className="tabular pointer-events-none absolute -top-8 -translate-x-1/2 rounded-md bg-black/85 px-2 py-0.5 text-[0.78rem] font-semibold" style={{ left: hoverTime.x }}>
              {formatTime(hoverTime.t)}
            </span>
          )}
          <input
            type="range"
            aria-label="Позиция воспроизведения"
            aria-valuetext={`${formatTime(time)} из ${formatTime(duration)}`}
            min={0}
            max={duration || 0}
            step={0.1}
            value={Math.min(time, duration || 0)}
            disabled={!duration}
            onChange={(e) => {
              const video = videoRef.current
              if (video) video.currentTime = Number(e.target.value)
            }}
            onPointerMove={(e) => {
              const rect = e.currentTarget.getBoundingClientRect()
              const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
              setHoverTime({ x: e.clientX - rect.left, t: ratio * duration })
            }}
            onPointerLeave={() => setHoverTime(null)}
            className="player-range block h-5 w-full cursor-pointer"
            style={{
              background: `linear-gradient(to right, var(--color-violet) 0 ${progressPct}%, rgb(255 255 255 / 0.38) ${progressPct}% ${Math.max(progressPct, bufferedPct)}%, rgb(255 255 255 / 0.16) ${Math.max(progressPct, bufferedPct)}% 100%) center / 100% 4px no-repeat`,
            }}
          />
        </div>

        <div className="mt-1 flex items-center gap-1 sm:gap-2">
          <IconButton icon={playing ? 'pause' : 'play'} label={playing ? 'Пауза (пробел)' : 'Смотреть (пробел)'} onClick={togglePlay} size={44} className="text-paper" />
          <IconButton icon="prev" label="Предыдущая серия (Shift+P)" onClick={() => goTo(prevEp)} disabled={!prevEp} className="hidden text-paper sm:inline-grid" />
          <IconButton icon="next" label="Следующая серия (Shift+N)" onClick={() => goTo(nextEp)} disabled={!nextEp} className="text-paper" />
          <IconButton icon="back10" label="Назад на 10 секунд (J)" onClick={() => seekBy(-10)} className="hidden text-paper md:inline-grid" />
          <IconButton icon="fwd10" label="Вперёд на 10 секунд (L)" onClick={() => seekBy(10)} className="hidden text-paper md:inline-grid" />
          <div className="group/vol flex items-center">
            <IconButton icon={muted || volume === 0 ? 'mute' : 'volume'} label="Звук (M)" onClick={toggleMute} className="text-paper" />
            <input
              type="range"
              aria-label="Громкость"
              min={0}
              max={1}
              step={0.05}
              value={muted ? 0 : volume}
              onChange={(e) => setVolume(Number(e.target.value))}
              className="player-range hidden h-5 w-20 cursor-pointer sm:block"
              style={{ background: `linear-gradient(to right, white 0 ${(muted ? 0 : volume) * 100}%, rgb(255 255 255 / 0.2) ${(muted ? 0 : volume) * 100}% 100%) center / 100% 3px no-repeat` }}
            />
          </div>
          <span className="tabular ml-1 whitespace-nowrap text-[0.82rem] text-paper/85">
            {formatTime(time)} <span className="text-paper/45">/ {formatTime(duration)}</span>
          </span>

          <div className="relative ml-auto flex items-center gap-0.5 sm:gap-1">
            {isOnline && (
              <div className="relative">
                <IconButton icon="mic" label="Озвучка" onClick={() => setMenu(menu === 'voice' ? null : 'voice')} active={menu === 'voice'} className="text-paper" />
                {menu === 'voice' && (
                  <PlayerMenu
                    title="Озвучка"
                    items={voiceItems}
                    empty={voiceovers.loading ? 'Загружаем список…' : voiceovers.error ? errorMessage(voiceovers.error) : 'Нет вариантов'}
                    onClose={() => setMenu(null)}
                  />
                )}
              </div>
            )}
            {subtitleTracks.length > 0 && (
              <div className="relative">
                <IconButton icon="cc" label="Субтитры" onClick={() => setMenu(menu === 'subs' ? null : 'subs')} active={menu === 'subs' || subtitleActive >= 0} className="text-paper" />
                {menu === 'subs' && (
                  <PlayerMenu
                    title="Субтитры"
                    items={[
                      { key: 'off', label: 'Выключены', active: subtitleActive < 0, onSelect: () => selectSubtitle(-1) },
                      ...subtitleTracks.map((t) => ({ key: String(t.id), label: t.label, active: subtitleActive === t.id, onSelect: () => selectSubtitle(t.id) })),
                    ]}
                    onClose={() => setMenu(null)}
                  />
                )}
              </div>
            )}
            {state.audioTracks.length > 1 && (
              <div className="relative">
                <IconButton icon="layers" label="Аудиодорожка" onClick={() => setMenu(menu === 'audio' ? null : 'audio')} active={menu === 'audio'} className="text-paper" />
                {menu === 'audio' && (
                  <PlayerMenu
                    title="Аудиодорожка"
                    items={state.audioTracks.map((t) => ({ key: String(t.id), label: t.label, active: state.audioTrack === t.id, onSelect: () => setAudioTrack(t.id) }))}
                    onClose={() => setMenu(null)}
                  />
                )}
              </div>
            )}
            {qualityItems.length > 1 && (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setMenu(menu === 'quality' ? null : 'quality')}
                  aria-label="Качество"
                  className={cx('tabular h-10 rounded-xl px-2.5 text-[0.8rem] font-bold', menu === 'quality' ? 'bg-violet/20 text-violet-text' : 'text-paper hover:bg-white/10')}
                >
                  {state.levels.length > 1 ? (state.level === -1 ? 'Авто' : state.levels[state.level]?.label) : `${state.stream?.quality}p`}
                </button>
                {menu === 'quality' && <PlayerMenu title="Качество" items={qualityItems} onClose={() => setMenu(null)} />}
              </div>
            )}
            <div className="relative">
              <button
                type="button"
                onClick={() => setMenu(menu === 'speed' ? null : 'speed')}
                aria-label="Скорость воспроизведения"
                className={cx('tabular h-10 rounded-xl px-2.5 text-[0.8rem] font-bold', menu === 'speed' ? 'bg-violet/20 text-violet-text' : 'text-paper hover:bg-white/10')}
              >
                {String(rate).replace('.', ',')}×
              </button>
              {menu === 'speed' && (
                <PlayerMenu
                  title="Скорость"
                  items={SPEEDS.map((s) => ({ key: String(s), label: s === 1 ? 'Обычная' : `${String(s).replace('.', ',')}×`, active: rate === s, onSelect: () => changeRate(s) }))}
                  onClose={() => setMenu(null)}
                />
              )}
            </div>
            <IconButton icon={fullscreen ? 'exitFullscreen' : 'fullscreen'} label="Полный экран (F)" onClick={toggleFullscreen} className="text-paper" />
          </div>
        </div>
      </div>

      {/* Episode drawer */}
      {drawer && (
        <aside className="glass absolute inset-y-0 right-0 z-30 flex w-[min(360px,100%)] flex-col border-l border-white/10" aria-label="Серии">
          <div className="flex items-center justify-between px-4 py-4">
            <p className="font-bold">Серии</p>
            <IconButton icon="close" label="Закрыть" onClick={() => setDrawer(false)} className="text-paper" />
          </div>
          <ol className="flex-1 space-y-1 overflow-y-auto px-2 pb-4">
            {ctx.episodes.map((ep) => {
              const active = ep.ordinal === episode
              const ratio = ep.duration ? Math.min(1, ep.progress / ep.duration) : 0
              return (
                <li key={ep.ordinal}>
                  <button
                    type="button"
                    onClick={() => {
                      setDrawer(false)
                      goTo(ep)
                    }}
                    aria-current={active || undefined}
                    className={cx('flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left', active ? 'bg-violet/20' : 'hover:bg-white/[0.07]')}
                  >
                    <span className="display tabular w-8 shrink-0 text-[0.95rem] font-semibold text-paper/80">{String(ep.ordinal).padStart(2, '0')}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[0.88rem] font-semibold">{ep.title}</span>
                      {ratio > 0 && (
                        <span className="mt-1.5 block h-[3px] overflow-hidden rounded-full bg-white/10">
                          <span className="block h-full bg-violet" style={{ width: `${Math.round(ratio * 100)}%` }} />
                        </span>
                      )}
                    </span>
                    {ep.localId && <Icon name="offline" size={15} className="shrink-0 text-offline" />}
                  </button>
                </li>
              )
            })}
          </ol>
          <p className="border-t border-white/10 px-4 py-3 text-[0.75rem] leading-5 text-fog">
            Пробел — пауза · ←/→ — 5 с · J/L — 10 с · ↑/↓ — громкость · F — полный экран · Shift+N — следующая
          </p>
        </aside>
      )}
    </div>
  )
}
