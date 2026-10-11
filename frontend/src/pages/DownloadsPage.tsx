import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { DownloadJob, DownloadStatus } from '../api/types'
import { Icon } from '../components/icons'
import { useToast } from '../components/toast'
import { Badge, Button, ButtonLink, EmptyState, Notice, ProgressBar, SectionHeader, Skeleton } from '../components/ui'
import { cx } from '../lib/cx'
import { formatBytes, formatSpeed, relativeDate } from '../lib/format'
import { routes } from '../lib/routes'
import { useInterval, useResource } from '../lib/useResource'

const STATUS: Record<DownloadStatus, { label: string; tone: 'neutral' | 'violet' | 'offline' | 'danger' | 'warn' }> = {
  queued: { label: 'В очереди', tone: 'neutral' },
  resolving: { label: 'Ищем поток', tone: 'violet' },
  downloading: { label: 'Скачивается', tone: 'violet' },
  processing: { label: 'Сжатие для Steam Deck', tone: 'violet' },
  paused: { label: 'На паузе', tone: 'warn' },
  completed: { label: 'Готово', tone: 'offline' },
  failed: { label: 'Ошибка', tone: 'danger' },
  cancelled: { label: 'Отменено', tone: 'neutral' },
}

const ACTIVE: DownloadStatus[] = ['queued', 'resolving', 'downloading', 'processing', 'paused']

function JobRow({ job, onAction, busy }: { job: DownloadJob; onAction: (job: DownloadJob, action: 'cancel' | 'retry' | 'pause' | 'resume' | 'remove') => void; busy: boolean }) {
  const meta = STATUS[job.status]
  const running = job.status === 'downloading' || job.status === 'processing'
  const showProgress = ACTIVE.includes(job.status) && job.status !== 'queued'
  const bytes = job.bytes_total ? `${formatBytes(job.bytes_done)} из ${formatBytes(job.bytes_total)}` : job.bytes_done ? formatBytes(job.bytes_done) : ''
  return (
    <li className="panel p-4 sm:p-5">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
        <span className="display tabular grid size-11 shrink-0 place-items-center rounded-xl bg-white/[0.05] text-[0.95rem] font-semibold">
          {String(job.episode).padStart(2, '0')}
        </span>
        <div className="min-w-0 flex-1">
          <Link to={routes.anime(job.anime_external_id, job.episode)} className="block truncate font-bold hover:text-violet-text">
            {job.anime_title}
          </Link>
          <p className="mt-0.5 truncate text-[0.82rem] text-fog">
            Серия {job.episode}
            {job.voiceover ? ` · ${job.voiceover}` : ' · озвучка по приоритету'}
            {job.player_host ? ` · ${job.player_host}` : ''}
            {job.quality ? ` · ${job.quality}p` : ''}
            {job.steam_deck ? ' · Steam Deck' : ''}
          </p>
        </div>
        <Badge tone={meta.tone}>{meta.label}</Badge>
      </div>

      {showProgress && (
        <div className="mt-4">
          <ProgressBar value={job.progress} label={`Прогресс серии ${job.episode}`} />
          <div className="tabular mt-2 flex flex-wrap justify-between gap-2 text-[0.78rem] text-fog">
            <span>
              {job.progress > 0 ? `${Math.floor(job.progress)}%` : job.status === 'resolving' ? 'подбираем рабочий плеер' : 'ожидание данных'}
              {bytes && ` · ${bytes}`}
            </span>
            <span>{running && formatSpeed(job.speed_bps)}</span>
          </div>
        </div>
      )}

      {job.error && job.status === 'failed' && (
        <p className="mt-3 rounded-lg bg-danger/[0.08] px-3 py-2 text-[0.82rem] leading-5 text-danger">{job.error}</p>
      )}
      {job.warning && <p className="mt-3 rounded-lg bg-warn/[0.08] px-3 py-2 text-[0.82rem] leading-5 text-warn">{job.warning}</p>}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {job.status === 'completed' && (
          <ButtonLink to={routes.anime(job.anime_external_id, job.episode)} size="sm" variant="primary" icon="play">
            Открыть
          </ButtonLink>
        )}
        {job.resumable && (job.status === 'downloading' || job.status === 'queued') && (
          <Button size="sm" icon="pause" disabled={busy} onClick={() => onAction(job, 'pause')}>
            Пауза
          </Button>
        )}
        {job.status === 'paused' && (
          <Button size="sm" variant="primary" icon="play" disabled={busy} onClick={() => onAction(job, 'resume')}>
            Продолжить
          </Button>
        )}
        {ACTIVE.includes(job.status) && (
          <Button size="sm" variant="ghost" icon="close" disabled={busy} onClick={() => onAction(job, 'cancel')}>
            Отменить
          </Button>
        )}
        {(job.status === 'failed' || job.status === 'cancelled') && (
          <Button size="sm" icon="retry" disabled={busy} onClick={() => onAction(job, 'retry')}>
            Повторить
          </Button>
        )}
        {!ACTIVE.includes(job.status) && (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => onAction(job, 'remove')}>
            Убрать из списка
          </Button>
        )}
        <span className="ml-auto text-[0.75rem] text-dim">
          {job.attempts > 1 && `попыток: ${job.attempts} · `}
          {relativeDate(job.finished_at || job.updated_at)}
        </span>
      </div>
    </li>
  )
}

export function DownloadsPage() {
  const toast = useToast()
  const jobs = useResource((signal) => api.downloads('all', signal), [])
  const [busyId, setBusyId] = useState<number | null>(null)
  const [clearing, setClearing] = useState(false)
  const list = jobs.data ?? []
  const active = list.filter((j) => ACTIVE.includes(j.status)).sort((a, b) => a.id - b.id)
  const finished = list.filter((j) => !ACTIVE.includes(j.status))
  const running = active.filter((j) => j.status !== 'paused' && j.status !== 'queued')
  const totalSpeed = running.reduce((sum, j) => sum + (j.speed_bps || 0), 0)

  useInterval(jobs.reload, active.length ? 1500 : 6000)

  async function act(job: DownloadJob, action: 'cancel' | 'retry' | 'pause' | 'resume' | 'remove') {
    setBusyId(job.id)
    try {
      if (action === 'remove') await api.removeDownload(job.id)
      else await api.downloadAction(job.id, action)
      jobs.reload()
    } catch (err) {
      toast.show(errorMessage(err), 'error')
    } finally {
      setBusyId(null)
    }
  }

  async function clear() {
    setClearing(true)
    try {
      await api.clearDownloads()
      jobs.reload()
    } catch (err) {
      toast.show(errorMessage(err), 'error')
    } finally {
      setClearing(false)
    }
  }

  return (
    <div className="page space-y-9">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="display text-[1.7rem] font-semibold sm:text-[2rem]">Загрузки</h1>
          <p className="mt-2 text-fog">Готовые серии сразу попадают в библиотеку.</p>
        </div>
        {running.length > 0 && (
          <p className="tabular inline-flex items-center gap-2 text-[0.9rem] text-fog">
            <Icon name="download" size={16} className="text-violet-text" />
            Скачивается {running.length} · {formatSpeed(totalSpeed) || 'ожидание'}
          </p>
        )}
      </header>

      {jobs.error ? <Notice title="Очередь недоступна">{errorMessage(jobs.error)}</Notice> : null}
      {jobs.loading && !jobs.data && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 rounded-[var(--radius-card)]" />
          ))}
        </div>
      )}

      {jobs.data && list.length === 0 && (
        <EmptyState icon="download" title="Загрузок пока нет" action={<ButtonLink to={routes.search()} variant="primary" icon="search">Найти аниме</ButtonLink>}>
          На странице тайтла выберите серию и нажмите «Скачать серию» — или скачайте весь сезон сразу.
        </EmptyState>
      )}

      {active.length > 0 && (
        <section>
          <SectionHeader title="Очередь" meta="Прямые MP4-файлы можно ставить на паузу; HLS-потоки при остановке начинаются заново." />
          <ul className="space-y-3">
            {active.map((job) => (
              <JobRow key={job.id} job={job} onAction={(j, a) => void act(j, a)} busy={busyId === job.id} />
            ))}
          </ul>
        </section>
      )}

      {finished.length > 0 && (
        <section>
          <SectionHeader
            title="История"
            action={
              <Button size="sm" variant="ghost" loading={clearing} onClick={() => void clear()}>
                Очистить историю
              </Button>
            }
          />
          <ul className={cx('space-y-3')}>
            {finished.map((job) => (
              <JobRow key={job.id} job={job} onAction={(j, a) => void act(j, a)} busy={busyId === job.id} />
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
