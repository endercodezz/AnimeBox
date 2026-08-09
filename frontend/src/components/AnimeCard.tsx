import { Link } from 'react-router-dom'

type Props = {
  id: string
  title: string
  poster?: string | null
  year?: number | null
  source?: string
  subtitle?: string
  to?: string
}

export function AnimeCard({ id, title, poster, year, source, subtitle, to }: Props) {
  const href = to || `/anime/${encodeURIComponent(id)}`
  return (
    <Link
      to={href}
      className="group relative block overflow-hidden rounded-2xl bg-ink-3 ring-1 ring-white/7 transition duration-300 hover:-translate-y-1.5 hover:ring-amber/70 hover:shadow-[0_22px_60px_rgba(67,35,115,0.45)]"
    >
      <div className="aspect-[2/3] overflow-hidden bg-ink-4">
        {poster ? (
          <img
            src={poster}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover transition duration-700 group-hover:scale-[1.055]"
          />
        ) : (
          <div className="flex h-full items-end bg-[radial-gradient(circle_at_70%_20%,rgba(139,92,246,0.38),transparent_45%)] p-4 font-display text-6xl font-bold text-white/12">
            {title.slice(0, 1)}
          </div>
        )}
        <div className="poster-shine absolute inset-0" />
        <div className="absolute inset-x-0 top-0 flex items-start justify-between gap-2 p-3 opacity-0 transition duration-300 group-hover:opacity-100 group-focus-visible:opacity-100">
          {source && (
            <span className="rounded-full border border-white/12 bg-black/65 px-2 py-1 text-[0.6rem] font-bold uppercase tracking-wider text-white backdrop-blur">
              {source}
            </span>
          )}
          <span className="ml-auto grid size-8 place-items-center rounded-full bg-amber text-sm text-white shadow-lg">▶</span>
        </div>
      </div>
      <div className="absolute inset-x-0 bottom-0 space-y-1 p-3.5 sm:p-4">
        <h3 className="line-clamp-2 font-display text-sm font-bold leading-snug text-paper sm:text-base">
          {title}
        </h3>
        <p className="min-h-4 text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-fog/80">
          {[year, subtitle].filter(Boolean).join(' · ') || source}
        </p>
      </div>
    </Link>
  )
}
