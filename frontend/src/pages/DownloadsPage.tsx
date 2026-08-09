import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { DownloadJob } from '../api/types'
import { ProgressBar } from '../components/ProgressBar'

const statusLabel: Record<string, string> = { queued: 'В очереди', downloading: 'Скачивается', completed: 'Готово', failed: 'Ошибка', cancelled: 'Отменено' }

export function DownloadsPage() {
  const [jobs, setJobs] = useState<DownloadJob[]>([])
  const [error, setError] = useState<string | null>(null)
  async function refresh() { try { setJobs(await api.downloads()); setError(null) } catch (err) { setError(err instanceof Error ? err.message : 'Очередь недоступна') } }
  useEffect(() => { void refresh(); const t = setInterval(() => void refresh(), 2000); return () => clearInterval(t) }, [])
  const active = jobs.filter((job) => job.status === 'downloading' || job.status === 'queued').length
  const offlineLink = (job: DownloadJob) =>
    `/anime/${encodeURIComponent(job.anime_external_id)}?local=1`

  return (
    <div className="animate-rise space-y-8">
      <header className="flex flex-col gap-4 border-b border-white/8 pb-7 sm:flex-row sm:items-end sm:justify-between">
        <div><p className="eyebrow">Менеджер очереди</p><h1 className="mt-2 font-display text-4xl font-extrabold tracking-[-0.04em] sm:text-5xl">Загрузки</h1><p className="mt-3 text-fog">Серии сохраняются прямо в локальную библиотеку.</p></div>
        <span className="w-fit rounded-full border border-amber/20 bg-amber/10 px-4 py-2 text-sm font-bold text-violet-soft">{active ? `Активно: ${active}` : 'Очередь спокойна'}</span>
      </header>
      {error && <p className="rounded-xl border border-danger/20 bg-danger/8 p-4 text-danger">{error}</p>}
      {!jobs.length && <div className="surface rounded-3xl px-6 py-16 text-center"><div className="mx-auto grid size-14 place-items-center rounded-2xl bg-amber/12 text-2xl text-violet-soft">↓</div><h2 className="mt-5 font-display text-xl font-bold">Пока ничего не загружается</h2><p className="mt-2 text-sm text-fog">Выберите серию или целый сезон на странице тайтла.</p></div>}
      <ul className="space-y-3">
        {jobs.map((job) => (
          <li key={job.id} className="surface rounded-2xl p-4 transition hover:border-white/14 sm:p-5">
            <div className="flex flex-wrap items-start gap-4">
              <div className="grid size-12 shrink-0 place-items-center rounded-xl bg-amber/12 font-display font-extrabold text-violet-soft">E{job.episode}</div>
              <div className="min-w-0 flex-1">
                <Link to={`/anime/${encodeURIComponent(job.anime_external_id)}`} className="font-display text-lg font-bold hover:text-violet-soft">{job.anime_title}</Link>
                <p className="mt-1 text-xs font-semibold uppercase tracking-[0.1em] text-fog">Сезон {job.season} · Серия {job.episode}{job.voiceover ? ` · ${job.voiceover}` : ''}{job.steam_deck ? ' · Steam Deck' : ''}</p>
              </div>
              <span className={['rounded-full px-3 py-1 text-xs font-bold', job.status === 'completed' ? 'bg-ok/12 text-ok' : job.status === 'failed' ? 'bg-danger/12 text-danger' : job.status === 'downloading' ? 'bg-amber/12 text-violet-soft' : 'bg-white/6 text-fog'].join(' ')}>{statusLabel[job.status] || job.status}</span>
            </div>
            {(job.status === 'downloading' || job.status === 'queued') && <div className="mt-5 flex items-center gap-3"><ProgressBar value={job.progress} className="flex-1" /><span className="w-10 text-right text-xs font-bold text-fog">{Math.round(job.progress)}%</span></div>}
            {job.error && <p className="mt-4 rounded-lg bg-danger/8 p-3 text-xs text-danger">{job.error}</p>}
            <div className="mt-4 flex flex-wrap gap-2">
              {(job.status === 'queued' || job.status === 'downloading') && <button type="button" className="btn-secondary px-3 py-1.5 text-xs" onClick={() => void api.cancelDownload(job.id).then(refresh)}>Отменить</button>}
              {(job.status === 'failed' || job.status === 'cancelled') && <button type="button" className="btn-secondary border-amber/25 px-3 py-1.5 text-xs text-violet-soft" onClick={() => void api.retryDownload(job.id).then(refresh)}>Повторить</button>}
              {job.status === 'completed' && <Link to={offlineLink(job)} className="btn-primary px-4 py-2 text-xs">▶ Смотреть офлайн</Link>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
