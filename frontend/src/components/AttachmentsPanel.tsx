import { useState } from 'react'
import { Download, Trash2 } from 'lucide-react'
import {
  Alert, AlertDescription, Badge, Card, CardContent, CardDescription, CardHeader, CardTitle,
  EmptyState, FileDropzone, Table, TableBody, TableCell, TableHead, TableHeader, TableRow, toast,
} from '@juanarenas31/metrik-ui'
import { attachmentsApi } from '../api'
import { ApiError } from '../api/client'
import type { Attachment, FormField, FormVersion } from '../api/types'
import { formatDateTime, formatSize } from '../constants'
import type { AsyncState } from '../hooks/useAsync'
import { useSubmit } from '../hooks/useSubmit'
import { ConfirmDialog } from './ConfirmDialog'
import { IconButton } from './IconButton'
import { QueryState } from './QueryState'

interface Shared {
  requestId: string
  /** El dueño puede subir y borrar (borrador o corrección). */
  canManage: boolean
  /** Dueño o personal administrativo. El administrador solo ve la lista. */
  canDownload: boolean
  /** Sin cédula guardada el servidor no sabe en qué carpeta guardar. */
  hasCedula: boolean
  reload: () => void
}

/** Un campo de soporte del formulario: qué documentos pide, si es obligatorio y sus archivos. */
function SupportField({ field, files, ...shared }: Shared & { field: FormField; files: Attachment[] }) {
  const { requestId, canManage, canDownload, hasCedula, reload } = shared
  const [toDelete, setToDelete] = useState<Attachment | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const remove = useSubmit((a: Attachment) => attachmentsApi.remove(requestId, a.id).then(() => true), 'Soporte eliminado')
  const download = useSubmit((a: Attachment) => attachmentsApi.download(requestId, a).then(() => true))
  const accept = field.allowed_types.map((t) => `.${t}`).join(',')

  // Se suben de a uno: con el primero el servidor asigna la carpeta "Solicitud N".
  const upload = async (picked: File[]) => {
    setUploading(true)
    setUploadError(null)
    let done = 0
    try {
      for (const file of picked) {
        await attachmentsApi.upload(requestId, field.key, file)
        done += 1
      }
    } catch (e) {
      setUploadError(`${picked[done].name}: ${e instanceof ApiError ? e.message : 'no se pudo subir'}`)
    } finally {
      setUploading(false)
      if (done) { toast.success(done === 1 ? 'Soporte cargado' : `${done} soportes cargados`); reload() }
    }
  }

  const onDelete = async () => {
    if (toDelete && (await remove.run(toDelete))) { setToDelete(null); reload() }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>{field.label}</CardTitle>
          <Badge tone={field.required_to_submit ? 'warning' : 'neutral'}>
            {field.required_to_submit ? 'Obligatorio' : 'Opcional'}
          </Badge>
          {field.required_to_submit && files.length === 0 && <Badge tone="danger" dot>Falta cargarlo</Badge>}
        </div>
        <CardDescription>
          {field.help_text && <>{field.help_text}. </>}
          Tipos admitidos: {field.allowed_types.map((t) => `.${t}`).join(', ')}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {canManage && !hasCedula && (
          <Alert tone="info">
            <AlertDescription>Guarda primero la cédula: con ella se crea la carpeta de los soportes.</AlertDescription>
          </Alert>
        )}
        {canManage && hasCedula && (
          <FileDropzone multiple accept={accept} disabled={uploading} value={[]} onFilesChange={upload}
            hint={uploading ? 'Subiendo…' : `Solo ${field.allowed_types.map((t) => `.${t}`).join(', ')}`} />
        )}
        {uploadError && <Alert tone="danger"><AlertDescription>{uploadError}</AlertDescription></Alert>}
        {(remove.error || download.error) && (
          <Alert tone="danger"><AlertDescription>{(remove.error ?? download.error)?.message}</AlertDescription></Alert>
        )}
        {files.length === 0 ? (
          <p className="text-sm text-fg-muted">Aún no se ha cargado ningún archivo en este campo.</p>
        ) : (
          <Table stackable>
            <TableHeader>
              <TableRow><TableHead>Archivo</TableHead><TableHead>Tamaño</TableHead><TableHead>Cargado</TableHead><TableHead /></TableRow>
            </TableHeader>
            <TableBody>
              {files.map((f) => (
                <TableRow key={f.id}>
                  <TableCell label="Archivo" className="font-medium">{f.file_name}</TableCell>
                  <TableCell label="Tamaño">{formatSize(f.file_size)}</TableCell>
                  <TableCell label="Cargado">{formatDateTime(f.created_at)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      {canDownload && <IconButton icon={Download} label="Descargar" loading={download.pending} onClick={() => download.run(f)} />}
                      {canManage && <IconButton icon={Trash2} label="Eliminar" variant="ghost" onClick={() => setToDelete(f)} />}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      {toDelete && (
        <ConfirmDialog title="Eliminar soporte" description={`Se eliminará «${toDelete.file_name}». Esta acción no se puede deshacer.`}
          confirmLabel="Eliminar" onConfirm={onDelete} onCancel={() => setToDelete(null)} />
      )}
    </Card>
  )
}

interface Props extends Omit<Shared, 'reload'> {
  form: FormVersion
  query: AsyncState<Attachment[]>
}

/** Los soportes de la solicitud, agrupados por el campo de soporte del formulario al que pertenecen. */
export function AttachmentsPanel({ form, query, ...shared }: Props) {
  const fields = form.sections.flatMap((s) => s.fields).filter((f) => f.type === 'SUPPORT')
  if (fields.length === 0) {
    return <EmptyState title="Sin soportes" description="Este formulario no pide ningún soporte." />
  }
  return (
    <QueryState query={query}>
      {(files) => (
        <div className="space-y-4">
          {files[0] && <p className="text-xs text-fg-muted">Carpeta: <Badge tone="neutral">{files[0].folder}</Badge></p>}
          {fields.map((f) => (
            <SupportField key={f.key} field={f} files={files.filter((a) => a.field_key === f.key)}
              {...shared} reload={query.reload} />
          ))}
        </div>
      )}
    </QueryState>
  )
}
