import type { ReactNode } from 'react'
import { Button, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@juanarenas31/metrik-ui'
import type { Page } from '../api/types'

export interface Column<T> {
  header: string
  cell: (row: T) => ReactNode
  className?: string
}

interface Props<T> {
  data: Page<T>
  columns: Column<T>[]
  rowKey: (row: T) => string
  noun: string
  onPage: (page: number) => void
}

/** Tabla de una lista paginada en el servidor: un único paginador (el de la API), sin el de DataTable. */
export function ServerTable<T>({ data, columns, rowKey, noun, onPage }: Props<T>) {
  return (
    <>
      <Table stackable>
        <TableHeader>
          <TableRow>{columns.map((c) => <TableHead key={c.header}>{c.header}</TableHead>)}</TableRow>
        </TableHeader>
        <TableBody>
          {data.items.map((row) => (
            <TableRow key={rowKey(row)}>
              {columns.map((c) => (
                <TableCell key={c.header} label={c.header} className={c.className}>{c.cell(row)}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <div className="mt-4 flex items-center justify-between text-sm text-fg-muted">
        <span>Página {data.page} de {Math.max(data.total_pages, 1)} · {data.total} {noun}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>Anterior</Button>
          <Button size="sm" variant="outline" disabled={data.page >= data.total_pages} onClick={() => onPage(data.page + 1)}>Siguiente</Button>
        </div>
      </div>
    </>
  )
}
