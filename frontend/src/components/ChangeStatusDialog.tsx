import { useState } from 'react'
import {
  Alert, AlertDescription, Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader,
  DialogTitle, FloatingTextarea, Label,
} from '@juanarenas31/metrik-ui'
import { requestsApi } from '../api'
import type { RequestDetail, RequestStatus } from '../api/types'
import { STATUS } from '../constants'
import { useSubmit } from '../hooks/useSubmit'
import { StatusBadge } from './StatusBadge'
import { StatusPicker } from './StatusPicker'

interface Props {
  /** Sirve desde el detalle y desde el listado: solo hace falta el id y el estado actual. */
  request: { id: string; status: RequestStatus }
  onChanged: (request: RequestDetail) => void
  onClose: () => void
}

/** Personal administrativo: pasa la solicitud a cualquier estado (menos borrador); el motivo queda en el historial. */
export function ChangeStatusDialog({ request, onChanged, onClose }: Props) {
  const [target, setTarget] = useState<RequestStatus | ''>('')
  const [reason, setReason] = useState('')
  const change = useSubmit((status: RequestStatus, text: string) => requestsApi.changeStatus(request.id, status, text), 'Estado actualizado')
  const options = (Object.keys(STATUS) as RequestStatus[]).filter((s) => s !== 'BORRADOR' && s !== request.status)

  const onConfirm = async () => {
    if (!target) return
    const updated = await change.run(target, reason.trim())
    if (updated) { onChanged(updated); onClose() }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Cambiar estado</DialogTitle>
          <DialogDescription>
            Se guarda en el historial con tu motivo y el mentor recibe un aviso. Al pasar a corrección solicitada
            el mentor recupera la edición.
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-fg-muted">Ahora:</span><StatusBadge status={request.status} />
        </div>
        <div className="space-y-2">
          <Label>Nuevo estado{target && <span className="ml-2 font-normal text-fg-muted">{STATUS[target].label}</span>}</Label>
          <StatusPicker label="Nuevo estado" value={target} onChange={setTarget} options={options} />
        </div>
        <FloatingTextarea label="Motivo del cambio (obligatorio)" rows={4} maxLength={2000} value={reason}
          onChange={(e) => setReason(e.target.value)} />
        {change.error && <Alert tone="danger"><AlertDescription>{change.error.message}</AlertDescription></Alert>}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button loading={change.pending} disabled={!target || !reason.trim()} onClick={onConfirm}>Cambiar estado</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
