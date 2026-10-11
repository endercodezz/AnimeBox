import { Link } from 'react-router-dom'
import type { WatchHistory } from '../api/types'
import { formatTime, progressRatio } from '../lib/format'
import { continueTarget } from '../lib/routes'
import { Icon } from './icons'

/** Landscape card with the poster as a blurred backdrop — used in "Продолжить просмотр". */
export function ContinueCard({ item }: { item: WatchHistory }) {
  const ratio = progressRatio(item.progress_seconds, item.duration_seconds)
  return (
    <Link
      to={continueTarget(item)}
      className="group relative flex h-[118px] overflow-hidden rounded-[var(--radius-card)] border border-line bg-ink-2 transition-[border-color,box-shadow] hover:border-violet/50 hover:shadow-[var(--shadow-glow)]"
    >
      {item.poster && (
        <img src={item.poster} alt="" aria-hidden="true" loading="lazy" referrerPolicy="no-referrer" className="absolute inset-0 h-full w-full scale-125 object-cover opacity-25 blur-2xl" />
      )}
      <div className="relative w-[80px] shrink-0 overflow-hidden bg-ink-3">
        {item.poster && <img src={item.poster} alt="" loading="lazy" referrerPolicy="no-referrer" className="h-full w-full object-cover" />}
      </div>
      <div className="relative flex min-w-0 flex-1 flex-col justify-between p-3.5">
        <div className="min-w-0">
          <p className="truncate text-[0.95rem] font-bold">{item.anime_title}</p>
          <p className="mt-0.5 truncate text-[0.8rem] text-fog">
            Серия {item.episode}
            {item.voiceover ? ` · ${item.voiceover}` : ''}
            {item.local_episode_id ? ' · офлайн' : ''}
          </p>
        </div>
        <div>
          <div className="tabular mb-1.5 flex justify-between text-[0.75rem] text-fog">
            <span>{formatTime(item.progress_seconds)}</span>
            <span>{item.duration_seconds ? formatTime(item.duration_seconds) : ''}</span>
          </div>
          <div className="h-1 overflow-hidden rounded-full bg-white/10">
            <div className="h-full rounded-full bg-violet" style={{ width: `${Math.round(ratio * 100)}%` }} />
          </div>
        </div>
      </div>
      <span className="relative mr-3 grid size-10 shrink-0 self-center place-items-center rounded-full bg-white/[0.08] text-paper transition group-hover:bg-violet group-hover:text-white">
        <Icon name="play" size={16} />
      </span>
    </Link>
  )
}
