import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRightLeft } from 'lucide-react'
import {
  Alert, AlertDescription, Button, Dialog, Label, Tooltip, TooltipContent, TooltipTrigger, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, EmptyState, FloatingInput, FloatingSelect, useDebounce,
} from '@juanarenas31/metrik-ui'
import { catalogApi, requestsApi } from '../api'
import type { RequestStatus, RequestSummary } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { ChangeStatusDialog } from '../components/ChangeStatusDialog'
import { PageHeader } from '../components/PageHeader'
import { QueryState } from '../components/QueryState'
import { ServerTable, type Column } from '../components/ServerTable'
import { StatusBadge } from '../components/StatusBadge'
import { StatusPicker } from '../components/StatusPicker'
import { PERM, formatDateTime } from '../constants'
import { useAsync } from '../hooks/useAsync'
import { useSubmit } from '../hooks/useSubmit'

const buildColumns = (onChangeStatus?: (r: RequestSummary) => void): Column<RequestSummary>[] => [
  {
    header: 'N.º',
    cell: (r) => (
      <Link className="font-medium text-primary hover:underline" to={`/solicitudes/${r.id}`}>{r.request_number}</Link>
    ),
  },
  { header: 'Producto', cell: (r) => r.product_type_name },
  { header: 'Mentor', cell: (r) => r.mentor.name },
  { header: 'Estado', cell: (r) => <StatusBadge status={r.status} /> },
  { header: 'Enviada', cell: (r) => (r.submitted_at ? formatDateTime(r.submitted_at) : '—') },
  { header: 'Actualizada', cell: (r) => formatDateTime(r.updated_at) },
  ...(onChangeStatus
    ? [{
        header: 'Acciones',
        cell: (r: RequestSummary) => (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="sm" variant="outline" aria-label={`Cambiar el estado de ${r.request_number}`}
                onClick={() => onChangeStatus(r)}><ArrowRightLeft className="size-4" aria-hidden /></Button>
            </TooltipTrigger>
            <TooltipContent>Cambiar estado</TooltipContent>
          </Tooltip>
        ),
      }]
    : []),
]

function NewRequestDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const types = useAsync(catalogApi.productTypes, [])
  const [typeId, setTypeId] = useState('')
  const create = useSubmit(requestsApi.create)

  const onCreate = async () => {
    const created = await create.run(Number(typeId))
    if (created) navigate(`/solicitudes/${created.id}`)
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nueva solicitud</DialogTitle>
          <DialogDescription>Elige el tipo de producto que vas a registrar.</DialogDescription>
        </DialogHeader>
        <QueryState query={types}>
          {(page) => page.items.length === 0 ? (
            <EmptyState title="Sin productos disponibles" description="Aún no hay formularios publicados." />
          ) : (
            <FloatingSelect label="Tipo de producto" value={typeId} onChange={(e) => setTypeId(e.target.value)}>
              <option value="" />
              {page.items.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </FloatingSelect>
          )}
        </QueryState>
        {create.error && <Alert tone="danger"><AlertDescription>{create.error.message}</AlertDescription></Alert>}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button loading={create.pending} disabled={!typeId} onClick={onCreate}>Crear borrador</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function RequestsPage() {
  const { can } = useAuth()
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<RequestStatus | ''>('')
  const [productId, setProductId] = useState('')
  const [number, setNumber] = useState('')
  const [creating, setCreating] = useState(false)
  const [changing, setChanging] = useState<RequestSummary | null>(null)
  const debouncedNumber = useDebounce(number.trim(), 400)
  const products = useAsync(catalogApi.productTypes, [])
  const query = useAsync(
    () => requestsApi.list(page, {
      status: status || undefined,
      product_type_id: productId ? Number(productId) : undefined,
      request_number: debouncedNumber || undefined,
    }),
    [page, status, productId, debouncedNumber],
  )
  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1) }

  return (
    <>
      <PageHeader
        title="Solicitudes"
        description="Registro de productos de investigación."
        actions={can(PERM.createRequest) && <Button onClick={() => setCreating(true)}>Nueva solicitud</Button>}
      />
      <div className="mb-2 space-y-1">
        <Label>Estado</Label>
        <StatusPicker label="Filtrar por estado" value={status} onChange={reset(setStatus)} />
      </div>
      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <FloatingSelect label="Producto" value={productId} onChange={(e) => reset(setProductId)(e.target.value)}>
          <option value="">Todos</option>
          {products.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </FloatingSelect>
        <FloatingInput label="N.º de solicitud (SOL-2026-000001)" value={number}
          onChange={(e) => reset(setNumber)(e.target.value)} />
      </div>
      <QueryState query={query}>
        {(data) => data.items.length === 0 ? (
          <EmptyState title="Sin solicitudes"
            description={can(PERM.reviewRequest)
              ? 'No hay solicitudes con estos filtros. Si nunca ves ninguna, pide a un administrador que te asigne productos.'
              : 'No hay solicitudes que coincidan con los filtros.'} />
        ) : (
          <ServerTable data={data} columns={buildColumns(can(PERM.changeStatus) ? setChanging : undefined)}
            rowKey={(r) => r.id} noun="solicitudes" onPage={setPage} />
        )}
      </QueryState>
      {creating && <NewRequestDialog onClose={() => setCreating(false)} />}
      {changing && (
        <ChangeStatusDialog
          request={{ id: changing.id, status: changing.status, number: changing.request_number, product: changing.product_type_name, mentor: changing.mentor.name }}
          onChanged={() => query.reload()} onClose={() => setChanging(null)} />
      )}
    </>
  )
}
