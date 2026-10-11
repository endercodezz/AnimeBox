import { useEffect, useRef, type ReactNode } from 'react'
import { Icon } from '../../components/icons'
import { cx } from '../../lib/cx'

export type MenuItem = { key: string; label: ReactNode; hint?: ReactNode; active?: boolean; disabled?: boolean; onSelect: () => void }

/** Popover menu anchored above the control bar. Closes on Escape / outside click. */
export function PlayerMenu({ title, items, onClose, empty }: { title: string; items: MenuItem[]; onClose: () => void; empty?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const first = ref.current?.querySelector<HTMLButtonElement>('button[aria-checked="true"], button:not([disabled])')
    first?.focus()
    const onDown = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose()
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('pointerdown', onDown, true)
    window.addEventListener('keydown', onKey, true)
    return () => {
      window.removeEventListener('pointerdown', onDown, true)
      window.removeEventListener('keydown', onKey, true)
    }
  }, [onClose])

  return (
    <div
      ref={ref}
      role="menu"
      aria-label={title}
      className="glass absolute bottom-[calc(100%+12px)] right-0 z-20 max-h-[min(60vh,420px)] w-[min(300px,calc(100vw-24px))] overflow-y-auto rounded-xl border border-white/10 p-1.5 shadow-[0_20px_60px_rgba(0,0,0,0.6)]"
    >
      <p className="eyebrow px-2.5 pb-1.5 pt-1">{title}</p>
      {items.length === 0 && <p className="px-2.5 py-2 text-[0.85rem] text-fog">{empty ?? 'Нет вариантов'}</p>}
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          role="menuitemradio"
          aria-checked={Boolean(item.active)}
          disabled={item.disabled}
          onClick={() => {
            item.onSelect()
            onClose()
          }}
          className={cx(
            'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[0.88rem] transition-colors disabled:opacity-40',
            item.active ? 'bg-violet/18 text-paper' : 'text-paper/85 hover:bg-white/[0.07]',
          )}
        >
          <span className="w-4 shrink-0 text-violet-text">{item.active && <Icon name="check" size={16} />}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate font-semibold">{item.label}</span>
            {item.hint && <span className="block truncate text-[0.75rem] text-fog">{item.hint}</span>}
          </span>
        </button>
      ))}
    </div>
  )
}
