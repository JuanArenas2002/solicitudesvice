import { useEffect, useState } from 'react'
import { Badge, useDebounce } from '@juanarenas31/metrik-ui'
import { journalsApi } from '../api'
import { ApiError } from '../api/client'
import type { Journal } from '../api/types'

// Mismo formato que valida el backend: NNNN-NNNC, con el guion opcional.
const ISSN = /^[0-9]{4}-?[0-9]{3}[0-9Xx]$/

type State = { kind: 'idle' } | { kind: 'loading' } | { kind: 'found'; journal: Journal }
  | { kind: 'missing' } | { kind: 'unavailable' }

/** Debajo de un campo ISSN: consulta el catálogo institucional y muestra qué revista es (o que no existe). */
export function JournalHint({ issn }: { issn: string }) {
  const value = useDebounce(issn.replace(/\s/g, '').toUpperCase(), 500)
  const [state, setState] = useState<State>({ kind: 'idle' })

  useEffect(() => {
    if (!ISSN.test(value)) { setState({ kind: 'idle' }); return }
    let stale = false
    setState({ kind: 'loading' })
    journalsApi.lookup(value)
      .then((journal) => { if (!stale) setState({ kind: 'found', journal }) })
      .catch((e: unknown) => {
        if (stale) return
        setState({ kind: e instanceof ApiError && e.status === 404 ? 'missing' : 'unavailable' })
      })
    return () => { stale = true }
  }, [value])

  switch (state.kind) {
    case 'idle': return null
    case 'loading': return <p className="mt-1 text-xs text-fg-muted">Verificando en el catálogo de revistas…</p>
    case 'found':
      return (
        <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-fg-muted">
          <Badge tone="success" dot>Revista encontrada</Badge>
          <span className="font-medium text-fg">{state.journal.title}</span>
          {state.journal.publisher && <span>· {state.journal.publisher}</span>}
          {state.journal.country && <span>· {state.journal.country}</span>}
        </p>
      )
    case 'missing':
      return <p className="mt-1 text-xs text-danger">Este ISSN no está en el catálogo de revistas: revisa que esté bien escrito.</p>
    case 'unavailable':
      return <p className="mt-1 text-xs text-fg-muted">No se pudo consultar el catálogo de revistas; se verificará al enviar.</p>
  }
}
