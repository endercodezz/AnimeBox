import { memo } from 'react'
import type { EpisodeInfo } from '../api/types'
import { cx } from '../lib/cx'

export type EpisodeState = {
  progress: number // 0..1
  completed: boolean
  downloaded: boolean
  missing: boolean
  queued: boolean
}

const EMPTY: EpisodeState = { progress: 0, completed: false, downloaded: false, missing: false, queued: false }

function describe(ep: EpisodeInfo, state: EpisodeState): string {
  const parts = [`Серия ${ep.ordinal}`]
  if (ep.title && ep.title !== `Episode ${ep.ordinal}`) parts.push(ep.title)
  if (state.completed) parts.push('просмотрена')
  else if (state.progress > 0) parts.push(`просмотрено ${Math.round(state.progress * 100)}%`)
  if (state.downloaded) parts.push('доступна офлайн')
  else if (state.queued) parts.push('в очереди загрузки')
  return parts.join(', ')
}

const EpisodeTile = memo(function EpisodeTile({ ep, state, selected, onSelect }: {
  ep: EpisodeInfo
  state: EpisodeState
  selected: boolean
  onSelect: (ordinal: number) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(ep.ordinal)}
      aria-pressed={selected}
      aria-label={describe(ep, state)}
      title={describe(ep, state)}
      className={cx(
        'group relative flex h-[60px] flex-col justify-between overflow-hidden rounded-[10px] border px-2.5 pb-2 pt-1.5 text-left transition-[border-color,background,box-shadow] duration-150',
        selected
          ? 'border-violet bg-violet/14 shadow-[0_0_0_1px_rgba(139,108,255,0.6),0_10px_30px_-12px_rgba(139,108,255,0.7)]'
          : 'border-line bg-ink-2 hover:border-white/15 hover:bg-ink-3',
      )}
    >
      {/* Film-strip perforations */}
      <span aria-hidden="true" className="absolute inset-x-2 top-1 flex justify-between opacity-40">
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className="h-[3px] w-[5px] rounded-[1px] bg-white/25" />
        ))}
      </span>
      <span
        className={cx(
          'display tabular mt-1.5 text-[1.15rem] font-semibold leading-none',
          state.completed ? 'text-dim' : selected ? 'text-white' : 'text-paper',
        )}
      >
        {String(ep.ordinal).padStart(2, '0')}
      </span>
      {state.downloaded && (
        <span aria-hidden="true" className="absolute right-0 top-0 h-0 w-0 border-l-[14px] border-t-[14px] border-l-transparent border-t-offline" />
      )}
      {!state.downloaded && state.queued && (
        <span aria-hidden="true" className="absolute right-1.5 top-1.5 size-1.5 animate-pulse rounded-full bg-violet-hi" />
      )}
      <span className="h-[3px] w-full overflow-hidden rounded-full bg-white/[0.08]">
        <span
          className={cx('block h-full rounded-full', state.completed ? 'bg-dim' : 'bg-violet')}
          style={{ width: `${Math.round((state.completed ? 1 : state.progress) * 100)}%` }}
        />
      </span>
    </button>
  )
})

export function EpisodeGrid({ episodes, states, selected, onSelect }: {
  episodes: EpisodeInfo[]
  states: Map<number, EpisodeState>
  selected: number | null
  onSelect: (ordinal: number) => void
}) {
  return (
    <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(76px, 1fr))' }} role="group" aria-label="Серии">
      {episodes.map((ep) => (
        <EpisodeTile key={`${ep.season}-${ep.ordinal}`} ep={ep} state={states.get(ep.ordinal) ?? EMPTY} selected={selected === ep.ordinal} onSelect={onSelect} />
      ))}
    </div>
  )
}

export function EpisodeLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.78rem] text-fog">
      <span className="inline-flex items-center gap-1.5">
        <span className="h-0 w-0 border-l-[9px] border-t-[9px] border-l-transparent border-t-offline" /> офлайн
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-[3px] w-4 rounded-full bg-violet" /> прогресс
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="size-1.5 rounded-full bg-violet-hi" /> в очереди
      </span>
    </div>
  )
}
