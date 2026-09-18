import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, BellRing, LockOpen } from 'lucide-react'
import {
  Alert, AlertDescription, Avatar, AvatarFallback, Badge, Button, Dialog, DialogContent, DialogDescription,
  DialogFooter, DialogHeader, DialogTitle, Label, Textarea, Tooltip, TooltipContent, TooltipTrigger, cn, toast,
} from '@juanarenas31/metrik-ui'
import { requestsApi } from '../api'
import type { RequestDetail, RequestStatus } from '../api/types'
import { STATUS } from '../constants'
import { useSubmit } from '../hooks/useSubmit'
import { ErrorBoundary } from './ErrorBoundary'
import { STATUS_ICON, StatusBadge } from './StatusBadge'

interface Props {
  /** Sirve desde el detalle y desde el listado: lo que se muestra de la solicitud viene de quien lo abre. */
  request: { id: string; status: RequestStatus; number: string; product: string; mentor: string }
  onChanged: (request: RequestDetail) => void
  onClose: () => void
}

/** Qué ocurre al pasar a cada estado, para que el cambio nunca sea una sorpresa. */
const EFFECT: Record<Exclude<RequestStatus, 'BORRADOR'>, { detail: string; reasons: string[] }> = {
  ENVIADA: {
    detail: 'Vuelve a la cola de revisión, sin nadie a cargo.',
    reasons: ['Se devuelve a la cola para reasignarla', 'Se había tomado por error'],
  },
  EN_REVISION: {
    detail: 'Queda a tu cargo para revisarla.',
    reasons: ['La tomo para revisarla', 'Se reabre la revisión'],
  },
  CORRECCION_SOLICITADA: {
    detail: 'El mentor podrá editarla y volver a enviarla. Tu motivo se le muestra como la corrección que debe hacer.',
    reasons: ['Falta un soporte obligatorio', 'Hay datos inconsistentes con el soporte', 'El soporte no se puede leer'],
  },
  REENVIADA: {
    detail: 'Se marca como corregida y lista para volver a revisarse.',
    reasons: ['La corrección se resolvió por otro medio'],
  },
  APROBADA: {
    detail: 'Cierra la revisión con resultado favorable.',
    reasons: ['Cumple todos los requisitos', 'Aprobada por comité', 'Verificada contra los soportes'],
  },
  RECHAZADA: {
    detail: 'Cierra la revisión con resultado desfavorable. El mentor deberá iniciar una solicitud nueva.',
    reasons: ['No cumple los criterios del producto', 'El producto ya estaba registrado', 'Soportes no válidos'],
  },
}

const CLOSED: RequestStatus[] = ['APROBADA', 'RECHAZADA']
const MAX = 2000
const initials = (name: string) => name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()

/** Personal administrativo: mueve la solicitud a cualquier estado (menos borrador); el motivo queda en el historial. */
function ChangeStatusDialogBody({ request, onChanged, onClose }: Props) {
  const [target, setTarget] = useState<Exclude<RequestStatus, 'BORRADOR'> | ''>('')
  const [reason, setReason] = useState('')
  const change = useSubmit((status: RequestStatus, text: string) => requestsApi.changeStatus(request.id, status, text), 'Estado actualizado')
  const options = useMemo(
    () => (Object.keys(EFFECT) as Exclude<RequestStatus, 'BORRADOR'>[]).filter((s) => s !== request.status),
    [request.status],
  )

  const ready = target !== '' && reason.trim().length > 0
  const onConfirm = async () => {
    if (!ready) return
    const updated = await change.run(target, reason.trim())
    if (updated) { onChanged(updated); onClose() }
  }
  // Ctrl/Cmd + Enter confirma sin salir del teclado.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') void onConfirm() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const TargetIcon = target ? STATUS_ICON[target] : null
  const reopening = CLOSED.includes(request.status)

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Cambiar el estado de la solicitud</DialogTitle>
          <DialogDescription>El cambio queda en el historial y el mentor recibe un aviso.</DialogDescription>
        </DialogHeader>

        {/* A qué solicitud se aplica */}
        <div className="flex items-center gap-3 rounded-lg border border-border bg-surface-muted p-3">
          <Avatar className="h-10 w-10"><AvatarFallback>{initials(request.mentor)}</AvatarFallback></Avatar>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{request.number}</p>
            <p className="truncate text-xs text-fg-muted">{request.product} · {request.mentor}</p>
          </div>
          <StatusBadge status={request.status} />
        </div>

        {/* 1 · nuevo estado */}
        <section className="space-y-3">
          <Label>1 · ¿A qué estado la pasas?</Label>
          <div className="grid grid-cols-5 gap-2" role="radiogroup" aria-label="Nuevo estado">
            {options.map((s) => {
              const Icon = STATUS_ICON[s]
              const selected = target === s
              return (
                <Tooltip key={s}>
                  <TooltipTrigger asChild>
                    <button type="button" role="radio" aria-checked={selected} aria-label={STATUS[s].label}
                      onClick={() => setTarget(s)}
                      className={cn(
                        'flex h-16 items-center justify-center rounded-xl border-2 bg-surface transition-all duration-fast',
                        'hover:-translate-y-0.5 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        selected ? 'border-primary bg-primary-soft shadow-sm' : 'border-border',
                      )}>
                      <Badge tone={STATUS[s].tone} className="size-9 justify-center rounded-full p-0">
                        <Icon className="size-5" aria-hidden />
                      </Badge>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>{STATUS[s].label}</TooltipContent>
                </Tooltip>
              )
            })}
          </div>

          {/* de qué a qué, y qué implica */}
          {target && TargetIcon ? (
            <div className="space-y-2 rounded-lg border border-border p-3">
              <div className="flex items-center gap-3">
                <StatusBadge status={request.status} />
                <ArrowRight className="size-4 text-fg-muted" aria-hidden />
                <StatusBadge status={target} />
                <span className="text-sm font-semibold">{STATUS[target].label}</span>
              </div>
              <p className="text-sm text-fg-muted">{EFFECT[target].detail}</p>
              <p className="flex items-center gap-2 text-xs text-fg-muted">
                <BellRing className="size-3.5" aria-hidden />El mentor recibe una notificación.
                {target === 'CORRECCION_SOLICITADA' && (<><LockOpen className="ml-2 size-3.5" aria-hidden />Recupera la edición.</>)}
              </p>
            </div>
          ) : (
            <p className="text-sm text-fg-muted">Elige el estado de destino; pasa el cursor sobre un icono para ver su nombre.</p>
          )}
          {reopening && target && (
            <Alert tone="warning">
              <AlertDescription>Esta solicitud ya estaba cerrada: al cambiarla la reabres y se vuelve a notificar al mentor.</AlertDescription>
            </Alert>
          )}
        </section>

        {/* 2 · motivo */}
        <section className="space-y-3">
          <Label>2 · Motivo <span className="font-normal text-fg-muted">(obligatorio, lo verá el mentor)</span></Label>
          {target && (
            <div className="flex flex-wrap gap-2">
              {EFFECT[target].reasons.map((r) => (
                <button key={r} type="button" onClick={() => setReason(r)}
                  className={cn(
                    'rounded-full border px-3 py-1 text-xs transition-colors duration-fast hover:bg-surface-muted',
                    reason === r ? 'border-primary bg-primary-soft text-fg' : 'border-border text-fg-muted',
                  )}>
                  {r}
                </button>
              ))}
            </div>
          )}
          <Textarea aria-label="Motivo del cambio" placeholder="Escribe el motivo o elige uno de arriba y edítalo…" rows={4}
            maxLength={MAX} value={reason} onChange={(e) => setReason(e.target.value)} />
          <p className="text-right text-xs text-fg-muted">{reason.length}/{MAX}</p>
        </section>

        {change.error && <Alert tone="danger"><AlertDescription>{change.error.message}</AlertDescription></Alert>}

        <DialogFooter className="items-center gap-2 sm:justify-between">
          <span className="hidden text-xs text-fg-muted sm:block">Ctrl + Enter para confirmar</span>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>Cancelar</Button>
            <Button variant={target === 'RECHAZADA' ? 'danger' : 'primary'} loading={change.pending} disabled={!ready}
              leftIcon={TargetIcon ? <TargetIcon className="size-4" aria-hidden /> : undefined} onClick={onConfirm}>
              Confirmar cambio
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Si el diálogo llegara a fallar, se cierra con un aviso: la pantalla de fondo nunca se queda en blanco. */
export function ChangeStatusDialog(props: Props) {
  return (
    <ErrorBoundary
      onError={(e) => toast.error(`No se pudo abrir el cambio de estado: ${e.message}`)}
      fallback={() => { queueMicrotask(props.onClose); return null }}
    >
      <ChangeStatusDialogBody {...props} />
    </ErrorBoundary>
  )
}
