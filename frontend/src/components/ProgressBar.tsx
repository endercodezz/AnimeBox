type Props = {
  value: number
  className?: string
}

export function ProgressBar({ value, className = '' }: Props) {
  const pct = Math.max(0, Math.min(100, value))
  return (
    <div className={`h-1.5 overflow-hidden rounded-full bg-white/8 ${className}`}>
      <div
        className="h-full rounded-full bg-gradient-to-r from-amber to-violet-soft shadow-[0_0_16px_rgba(139,92,246,0.55)] transition-[width] duration-300"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}
