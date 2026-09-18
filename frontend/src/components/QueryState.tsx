import type { ReactNode } from 'react'
import { Alert, AlertDescription, Button, Skeleton } from '@juanarenas31/metrik-ui'
import type { AsyncState } from '../hooks/useAsync'

/** Loading / error / contenido para cualquier `useAsync`. `children` solo se renderiza con datos. */
export function QueryState<T>({ query, children }: { query: AsyncState<T>; children: (data: T) => ReactNode }) {
  if (query.data) return <>{children(query.data)}</>
  if (query.error)
    return (
      <Alert tone="danger">
        <AlertDescription className="flex items-center justify-between gap-3">
          {query.error}
          <Button size="sm" variant="outline" onClick={query.reload}>Reintentar</Button>
        </AlertDescription>
      </Alert>
    )
  return <div className="space-y-3"><Skeleton className="h-10 w-full" /><Skeleton className="h-64 w-full" /></div>
}
