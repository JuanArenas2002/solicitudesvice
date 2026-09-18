import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'

export interface AsyncState<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
  setData: (data: T) => void
}

/** Carga datos al montar/cambiar `deps`. Ignora respuestas de peticiones ya obsoletas. */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let stale = false
    setLoading(true)
    load()
      .then((d) => { if (!stale) { setData(d); setError(null) } })
      .catch((e: unknown) => { if (!stale) setError(e instanceof ApiError ? e.message : 'No se pudo cargar') })
      .finally(() => { if (!stale) setLoading(false) })
    return () => { stale = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  return { data, error, loading, reload: useCallback(() => setTick((t) => t + 1), []), setData }
}
