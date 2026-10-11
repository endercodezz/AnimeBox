import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiError, errorMessage } from '../api/client'
import type { AnimeDetail, DownloadJob, LibraryEpisode, VoiceoverOption, WatchHistory } from '../api/types'
import { EpisodeGrid, EpisodeLegend, type EpisodeState } from '../components/EpisodeGrid'
import { Icon } from '../components/icons'
import { useToast } from '../components/toast'
import { Badge, Button, ButtonLink, ConfirmDialog, EmptyState, Notice, Skeleton, Spinner } from '../components/ui'
import { cx } from '../lib/cx'
import { episodesLabel, formatBytes, formatTime, plural, progressRatio } from '../lib/format'
import { canonicalId } from '../lib/ids'
import { routes } from '../lib/routes'
import { useInterval, useResource } from '../lib/useResource'

type Loaded = {
  detail: AnimeDetail | null
  detailError: unknown
  local: LibraryEpisode[]
  history: WatchHistory[]
  offlineTitle: { title: string; poster: string | null } | null
}

async function loadAll(id: string, signal: AbortSignal): Promise<Loaded> {
  const [detail, local, history] = await Promise.allSettled([
    api.anime(id, signal),
    api.libraryEpisodes(id, signal),
    api.animeHistory(id, signal),
  ])
  const localEps = local.status === 'fulfilled' ? local.value : []
  let offlineTitle: Loaded['offlineTitle'] = null
  if (detail.status === 'rejected' && localEps.length) {
    const item = (await api.library(signal).catch(() => [])).find((x) => x.id === id)
    if (item) offlineTitle = { title: item.title, poster: item.poster }
  }
  return {
    detail: detail.status === 'fulfilled' ? detail.value : null,
    detailError: detail.status === 'rejected' ? detail.reason : null,
    local: localEps,
    history: history.status === 'fulfilled' ? history.value : [],
    offlineTitle,
  }
}

function VoiceoverPicker({ options, value, onChange, loading, error }: {
  options: VoiceoverOption[]
  value: string
  onChange: (value: string) => void
  loading: boolean
  error: unknown
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <p className="eyebrow">Озвучка</p>
        {loading && <Spinner size={12} className="text-fog" />}
      </div>
      {error ? (
        <p className="text-[0.85rem] text-danger">{errorMessage(error, 'Список озвучек недоступен')}</p>
      ) : (
        <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Озвучка">
          {[{ title: '', label: 'Авто', hint: 'по приоритетам из настроек' }, ...options.map((o) => ({ title: o.title, label: o.title, hint: o.players.join(', '), kind: o.kind }))].map(
            (option) => (
              <button
                key={option.title || 'auto'}
                type="button"
                role="radio"
                aria-checked={value === option.title}
                title={option.hint ? `Плееры: ${option.hint}` : undefined}
                onClick={() => onChange(option.title)}
                className={cx(
                  'inline-flex h-9 items-center gap-1.5 rounded-lg border px-3 text-[0.85rem] font-semibold transition-colors',
                  value === option.title ? 'border-violet/70 bg-violet/16 text-paper' : 'border-line text-fog hover:border-white/15 hover:text-paper',
                )}
              >
                {option.label}
                {'kind' in option && option.kind === 'subtitles' && <span className="text-[0.7rem] text-violet-text">SUB</span>}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  )
}

export function AnimePage() {
  const { id: rawId = '' } = useParams()
  const id = canonicalId(rawId)
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const page = useResource((signal) => loadAll(id, signal), [id])
  const [jobs, setJobs] = useState<DownloadJob[]>([])
  const [voice, setVoice] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<LibraryEpisode | null>(null)
  const [expanded, setExpanded] = useState(false)

  const data = page.data
  const offline = Boolean(data && !data.detail && data.local.some((e) => e.available))
  const episodes = useMemo(() => {
    if (data?.detail) return data.detail.episodes
    return (data?.local ?? []).filter((e) => e.available).map((e) => ({ ordinal: e.episode, season: e.season, title: e.title || `Episode ${e.episode}` }))
  }, [data])

  const refreshJobs = () =>
    api
      .downloads('active')
      .then((list) => setJobs(list.filter((j) => j.anime_external_id === (data?.detail?.id ?? id))))
      .catch(() => {})
  useEffect(() => {
    void refreshJobs()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, data?.detail?.id])
  useInterval(() => {
    if (jobs.length) {
      void refreshJobs()
      page.reload()
    }
  }, jobs.length ? 4000 : null)

  const localByEpisode = useMemo(() => new Map((data?.local ?? []).map((e) => [e.episode, e])), [data])
  const historyByEpisode = useMemo(() => new Map((data?.history ?? []).map((h) => [h.episode, h])), [data])
  const queued = useMemo(() => new Set(jobs.map((j) => j.episode)), [jobs])

  const states = useMemo(() => {
    const map = new Map<number, EpisodeState>()
    for (const ep of episodes) {
      const h = historyByEpisode.get(ep.ordinal)
      const local = localByEpisode.get(ep.ordinal)
      map.set(ep.ordinal, {
        progress: h ? progressRatio(h.progress_seconds, h.duration_seconds) : 0,
        completed: Boolean(h?.completed || local?.completed),
        downloaded: Boolean(local?.available),
        missing: Boolean(local && !local.available),
        queued: queued.has(ep.ordinal),
      })
    }
    return map
  }, [episodes, historyByEpisode, localByEpisode, queued])

  // The episode to resume: latest unfinished history entry, else the first unwatched one.
  const resume = useMemo(() => {
    const unfinished = [...(data?.history ?? [])]
      .filter((h) => !h.completed && h.progress_seconds > 5)
      .sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''))[0]
    if (unfinished && episodes.some((e) => e.ordinal === unfinished.episode)) return unfinished.episode
    const next = episodes.find((e) => !states.get(e.ordinal)?.completed)
    return next?.ordinal ?? episodes[0]?.ordinal ?? null
  }, [data, episodes, states])

  const selected = Number(params.get('episode')) || resume
  const selectedEpisode = episodes.find((e) => e.ordinal === selected) ?? null
  const selectedLocal = selected ? localByEpisode.get(selected) : undefined
  const selectedHistory = selected ? historyByEpisode.get(selected) : undefined

  const voiceovers = useResource(
    (signal) => api.voiceovers(data?.detail?.id ?? id, selected ?? 1, signal),
    [data?.detail?.id, selected],
    Boolean(data?.detail && selected !== null),
  )
  const lastVoice = useMemo(
    () => [...(data?.history ?? [])].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''))[0]?.voiceover ?? '',
    [data],
  )
  const voiceValue = voice ?? (lastVoice && voiceovers.data?.some((v) => v.title === lastVoice) ? lastVoice : '')

  function select(ordinal: number) {
    const next = new URLSearchParams(params)
    next.set('episode', String(ordinal))
    setParams(next, { replace: true })
  }

  function play(ordinal: number, preferLocal = true) {
    const local = localByEpisode.get(ordinal)
    const animeId = data?.detail?.id ?? id
    navigate(
      routes.player(animeId, {
        episode: ordinal,
        voiceover: preferLocal && local?.available ? null : voiceValue || null,
        local: preferLocal && local?.available ? local.id : null,
      }),
    )
  }

  async function download(episodesToGet: number[] | null, replace = false) {
    if (!data?.detail) return
    setBusy(episodesToGet ? `ep-${episodesToGet[0]}` : 'season')
    try {
      const result = await api.createDownloads({
        anime_id: data.detail.id,
        episodes: episodesToGet,
        voiceover: voiceValue || null,
        replace,
      })
      const added = result.jobs.length
      const skipped = result.skipped.length
      if (added) {
        toast.show(
          `${added} ${plural(added, 'серия добавлена', 'серии добавлены', 'серий добавлено')} в загрузки${skipped ? `, ${skipped} уже скачано или в очереди` : ''}`,
          'success',
          { label: 'Открыть', onClick: () => navigate(routes.downloads()) },
        )
      } else {
        toast.show(skipped ? 'Эти серии уже скачаны или стоят в очереди' : 'Нечего скачивать', 'info')
      }
      await refreshJobs()
    } catch (err) {
      toast.show(errorMessage(err, 'Не удалось добавить в загрузки'), 'error')
    } finally {
      setBusy(null)
    }
  }

  async function deleteLocal(ep: LibraryEpisode) {
    setBusy('delete')
    try {
      await api.deleteLibraryEpisode(ep.id)
      toast.show(`Файл серии ${ep.episode} удалён`)
      page.reload()
    } catch (err) {
      toast.show(errorMessage(err), 'error')
    } finally {
      setBusy(null)
      setConfirmDelete(null)
    }
  }

  if (page.loading && !data) {
    return (
      <div className="page">
        <div className="flex flex-col gap-8 sm:flex-row">
          <Skeleton className="aspect-[2/3] w-[200px] rounded-[var(--radius-card)]" />
          <div className="flex-1 space-y-4 pt-4">
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-20 w-full max-w-2xl" />
          </div>
        </div>
        <div className="mt-10 grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(76px, 1fr))' }}>
          {Array.from({ length: 24 }, (_, i) => (
            <Skeleton key={i} className="h-[60px] rounded-[10px]" />
          ))}
        </div>
      </div>
    )
  }

  if (data && !data.detail && !offline) {
    const err = data.detailError
    const expired = err instanceof ApiError && err.code === 'search_expired'
    return (
      <div className="page">
        <EmptyState
          icon="alert"
          title={expired ? 'Данные тайтла устарели' : 'Тайтл не открылся'}
          action={
            <>
              <Button icon="retry" onClick={page.reload}>
                Повторить
              </Button>
              <ButtonLink to={routes.search()} variant="primary" icon="search">
                Найти заново
              </ButtonLink>
            </>
          }
        >
          {expired ? 'Источник больше не узнаёт этот тайтл по сохранённым данным. Найдите его поиском ещё раз.' : errorMessage(err)}
        </EmptyState>
      </div>
    )
  }

  if (!data) return null
  const title = data.detail?.title ?? data.offlineTitle?.title ?? 'Без названия'
  const poster = data.detail?.poster ?? data.offlineTitle?.poster ?? null
  const downloadedCount = data.local.filter((e) => e.available).length
  const description = data.detail?.description

  return (
    <div className="pb-24 lg:pb-16">
      <section className="relative isolate overflow-hidden border-b border-line">
        {poster && <img src={poster} alt="" aria-hidden="true" referrerPolicy="no-referrer" className="absolute inset-0 -z-20 h-full w-full scale-110 object-cover opacity-40 blur-2xl" />}
        <div className="scrim-bottom absolute inset-0 -z-10" />
        <div className="mx-auto flex max-w-[1480px] flex-col gap-7 px-4 pb-9 pt-8 sm:flex-row sm:px-6 lg:px-10 lg:pt-12">
          <div className="w-[150px] shrink-0 overflow-hidden rounded-[var(--radius-card)] bg-ink-3 shadow-[var(--shadow-lift)] ring-1 ring-white/10 sm:w-[210px]">
            {poster ? (
              <img src={poster} alt={`Постер: ${title}`} referrerPolicy="no-referrer" className="aspect-[2/3] w-full object-cover" />
            ) : (
              <div className="grid aspect-[2/3] place-items-center text-dim">
                <Icon name="film" size={36} />
              </div>
            )}
          </div>
          <div className="enter flex min-w-0 flex-1 flex-col justify-end">
            <div className="flex flex-wrap gap-1.5">
              {data.detail && <Badge>{data.detail.source_label || data.detail.source}</Badge>}
              {data.detail?.year && <Badge>{data.detail.year}</Badge>}
              <Badge>{episodesLabel(episodes.length)}</Badge>
              {downloadedCount > 0 && (
                <Badge tone="offline">
                  <Icon name="offline" size={12} /> офлайн: {downloadedCount}
                </Badge>
              )}
            </div>
            <h1 className="display mt-4 max-w-4xl text-[1.9rem] font-semibold leading-[1.08] sm:text-[2.6rem]">{title}</h1>
            {description && (
              <div className="mt-4 max-w-3xl">
                <p className={cx('text-[0.95rem] leading-7 text-paper/75', !expanded && 'line-clamp-3')}>{description}</p>
                {description.length > 240 && (
                  <button type="button" onClick={() => setExpanded((v) => !v)} className="mt-1 text-[0.85rem] font-semibold text-violet-text hover:text-paper">
                    {expanded ? 'Свернуть' : 'Читать полностью'}
                  </button>
                )}
              </div>
            )}
            <div className="mt-6 flex flex-wrap gap-2">
              {resume !== null && (
                <Button variant="primary" size="lg" icon="play" onClick={() => play(resume)}>
                  {historyByEpisode.get(resume)?.progress_seconds ? `Продолжить серию ${resume}` : `Смотреть серию ${resume}`}
                </Button>
              )}
              {data.detail && episodes.length > 1 && (
                <Button size="lg" icon="download" loading={busy === 'season'} onClick={() => void download(null)}>
                  Скачать сезон
                </Button>
              )}
            </div>
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-[1480px] space-y-6 px-4 pt-8 sm:px-6 lg:px-10">
        {offline && (
          <Notice tone="info" title="Источник недоступен — показаны скачанные серии">
            {errorMessage(data.detailError)}. Офлайн-просмотр работает без интернета.
          </Notice>
        )}

        <div className="grid gap-8 xl:grid-cols-[1fr_380px]">
          <section aria-labelledby="episodes-title">
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <h2 id="episodes-title" className="display text-[1.2rem] font-semibold">
                Серии
              </h2>
              <EpisodeLegend />
            </div>
            {episodes.length ? (
              <EpisodeGrid episodes={episodes} states={states} selected={selected} onSelect={select} />
            ) : (
              <p className="text-fog">Источник пока не опубликовал серии этого тайтла.</p>
            )}
          </section>

          {selectedEpisode && (
            <aside className="panel h-fit space-y-5 p-5 xl:sticky xl:top-24" aria-label={`Серия ${selectedEpisode.ordinal}`}>
              <div>
                <p className="eyebrow">Серия {selectedEpisode.ordinal}</p>
                <h3 className="mt-1.5 text-[1.05rem] font-bold leading-snug">
                  {selectedEpisode.title && selectedEpisode.title !== `Episode ${selectedEpisode.ordinal}` ? selectedEpisode.title : `Серия ${selectedEpisode.ordinal}`}
                </h3>
                {selectedHistory && selectedHistory.progress_seconds > 0 && (
                  <p className="tabular mt-1 text-[0.83rem] text-fog">
                    {selectedHistory.completed ? 'Просмотрена' : `Остановились на ${formatTime(selectedHistory.progress_seconds)}`}
                  </p>
                )}
              </div>

              {data.detail && (
                <VoiceoverPicker options={voiceovers.data ?? []} value={voiceValue} onChange={setVoice} loading={voiceovers.loading} error={voiceovers.error} />
              )}

              <div className="flex flex-col gap-2">
                {selectedLocal?.available && (
                  <Button variant="primary" icon="play" onClick={() => play(selectedEpisode.ordinal, true)}>
                    Смотреть офлайн
                  </Button>
                )}
                {data.detail && (
                  <Button variant={selectedLocal?.available ? 'secondary' : 'primary'} icon="play" onClick={() => play(selectedEpisode.ordinal, false)}>
                    Смотреть онлайн
                  </Button>
                )}
                {data.detail &&
                  (queued.has(selectedEpisode.ordinal) ? (
                    <ButtonLink to={routes.downloads()} icon="download">
                      В очереди загрузки
                    </ButtonLink>
                  ) : selectedLocal?.available ? (
                    <Button icon="retry" loading={busy === `ep-${selectedEpisode.ordinal}`} onClick={() => void download([selectedEpisode.ordinal], true)}>
                      Скачать заново{voiceValue ? ` · ${voiceValue}` : ''}
                    </Button>
                  ) : (
                    <Button icon="download" loading={busy === `ep-${selectedEpisode.ordinal}`} onClick={() => void download([selectedEpisode.ordinal])}>
                      Скачать серию
                    </Button>
                  ))}
              </div>

              {selectedLocal && (
                <div className="border-t border-line pt-4 text-[0.83rem] text-fog">
                  {selectedLocal.available ? (
                    <div className="flex items-center justify-between gap-3">
                      <span className="tabular">
                        На диске · {formatBytes(selectedLocal.file_size)}
                        {selectedLocal.voiceover ? ` · ${selectedLocal.voiceover}` : ''}
                        {selectedLocal.quality ? ` · ${selectedLocal.quality}p` : ''}
                      </span>
                      <button type="button" className="font-semibold text-fog hover:text-danger" onClick={() => setConfirmDelete(selectedLocal)}>
                        Удалить файл
                      </button>
                    </div>
                  ) : (
                    <p className="text-warn">Файл этой серии был удалён или перемещён. Скачайте её снова или пересканируйте библиотеку в настройках.</p>
                  )}
                </div>
              )}
            </aside>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmDelete !== null}
        title={`Удалить файл серии ${confirmDelete?.episode ?? ''}?`}
        confirmLabel="Удалить"
        busy={busy === 'delete'}
        onConfirm={() => confirmDelete && void deleteLocal(confirmDelete)}
        onCancel={() => setConfirmDelete(null)}
      >
        Видеофайл будет удалён с диска. История просмотра сохранится.
      </ConfirmDialog>
    </div>
  )
}
