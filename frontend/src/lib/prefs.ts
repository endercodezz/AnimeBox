import { useSyncExternalStore } from 'react'

/** Per-device interface preferences (stored in this browser only). */
export type UiPrefs = {
  reduceMotion: boolean
  compactGrid: boolean
  volume: number
  muted: boolean
}

const KEY = 'animebox.ui'
const DEFAULTS: UiPrefs = { reduceMotion: false, compactGrid: false, volume: 1, muted: false }
const listeners = new Set<() => void>()

function read(): UiPrefs {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS
  } catch {
    return DEFAULTS
  }
}

let current = read()

export function getPrefs(): UiPrefs {
  return current
}

export function setPrefs(patch: Partial<UiPrefs>) {
  current = { ...current, ...patch }
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    /* storage unavailable (private mode) */
  }
  applyDocumentPrefs()
  listeners.forEach((listener) => listener())
}

export function applyDocumentPrefs() {
  document.documentElement.dataset.reduceMotion = String(current.reduceMotion)
}

export function usePrefs(): UiPrefs {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => current,
  )
}
