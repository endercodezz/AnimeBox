import Hls, { type ErrorData } from 'hls.js'
import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { api, ApiError, errorMessage, isAbort } from '../../api/client'
import type { StreamInfo } from '../../api/types'

export type SourceRequest = {
  animeId: string
  episode: number
  voiceover: string | null
  quality: number | null
  localId: number | null
  localUrl: string | null
}

export type Track = { id: number; label: string }

export type SourceState = {
  phase: 'resolving' | 'loading' | 'ready' | 'recovering' | 'error'
  stream: StreamInfo | null
  error: string | null
  levels: Track[]
  level: number // -1 = auto
  audioTracks: Track[]
  audioTrack: number
  subtitleTracks: Track[]
  subtitleTrack: number // -1 = off
}

const INITIAL: SourceState = {
  phase: 'resolving',
  stream: null,
  error: null,
  levels: [],
  level: -1,
  audioTracks: [],
  audioTrack: -1,
  subtitleTracks: [],
  subtitleTrack: -1,
}

const MAX_NETWORK_RETRIES = 3
const MAX_RERESOLVES = 2

function describeHlsError(data: ErrorData): string {
  const status = data.response && 'code' in data.response ? Number(data.response.code) : 0
  if (status === 410 || status === 502) return 'Ссылка на поток устарела'
  if (status === 403) return 'Хостинг видео отклонил запрос'
  if (data.type === Hls.ErrorTypes.MEDIA_ERROR) return 'Браузер не смог декодировать поток'
  if (data.details === Hls.ErrorDetails.MANIFEST_LOAD_TIMEOUT || data.details === Hls.ErrorDetails.FRAG_LOAD_TIMEOUT) return 'Хостинг видео не отвечает'
  return 'Не удалось загрузить видео'
}

/**
 * Attaches the episode's media to the <video> element and keeps it alive:
 * network hiccups are retried, expired links are re-resolved and playback resumes at the same position.
 * Every source change fully disposes the previous hls.js instance and media element source.
 */
export function useSource(videoRef: RefObject<HTMLVideoElement | null>, req: SourceRequest, startAt: () => number) {
  const [state, setState] = useState<SourceState>(INITIAL)
  const [attempt, setAttempt] = useState(0)
  const hlsRef = useRef<Hls | null>(null)
  const reresolves = useRef(0)
  const resumeAt = useRef<number | null>(null)
  const startRef = useRef(startAt)
  startRef.current = startAt

  const retry = useCallback((keepPosition = true) => {
    const video = videoRef.current
    resumeAt.current = keepPosition && video && video.currentTime > 1 ? video.currentTime : resumeAt.current
    setAttempt((n) => n + 1)
  }, [videoRef])

  useEffect(() => {
    reresolves.current = 0
    resumeAt.current = null
  }, [req.animeId, req.episode, req.voiceover, req.quality, req.localId])

  useEffect(() => {
    const element = videoRef.current
    if (!element) return
    const video: HTMLVideoElement = element
    const controller = new AbortController()
    let networkRetries = 0
    let mediaRecoveries = 0
    let disposed = false

    const seekToStart = () => {
      const target = resumeAt.current ?? startRef.current()
      resumeAt.current = null
      if (target > 0 && Number.isFinite(video.duration) && target < video.duration - 3) video.currentTime = target
      void video.play().catch(() => {
        /* autoplay may be blocked until the user interacts; controls stay available */
      })
    }

    const fail = (message: string) => {
      if (!disposed) setState((s) => ({ ...s, phase: 'error', error: message }))
    }

    async function attach() {
      setState((s) => ({ ...INITIAL, phase: req.localId ? 'loading' : s.phase === 'error' ? 'resolving' : 'resolving', stream: null }))
      let url: string
      let isHls = false
      if (req.localId && req.localUrl) {
        url = req.localUrl
      } else {
        try {
          const stream = await api.resolveStream(
            { anime_id: req.animeId, episode: req.episode, voiceover: req.voiceover, quality: req.quality, refresh: attempt > 0 },
            controller.signal,
          )
          if (disposed) return
          if (!stream.browser_playable) {
            fail('Этот поток можно только скачать: браузер не воспроизводит формат DASH. Выберите другую озвучку или скачайте серию.')
            return
          }
          url = stream.url
          isHls = stream.type === 'm3u8'
          setState((s) => ({ ...s, stream, phase: 'loading' }))
        } catch (err) {
          if (isAbort(err) || disposed) return
          if (err instanceof ApiError && err.code === 'stream_unavailable') fail(`Ни один плеер не отдал поток. ${err.message}`)
          else fail(errorMessage(err, 'Не удалось получить поток'))
          return
        }
      }

      video.addEventListener('loadedmetadata', seekToStart, { once: true })

      if (isHls && Hls.isSupported()) {
        const hls = new Hls({ enableWorker: true, backBufferLength: 60, maxBufferLength: 45, startLevel: -1 })
        hlsRef.current = hls
        hls.on(Hls.Events.MANIFEST_PARSED, (_e, data) => {
          setState((s) => ({
            ...s,
            levels: data.levels.map((l, i) => ({ id: i, label: l.height ? `${l.height}p` : `${Math.round((l.bitrate || 0) / 1000)} кбит/с` })),
          }))
        })
        hls.on(Hls.Events.LEVEL_SWITCHED, () => setState((s) => ({ ...s, level: hls.autoLevelEnabled ? -1 : hls.currentLevel })))
        hls.on(Hls.Events.AUDIO_TRACKS_UPDATED, (_e, data) =>
          setState((s) => ({ ...s, audioTracks: data.audioTracks.map((t, i) => ({ id: i, label: t.name || t.lang || `Дорожка ${i + 1}` })), audioTrack: hls.audioTrack })),
        )
        hls.on(Hls.Events.SUBTITLE_TRACKS_UPDATED, (_e, data) =>
          setState((s) => ({ ...s, subtitleTracks: data.subtitleTracks.map((t, i) => ({ id: i, label: t.name || t.lang || `Субтитры ${i + 1}` })), subtitleTrack: hls.subtitleTrack })),
        )
        hls.on(Hls.Events.FRAG_LOADED, () => {
          networkRetries = 0
        })
        hls.on(Hls.Events.ERROR, (_e, data) => {
          if (!data.fatal) return
          if (data.type === Hls.ErrorTypes.MEDIA_ERROR && mediaRecoveries < 2) {
            mediaRecoveries += 1
            if (mediaRecoveries === 2) hls.swapAudioCodec()
            hls.recoverMediaError()
            return
          }
          const status = data.response && 'code' in data.response ? Number(data.response.code) : 0
          const expired = status === 410 || status === 502 || status === 403
          if (data.type === Hls.ErrorTypes.NETWORK_ERROR && !expired && networkRetries < MAX_NETWORK_RETRIES) {
            networkRetries += 1
            setState((s) => ({ ...s, phase: 'recovering' }))
            window.setTimeout(() => !disposed && hls.startLoad(), 1000 * 2 ** (networkRetries - 1))
            return
          }
          if (!req.localId && reresolves.current < MAX_RERESOLVES) {
            reresolves.current += 1
            setState((s) => ({ ...s, phase: 'recovering' }))
            resumeAt.current = video.currentTime > 1 ? video.currentTime : resumeAt.current
            setAttempt((n) => n + 1)
            return
          }
          fail(describeHlsError(data))
        })
        hls.loadSource(url)
        hls.attachMedia(video)
      } else {
        video.src = url
        video.load()
      }
    }

    const onNativeError = () => {
      const code = video.error?.code
      if (!video.getAttribute('src') && !hlsRef.current) return
      if (hlsRef.current) return // handled by hls.js
      if (!req.localId && reresolves.current < MAX_RERESOLVES && code !== MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED) {
        reresolves.current += 1
        resumeAt.current = video.currentTime > 1 ? video.currentTime : resumeAt.current
        setAttempt((n) => n + 1)
        return
      }
      fail(
        code === MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED
          ? req.localId
            ? 'Браузер не поддерживает формат этого файла. Откройте его во внешнем плеере (например, VLC).'
            : 'Браузер не поддерживает формат этого потока.'
          : req.localId
            ? 'Файл не читается. Возможно, он был удалён или повреждён.'
            : 'Воспроизведение прервалось.',
      )
    }
    const onReady = () => setState((s) => (s.phase === 'error' ? s : { ...s, phase: 'ready', error: null }))
    video.addEventListener('error', onNativeError)
    video.addEventListener('canplay', onReady)
    void attach()

    return () => {
      disposed = true
      controller.abort()
      video.removeEventListener('error', onNativeError)
      video.removeEventListener('canplay', onReady)
      video.removeEventListener('loadedmetadata', seekToStart)
      hlsRef.current?.destroy()
      hlsRef.current = null
      video.pause()
      video.removeAttribute('src')
      video.load()
    }
  }, [videoRef, req.animeId, req.episode, req.voiceover, req.quality, req.localId, req.localUrl, attempt])

  const setLevel = useCallback((level: number) => {
    const hls = hlsRef.current
    if (!hls) return
    hls.currentLevel = level
    setState((s) => ({ ...s, level }))
  }, [])
  const setAudioTrack = useCallback((id: number) => {
    if (hlsRef.current) hlsRef.current.audioTrack = id
    setState((s) => ({ ...s, audioTrack: id }))
  }, [])
  const setSubtitleTrack = useCallback((id: number) => {
    if (hlsRef.current) {
      hlsRef.current.subtitleTrack = id
      hlsRef.current.subtitleDisplay = id >= 0
    }
    setState((s) => ({ ...s, subtitleTrack: id }))
  }, [])

  return { state, retry, setLevel, setAudioTrack, setSubtitleTrack }
}
