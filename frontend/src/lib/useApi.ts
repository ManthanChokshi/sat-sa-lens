import { useCallback, useEffect, useState } from 'react'

export interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
  reload: () => void
}

/** Minimal data hook: load on mount, reload on demand or when `deps` change. */
export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    run()
      .then((result) => {
        if (alive) setData(result)
      })
      .catch((err: Error) => {
        if (alive) setError(err.message || 'Request failed')
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [run, tick])

  return { data, loading, error, reload: () => setTick((t) => t + 1) }
}
