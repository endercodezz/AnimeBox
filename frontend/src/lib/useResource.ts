import { useCallback, useEffect, useRef, useState } from 'react'
import { isAbort } from '../api/client'

export type Resource<T> = {
  data: T | undefined
  error: unknown
  loading: boolean
  reload: () => void
  setData: (updater: T | ((current: T | undefined) => T)) => void
}

/** Fetch on mount / when `deps` change; aborts stale requests; keeps old data while reloading. */
export function useResource<T>(load: (signal: AbortSignal) => Promise<T>, deps: unknown[], enabled = true): Resource<T> {
  const [data, setDataState] = useState<T | undefined>(undefined)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(enabled)
  const [tick, setTick] = useState(0)
  const loader = useRef(load)
  loader.current = load

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    loader
      .current(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setDataState(value)
      })
      .catch((err) => {
        if (!controller.signal.aborted && !isAbort(err)) setError(err)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps are supplied by the caller
  }, [...deps, tick, enabled])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  const setData = useCallback((updater: T | ((current: T | undefined) => T)) => {
    setDataState((current) => (typeof updater === 'function' ? (updater as (c: T | undefined) => T)(current) : updater))
  }, [])
  return { data, error, loading, reload, setData }
}

/** Repeats `fn` every `ms` while the tab is visible. */
export function useInterval(fn: () => void, ms: number | null) {
  const saved = useRef(fn)
  saved.current = fn
  useEffect(() => {
    if (ms === null) return
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') saved.current()
    }, ms)
    return () => window.clearInterval(id)
  }, [ms])
}
