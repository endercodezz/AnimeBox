const UNITS = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return '—'
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024
    unit += 1
  }
  const digits = unit === 0 || value >= 100 ? 0 : 1
  return `${value.toFixed(digits).replace('.', ',')} ${UNITS[unit]}`
}

export function formatSpeed(bps: number | null | undefined): string {
  if (!bps || bps <= 0) return ''
  return `${formatBytes(bps)}/с`
}

/** 75 -> "1:15", 3725 -> "1:02:05" */
export function formatTime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return '0:00'
  const total = Math.floor(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const ss = String(s).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}

export function progressRatio(progress: number, duration: number | null | undefined): number {
  if (!duration || duration <= 0) return 0
  return Math.max(0, Math.min(1, progress / duration))
}

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

export function episodesLabel(n: number): string {
  return `${n} ${plural(n, 'серия', 'серии', 'серий')}`
}

export function relativeDate(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return ''
  const date = new Date(iso.endsWith('Z') || /[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)
  const diff = Math.max(0, now - date.getTime())
  const minutes = Math.round(diff / 60000)
  if (minutes < 1) return 'только что'
  if (minutes < 60) return `${minutes} мин назад`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} ч назад`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days} ${plural(days, 'день', 'дня', 'дней')} назад`
  return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: days > 300 ? 'numeric' : undefined })
}
