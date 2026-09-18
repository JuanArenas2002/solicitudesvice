import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Alert, AlertDescription, AlertTitle, Button, toast } from '@juanarenas31/metrik-ui'
import { catalogApi } from '../api'
import type { FormSection, FormVersion } from '../api/types'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { CEDULA_FIELD, FormBuilder, slug } from '../components/FormBuilder'
import { PageHeader } from '../components/PageHeader'
import { QueryState } from '../components/QueryState'
import { FormStatusBadge } from '../components/StatusBadge'
import { IDENTITY_KEY } from '../constants'
import { useAsync } from '../hooks/useAsync'
import { useSubmit } from '../hooks/useSubmit'

/** Solo lo que acepta el backend (rechaza campos desconocidos): sin ids ni datos de solo lectura. */
const toPayload = (sections: FormSection[]): FormSection[] =>
  sections.map((s) => ({
    title: s.title,
    description: s.description || null,
    fields: s.fields.map((f) => ({
      key: f.key,
      label: f.label,
      type: f.type,
      required_to_submit: f.required_to_submit,
      help_text: f.help_text || null,
      min_length: f.min_length,
      max_length: f.max_length,
      min_value: f.min_value,
      max_value: f.max_value,
      // Las opciones a medio llenar se descartan; si falta el valor se deriva de la etiqueta.
      allowed_types: f.type === 'SUPPORT' ? f.allowed_types : [],
      options: f.options
        .filter((o) => o.label.trim() || o.value.trim())
        .map((o) => ({ value: o.value.trim() || slug(o.label), label: o.label.trim() || o.value.trim() })),
    })),
  }))

const hasCedula = (sections: FormSection[]) =>
  sections.some((s) => s.fields.some((f) => f.key === IDENTITY_KEY && f.type === 'CEDULA'))

function Editor({ version, onSaved }: { version: FormVersion; onSaved: (v: FormVersion) => void }) {
  const [sections, setSections] = useState<FormSection[]>(version.sections)
  const [confirming, setConfirming] = useState(false)
  useEffect(() => setSections(version.sections), [version])

  const readOnly = version.status !== 'BORRADOR'
  const dirty = JSON.stringify(toPayload(sections)) !== JSON.stringify(toPayload(version.sections))
  const save = useSubmit(() => catalogApi.saveDraft(version.id, toPayload(sections)), 'Borrador guardado')
  const publish = useSubmit(async () => {
    if (dirty) await catalogApi.saveDraft(version.id, toPayload(sections)) // se publica lo que se ve
    return catalogApi.publish(version.id)
  })

  const onSave = async () => {
    const saved = await save.run()
    if (saved) onSaved(saved)
  }
  const onPublish = async () => {
    setConfirming(false)
    const published = await publish.run()
    if (published) {
      toast.success(`Versión ${published.version_number} publicada`)
      onSaved(published)
    }
  }
  const addCedula = () =>
    setSections((all) =>
      all.length
        ? all.map((s, i) => (i === 0 ? { ...s, fields: [CEDULA_FIELD, ...s.fields] } : s))
        : [{ title: 'Datos generales', description: null, fields: [CEDULA_FIELD] }],
    )

  const error = save.error ?? publish.error
  return (
    <>
      <PageHeader
        title={`Versión ${version.version_number}`}
        description={
          readOnly
            ? 'Solo lectura: las versiones publicadas no se modifican. Abre un borrador nuevo para cambiarlas.'
            : 'Borrador: los mentores aún no lo ven.'
        }
        actions={
          <>
            <FormStatusBadge status={version.status} />
            <Button asChild variant="ghost"><Link to={`/productos/${version.product_type_id}`}>Volver</Link></Button>
            {!readOnly && <Button variant="outline" loading={save.pending} disabled={!dirty} onClick={onSave}>Guardar</Button>}
            {!readOnly && <Button loading={publish.pending} onClick={() => setConfirming(true)}>Publicar</Button>}
          </>
        }
      />
      {!readOnly && !hasCedula(sections) && (
        <Alert tone="warning" className="mb-4">
          <AlertTitle>Falta el campo Cédula</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
            Todo formulario lo necesita: define la carpeta donde se guardan los soportes.
            <Button size="sm" variant="outline" onClick={addCedula}>Agregar campo Cédula</Button>
          </AlertDescription>
        </Alert>
      )}
      {error && <Alert tone="danger" className="mb-4"><AlertDescription>{error.message}</AlertDescription></Alert>}
      <FormBuilder sections={sections} readOnly={readOnly} onChange={setSections} />
      {confirming && (
        <ConfirmDialog
          title="Publicar versión"
          confirmLabel="Publicar"
          description="Las solicitudes nuevas usarán esta versión y la publicada hasta ahora se retira. Las solicitudes en curso conservan la suya."
          onCancel={() => setConfirming(false)}
          onConfirm={onPublish}
        />
      )}
    </>
  )
}

export default function FormEditorPage() {
  const versionId = Number(useParams().versionId)
  const query = useAsync(() => catalogApi.version(versionId), [versionId])
  return <QueryState query={query}>{(version) => <Editor version={version} onSaved={query.setData} />}</QueryState>
}
