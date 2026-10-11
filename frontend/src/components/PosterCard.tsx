import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { usePrefs } from '../lib/prefs'
import { Icon } from './icons'
import { Skeleton } from './ui'
import { cx } from '../lib/cx'

function PosterImage({ src, title }: { src: string | null | undefined; title: string }) {
  const [failed, setFailed] = useState(false)
  if (!src || failed) {
    return (
      <div className="flex h-full w-full items-end bg-[radial-gradient(120%_80%_at_80%_0%,rgba(139,108,255,0.28),transparent_60%),#1a1724] p-3">
        <span className="display line-clamp-3 text-[1.05rem] font-semibold leading-tight text-white/30">{title}</span>
      </div>
    )
  }
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="h-full w-full object-cover transition-transform duration-500 ease-out group-hover:scale-[1.04]"
    />
  )
}

export function PosterCard({ to, title, poster, meta, badge, progress }: {
  to: string
  title: string
  poster?: string | null
  meta?: ReactNode
  badge?: ReactNode
  progress?: number
}) {
  return (
    <Link to={to} className="group block rounded-[var(--radius-card)] outline-offset-4">
      <div className="relative aspect-[2/3] overflow-hidden rounded-[var(--radius-card)] bg-ink-3 ring-1 ring-line transition-shadow duration-300 group-hover:shadow-[var(--shadow-glow)] group-focus-visible:shadow-[var(--shadow-glow)]">
        <PosterImage src={poster} title={title} />
        {/* Light leak from the top edge on hover: the "projector" moment of the card. */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-1/2 bg-[linear-gradient(180deg,rgba(164,141,255,0.32),transparent)] opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
        {badge && <div className="absolute left-2 top-2 flex flex-wrap gap-1">{badge}</div>}
        <span className="absolute bottom-2.5 right-2.5 grid size-9 translate-y-1 place-items-center rounded-full bg-violet text-white opacity-0 shadow-lg transition duration-200 group-hover:translate-y-0 group-hover:opacity-100">
          <Icon name="play" size={16} />
        </span>
        {progress !== undefined && progress > 0 && (
          <div className="absolute inset-x-0 bottom-0 h-1 bg-black/50">
            <div className="h-full bg-violet" style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
        )}
      </div>
      <div className="mt-2.5 px-0.5">
        <h3 className="line-clamp-2 text-[0.9rem] font-semibold leading-snug text-paper group-hover:text-white">{title}</h3>
        {meta && <div className="mt-1 text-[0.78rem] text-fog">{meta}</div>}
      </div>
    </Link>
  )
}

export function PosterGrid({ children, className }: { children: ReactNode; className?: string }) {
  const { compactGrid } = usePrefs()
  return (
    <div
      className={cx('grid gap-x-4 gap-y-6', className)}
      style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${compactGrid ? 128 : 158}px, 1fr))` }}
    >
      {children}
    </div>
  )
}

export function PosterGridSkeleton({ count = 12 }: { count?: number }) {
  return (
    <PosterGrid>
      {Array.from({ length: count }, (_, i) => (
        <div key={i}>
          <Skeleton className="aspect-[2/3] rounded-[var(--radius-card)]" />
          <Skeleton className="mt-3 h-3.5 w-4/5" />
          <Skeleton className="mt-2 h-3 w-1/3" />
        </div>
      ))}
    </PosterGrid>
  )
}
