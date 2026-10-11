import { useEffect, useId, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { ProviderStatus } from '../api/types'
import { cx } from '../lib/cx'
import { Icon, type IconName } from './icons'



type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

const variantClass: Record<Variant, string> = {
  primary:
    'bg-violet text-white shadow-[0_8px_26px_-10px_rgba(139,108,255,0.9)] hover:bg-violet-hi active:bg-violet-lo disabled:bg-violet/45 disabled:shadow-none',
  secondary: 'border border-line bg-white/[0.04] text-paper hover:border-white/15 hover:bg-white/[0.08] disabled:opacity-50',
  ghost: 'text-fog hover:bg-white/[0.06] hover:text-paper disabled:opacity-40',
  danger: 'border border-danger/25 bg-danger/10 text-danger hover:bg-danger/18 disabled:opacity-50',
}

const sizeClass: Record<Size, string> = {
  sm: 'h-8 gap-1.5 rounded-lg px-3 text-[0.82rem]',
  md: 'h-10 gap-2 rounded-xl px-4 text-[0.9rem]',
  lg: 'h-12 gap-2.5 rounded-xl px-5 text-[0.98rem]',
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  size?: Size
  icon?: IconName
  loading?: boolean
}

export function Button({ variant = 'secondary', size = 'md', icon, loading, className, children, disabled, ...props }: ButtonProps) {
  return (
    <button
      type="button"
      {...props}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx(
        'inline-flex shrink-0 select-none items-center justify-center whitespace-nowrap font-semibold transition-[background,border-color,color,box-shadow] duration-150',
        variantClass[variant],
        sizeClass[size],
        className,
      )}
    >
      {loading ? <Spinner size={size === 'sm' ? 14 : 16} /> : icon ? <Icon name={icon} size={size === 'sm' ? 15 : 18} /> : null}
      {children}
    </button>
  )
}

export function ButtonLink({ to, variant = 'secondary', size = 'md', icon, className, children }: {
  to: string
  variant?: Variant
  size?: Size
  icon?: IconName
  className?: string
  children: ReactNode
}) {
  return (
    <Link
      to={to}
      className={cx(
        'inline-flex shrink-0 items-center justify-center whitespace-nowrap font-semibold transition-[background,border-color,color] duration-150',
        variantClass[variant],
        sizeClass[size],
        className,
      )}
    >
      {icon && <Icon name={icon} size={size === 'sm' ? 15 : 18} />}
      {children}
    </Link>
  )
}

export function IconButton({ icon, label, size = 40, className, active, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: IconName
  label: string
  size?: number
  active?: boolean
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      {...props}
      style={{ width: size, height: size }}
      className={cx(
        'inline-grid shrink-0 place-items-center rounded-xl transition-colors duration-150 disabled:opacity-40',
        active ? 'bg-violet/20 text-violet-text' : 'text-fog hover:bg-white/[0.07] hover:text-paper',
        className,
      )}
    >
      <Icon name={icon} size={Math.round(size * 0.5)} />
    </button>
  )
}

export function Spinner({ size = 18, className }: { size?: number; className?: string }) {
  return (
    <span
      role="status"
      aria-label="Загрузка"
      className={cx('inline-block shrink-0 rounded-full border-2 border-current border-r-transparent', className)}
      style={{ width: size, height: size, animation: 'spin 0.7s linear infinite' }}
    />
  )
}

type Tone = 'neutral' | 'violet' | 'offline' | 'danger' | 'warn'
const toneClass: Record<Tone, string> = {
  neutral: 'bg-white/[0.06] text-fog',
  violet: 'bg-violet/16 text-violet-text',
  offline: 'bg-offline/12 text-offline',
  danger: 'bg-danger/12 text-danger',
  warn: 'bg-warn/12 text-warn',
}

export function Badge({ tone = 'neutral', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cx('inline-flex h-6 items-center gap-1 rounded-md px-2 text-[0.72rem] font-bold tracking-wide', toneClass[tone], className)}>
      {children}
    </span>
  )
}

export function ProgressBar({ value, className, tone = 'violet', label }: { value: number; className?: string; tone?: 'violet' | 'offline' | 'danger'; label?: string }) {
  const pct = Math.max(0, Math.min(100, value))
  const fill = tone === 'offline' ? 'bg-offline' : tone === 'danger' ? 'bg-danger' : 'bg-violet'
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
      aria-label={label}
      className={cx('h-1.5 overflow-hidden rounded-full bg-white/[0.08]', className)}
    >
      <div className={cx('h-full rounded-full transition-[width] duration-500 ease-out', fill)} style={{ width: `${pct}%` }} />
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx('skeleton rounded-lg', className)} aria-hidden="true" />
}

export function EmptyState({ icon, title, children, action }: { icon: IconName; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="panel flex flex-col items-center px-6 py-14 text-center">
      <div className="grid size-12 place-items-center rounded-2xl bg-violet/12 text-violet-text">
        <Icon name={icon} size={24} />
      </div>
      <h2 className="mt-4 text-lg font-bold">{title}</h2>
      {children && <p className="mt-1.5 max-w-md text-[0.92rem] leading-6 text-fog">{children}</p>}
      {action && <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  )
}

export function Notice({ tone = 'danger', title, children, action }: { tone?: 'danger' | 'warn' | 'info'; title?: string; children: ReactNode; action?: ReactNode }) {
  const styles = {
    danger: 'border-danger/25 bg-danger/[0.07] text-danger',
    warn: 'border-warn/25 bg-warn/[0.07] text-warn',
    info: 'border-violet/25 bg-violet/[0.07] text-violet-text',
  }[tone]
  return (
    <div role={tone === 'danger' ? 'alert' : 'status'} className={cx('flex flex-wrap items-start gap-3 rounded-xl border px-4 py-3 text-[0.9rem]', styles)}>
      <Icon name={tone === 'info' ? 'info' : 'alert'} size={18} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1 leading-6">
        {title && <p className="font-bold">{title}</p>}
        <div className={title ? 'text-paper/80' : ''}>{children}</div>
      </div>
      {action}
    </div>
  )
}

export function Toggle({ checked, onChange, label, description, disabled }: {
  checked: boolean
  onChange: (value: boolean) => void
  label: string
  description?: ReactNode
  disabled?: boolean
}) {
  const id = useId()
  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <label htmlFor={id} className="min-w-0 flex-1">
        <span className="block text-[0.93rem] font-semibold">{label}</span>
        {description && <span className="mt-0.5 block text-[0.83rem] leading-5 text-fog">{description}</span>}
      </label>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cx(
          'relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors duration-200 disabled:opacity-40',
          checked ? 'bg-violet' : 'bg-white/[0.12]',
        )}
      >
        <span className={cx('absolute top-0.5 size-5 rounded-full bg-white shadow transition-[left] duration-200', checked ? 'left-[22px]' : 'left-0.5')} />
      </button>
    </div>
  )
}

export function Segmented<T extends string | number>({ value, options, onChange, label }: {
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
  label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-xl border border-line bg-ink p-1">
      {options.map((option) => (
        <button
          key={String(option.value)}
          type="button"
          role="radio"
          aria-checked={option.value === value}
          onClick={() => onChange(option.value)}
          className={cx(
            'h-8 rounded-lg px-3 text-[0.84rem] font-semibold transition-colors',
            option.value === value ? 'bg-violet/22 text-violet-text' : 'text-fog hover:text-paper',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function SectionHeader({ title, meta, action }: { title: string; meta?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div className="min-w-0">
        <h2 className="display text-[1.15rem] font-semibold sm:text-[1.3rem]">{title}</h2>
        {meta && <p className="mt-1 text-[0.85rem] text-fog">{meta}</p>}
      </div>
      {action}
    </div>
  )
}

const statusMeta: Record<ProviderStatus, { label: string; className: string }> = {
  ok: { label: 'Работает', className: 'bg-offline' },
  partial: { label: 'Частично проверен', className: 'bg-violet-hi' },
  degraded: { label: 'Есть сбои', className: 'bg-warn' },
  down: { label: 'Не отвечает', className: 'bg-danger' },
  unknown: { label: 'Не проверялся', className: 'bg-dim' },
}

export function StatusDot({ status, withLabel }: { status: ProviderStatus; withLabel?: boolean }) {
  const meta = statusMeta[status]
  return (
    <span className="inline-flex items-center gap-1.5 text-[0.8rem] text-fog" title={meta.label}>
      <span className={cx('size-2 rounded-full', meta.className)} aria-hidden="true" />
      {withLabel ? meta.label : <span className="sr-only">{meta.label}</span>}
    </span>
  )
}

export function ConfirmDialog({ open, title, children, confirmLabel, tone = 'danger', busy, onConfirm, onCancel }: {
  open: boolean
  title: string
  children: ReactNode
  confirmLabel: string
  tone?: 'danger' | 'primary'
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal?.()
    if (!open && dialog.open) dialog.close()
  }, [open])
  return (
    <dialog
      ref={ref}
      onCancel={(event) => {
        event.preventDefault()
        onCancel()
      }}
      className="m-auto w-[min(440px,calc(100vw-32px))] rounded-2xl border border-line bg-ink-2 p-0 text-paper shadow-[0_30px_90px_rgba(0,0,0,0.6)] backdrop:bg-black/60 backdrop:backdrop-blur-sm"
    >
      {open && (
        <div className="p-6">
          <h2 className="text-lg font-bold">{title}</h2>
          <div className="mt-2 text-[0.92rem] leading-6 text-fog">{children}</div>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="ghost" onClick={onCancel} disabled={busy}>
              Отмена
            </Button>
            <Button variant={tone === 'danger' ? 'danger' : 'primary'} onClick={onConfirm} loading={busy} autoFocus>
              {confirmLabel}
            </Button>
          </div>
        </div>
      )}
    </dialog>
  )
}
