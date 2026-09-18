import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowRightLeft, CircleCheck, CircleX, MessageSquareWarning, RefreshCw, Save, ScanSearch, Send } from 'lucide-react'
import {
  Alert, AlertDescription, AlertTitle, Button, Card, CardContent, Tabs, TabsContent, TabsList, TabsTrigger, toast,
} from '@juanarenas31/metrik-ui'
import { attachmentsApi, requestsApi } from '../api'
import type { Answers, RequestAction, RequestDetail, RequestStatus } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { AttachmentsPanel } from '../components/AttachmentsPanel'
import { ChangeStatusDialog } from '../components/ChangeStatusDialog'
import { IconButton } from '../components/IconButton'
import { DynamicForm } from '../components/DynamicForm'
import { PageHeader } from '../components/PageHeader'
import { QueryState } from '../components/QueryState'
import { ReasonDialog } from '../components/ReasonDialog'
import { StatusBadge } from '../components/StatusBadge'
import { ACTIONS, IDENTITY_KEY, PERM, formatDateTime } from '../constants'
import { useAsync } from '../hooks/useAsync'
import { useSubmit } from '../hooks/useSubmit'

const ACTION_ICON = {
  submit: Send,
  resubmit: RefreshCw,
  review: ScanSearch,
  approve: CircleCheck,
  'request-correction': MessageSquareWarning,
  reject: CircleX,
} as const

/** Qué botones ofrecer. Es solo comodidad de la interfaz: el backend valida rol, dueño y estado. */
function offeredActions(status: RequestStatus, isOwner: boolean, can: (p: string) => boolean): RequestAction[] {
  if (isOwner && status === 'BORRADOR') return ['submit']
  if (isOwner && status === 'CORRECCION_SOLICITADA') return ['resubmit']
  if ((status === 'ENVIADA' || status === 'REENVIADA') && can(PERM.reviewRequest)) return ['review']
  if (status === 'EN_REVISION') {
    const out: RequestAction[] = []
    if (can(PERM.requestCorrection)) out.push('request-correction')
    if (can(PERM.approveRequest)) out.push('approve')
    if (can(PERM.rejectRequest)) out.push('reject')
    return out
  }
  return []
}

function History({ request }: { request: RequestDetail }) {
  const history = useAsync(() => requestsApi.history(request.id), [request.id, request.version])
  return (
    <Card>
      <CardContent className="pt-6">
        <QueryState query={history}>
          {(entries) => (
            <ol className="space-y-4">
              {[...entries].reverse().map((h, i) => (
                <li key={i} className="text-sm">
                  <div className="font-medium"><StatusBadge status={h.new_status} /></div>
                  <div className="mt-1 text-xs text-fg-muted">
                    {h.changed_by === request.mentor.id ? 'Mentor' : 'Personal administrativo'} · {formatDateTime(h.occurred_at)}
                  </div>
                  {h.reason && <p className="mt-1 text-fg-muted">{h.reason}</p>}
                </li>
              ))}
            </ol>
          )}
        </QueryState>
      </CardContent>
    </Card>
  )
}

function RequestView({ request, onChange }: { request: RequestDetail; onChange: (r: RequestDetail) => void }) {
  const { user, can } = useAuth()
  const [answers, setAnswers] = useState<Answers>(request.answers)
  const [askFor, setAskFor] = useState<RequestAction | null>(null)
  const [changing, setChanging] = useState(false)
  const attachments = useAsync(() => attachmentsApi.list(request.id), [request.id])
  useEffect(() => setAnswers(request.answers), [request])

  const isOwner = user?.id === request.mentor.id
  const canEdit = isOwner && request.is_editable

  // Solo se envía lo que cambió: el PATCH es parcial y "vacío" borra la respuesta.
  const changes = useMemo(() => {
    const out: Answers = {}
    for (const key of Object.keys(answers)) {
      const before = request.answers[key] ?? null
      const now = answers[key] === '' ? null : answers[key]
      if (JSON.stringify(before) !== JSON.stringify(now)) out[key] = answers[key]
    }
    return out
  }, [answers, request.answers])
  const dirty = Object.keys(changes).length > 0

  const save = useSubmit(() => requestsApi.saveAnswers(request.id, request.version, changes), 'Cambios guardados')
  const act = useSubmit(async (action: RequestAction, text?: string) => {
    let current = request
    // Enviar valida lo guardado en el servidor: primero se persisten los cambios pendientes.
    if (dirty && (action === 'submit' || action === 'resubmit')) {
      current = await requestsApi.saveAnswers(request.id, request.version, changes)
      onChange(current)
    }
    const updated = await requestsApi.act(current.id, action, text)
    toast.success(`${ACTIONS[action].label}: listo`)
    return updated
  })

  const run = async (action: RequestAction, text?: string) => {
    const updated = await act.run(action, text)
    if (updated) { setAskFor(null); onChange(updated) }
  }
  const onSave = async () => {
    const updated = await save.run()
    if (updated) onChange(updated)
  }
  const onAction = (action: RequestAction) => {
    if (ACTIONS[action].text) { act.clearError(); setAskFor(action) } else run(action)
  }

  const labels = useMemo(
    () => Object.fromEntries(request.form.sections.flatMap((s) => s.fields.map((f) => [f.key, f.label]))),
    [request.form],
  )
  const failure = save.error ?? act.error
  const fieldErrors = save.error?.field ? { [save.error.field]: save.error.message } : {}
  const actions = offeredActions(request.status, isOwner, can)
  const hasFiles = (attachments.data?.length ?? 0) > 0
  const locked: Record<string, string> = hasFiles ? { [IDENTITY_KEY]: 'No se puede cambiar: ya hay soportes cargados con esta cédula.' } : {}

  return (
    <>
      <PageHeader
        title={`Solicitud ${request.request_number}`}
        description={`${request.product_type.name} · ${request.mentor.name}`}
        actions={
          <>
            <StatusBadge status={request.status} />
            {canEdit && <IconButton icon={Save} label="Guardar cambios" loading={save.pending} disabled={!dirty} onClick={onSave} />}
            {request.status !== 'BORRADOR' && can(PERM.changeStatus) && (
              <IconButton icon={ArrowRightLeft} label="Cambiar estado" onClick={() => setChanging(true)} />
            )}
            {actions.map((a) => (
              <IconButton key={a} icon={ACTION_ICON[a]} label={ACTIONS[a].label} variant={ACTIONS[a].variant}
                loading={act.pending && !askFor} onClick={() => onAction(a)} />
            ))}
          </>
        }
      />
      {request.open_correction && (
        <Alert tone="warning" className="mb-4">
          <AlertTitle>Corrección solicitada</AlertTitle>
          <AlertDescription>{request.open_correction.description}</AlertDescription>
        </Alert>
      )}
      {canEdit && request.missing_required.length > 0 && (
        <Alert tone="info" className="mb-4">
          <AlertTitle>Para enviar falta completar</AlertTitle>
          <AlertDescription>{request.missing_required.map((k) => labels[k] ?? k).join(', ')}</AlertDescription>
        </Alert>
      )}
      {failure && !askFor && (
        <Alert tone="danger" className="mb-4">
          <AlertDescription>
            {act.error?.missing?.length
              ? `Faltan campos obligatorios: ${act.error.missing.map((k) => labels[k] ?? k).join(', ')}`
              : failure.message}
          </AlertDescription>
        </Alert>
      )}
      <Tabs defaultValue="form">
        <TabsList>
          <TabsTrigger value="form">Formulario</TabsTrigger>
          <TabsTrigger value="files">Soportes{attachments.data ? ` (${attachments.data.length})` : ''}</TabsTrigger>
          <TabsTrigger value="history">Historial</TabsTrigger>
        </TabsList>
        <TabsContent value="form">
          <Card>
            <CardContent className="pt-6">
              <DynamicForm form={request.form} answers={answers} errors={fieldErrors} disabled={!canEdit} locked={locked}
                onChange={(key, value) => setAnswers((a) => ({ ...a, [key]: value }))} />
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="files">
          <AttachmentsPanel requestId={request.id} form={request.form} query={attachments} canManage={canEdit}
            canDownload={isOwner || can(PERM.downloadAttachments)}
            hasCedula={Boolean(request.answers[IDENTITY_KEY])} />
        </TabsContent>
        <TabsContent value="history"><History request={request} /></TabsContent>
      </Tabs>
      {changing && <ChangeStatusDialog request={request} onChanged={onChange} onClose={() => setChanging(false)} />}
      {askFor && (
        <ReasonDialog title={ACTIONS[askFor].label} label={ACTIONS[askFor].textLabel ?? 'Motivo'}
          required={ACTIONS[askFor].text === 'required'} pending={act.pending} error={act.error?.message}
          onCancel={() => setAskFor(null)} onConfirm={(text) => run(askFor, text)} />
      )}
    </>
  )
}

export default function RequestPage() {
  const { id = '' } = useParams()
  const query = useAsync(() => requestsApi.get(id), [id])
  if (query.error && !query.data) {
    return (
      <Alert tone="danger">
        <AlertDescription className="flex items-center justify-between gap-3">
          {query.error}
          <Button asChild size="sm" variant="outline"><Link to="/">Volver a solicitudes</Link></Button>
        </AlertDescription>
      </Alert>
    )
  }
  return <QueryState query={query}>{(request) => <RequestView request={request} onChange={query.setData} />}</QueryState>
}
