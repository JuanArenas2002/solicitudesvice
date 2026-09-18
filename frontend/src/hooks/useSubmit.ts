import { useState } from 'react'
import { toast } from '@juanarenas31/metrik-ui'
import { ApiError } from '../api/client'

/** Envuelve una acción async: estado `pending`, error del backend (con `field`) y toast opcional. */
export function useSubmit<A extends unknown[], R>(action: (...args: A) => Promise<R>, successMessage?: string) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<{ message: string; field?: string; missing?: string[] } | null>(null)

  const run = async (...args: A): Promise<R | undefined> => {
    setPending(true)
    setError(null)
    try {
      const result = await action(...args)
      if (successMessage) toast.success(successMessage)
      return result
    } catch (e) {
      setError(e instanceof ApiError ? { message: e.message, field: e.field, missing: e.missing } : { message: 'Error inesperado' })
    } finally {
      setPending(false)
    }
  }
  return { run, pending, error, clearError: () => setError(null) }
}
