import { ArrowDown, ArrowUp, Trash2, X } from 'lucide-react'
import {
  Alert, AlertDescription, Badge, Button, Card, CardContent, ChipSelector, FloatingInput, FloatingSelect,
  FloatingTextarea, Label, Separator,
} from '@juanarenas31/metrik-ui'
import type { FieldType, FormField, FormOption, FormSection } from '../api/types'
import { DOCUMENT_TYPES, FIELD_TYPE, IDENTITY_KEY } from '../constants'
import { IconButton } from './IconButton'

const SELECTS: FieldType[] = ['SINGLE_SELECT', 'MULTI_SELECT']
const RANGES: FieldType[] = ['INTEGER', 'DECIMAL']
const LENGTHS: FieldType[] = ['TEXT', 'LONG_TEXT']

/** Los tipos que se pueden elegir. CEDULA no: es el campo reservado que ya trae todo formulario. */
const TYPES = (Object.keys(FIELD_TYPE) as FieldType[]).filter((t) => t !== 'CEDULA')

export const CEDULA_FIELD: FormField = {
  key: IDENTITY_KEY, label: 'Cédula', type: 'CEDULA', required_to_submit: true, help_text: null,
  min_length: null, max_length: null, min_value: null, max_value: null, options: [], allowed_types: [],
}

/** "Título del artículo" -> "titulo_del_articulo": las claves son estables (minúsculas, dígitos y _). */
export const slug = (text: string) => {
  const s = text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
  return (/^[0-9]/.test(s) ? `c_${s}` : s).slice(0, 60)
}

export const newField = (): FormField => ({
  key: '', label: '', type: 'TEXT', required_to_submit: false, help_text: null,
  min_length: null, max_length: null, min_value: null, max_value: null, options: [], allowed_types: [],
})

const num = (v: string): number | null => (v === '' || Number.isNaN(Number(v)) ? null : Number(v))
const move = <T,>(list: T[], from: number, to: number): T[] => {
  if (to < 0 || to >= list.length) return list
  const copy = [...list]
  copy.splice(to, 0, copy.splice(from, 1)[0])
  return copy
}
const patch = <T,>(list: T[], i: number, changes: Partial<T>): T[] => list.map((x, j) => (j === i ? { ...x, ...changes } : x))

function OptionsEditor({ options, readOnly, onChange }: { options: FormOption[]; readOnly: boolean; onChange: (o: FormOption[]) => void }) {
  return (
    <div className="space-y-2">
      <Label>Opciones</Label>
      {options.map((o, i) => (
        <div key={i} className="grid grid-cols-[1fr_1fr_auto] items-start gap-2">
          <FloatingInput label="Etiqueta" value={o.label} disabled={readOnly}
            onChange={(e) => onChange(patch(options, i, { label: e.target.value, ...(o.value === slug(o.label) ? { value: slug(e.target.value) } : {}) }))} />
          <FloatingInput label="Valor" value={o.value} disabled={readOnly}
            onChange={(e) => onChange(patch(options, i, { value: e.target.value }))} />
          {!readOnly && <IconButton icon={X} label="Quitar opción" variant="ghost" onClick={() => onChange(options.filter((_, j) => j !== i))} />}
        </div>
      ))}
      {!readOnly && <Button size="sm" variant="outline" onClick={() => onChange([...options, { value: '', label: '' }])}>Agregar opción</Button>}
    </div>
  )
}

function FieldEditor({ field, index, count, readOnly, onChange, onMove, onRemove }: {
  field: FormField; index: number; count: number; readOnly: boolean
  onChange: (changes: Partial<FormField>) => void; onMove: (to: number) => void; onRemove: () => void
}) {
  const reserved = field.key === IDENTITY_KEY && field.type === 'CEDULA'
  const locked = readOnly || reserved
  const changeType = (type: FieldType) =>
    // Al cambiar de tipo se descartan las restricciones que ya no aplican.
    onChange({
      type,
      min_length: null, max_length: null, min_value: null, max_value: null,
      options: SELECTS.includes(type) ? (field.options.length ? field.options : [{ value: '', label: '' }]) : [],
      allowed_types: type === 'SUPPORT' ? (field.allowed_types.length ? field.allowed_types : ['pdf']) : [],
    })

  return (
    <div className="space-y-3 rounded-md border border-border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          {field.label || 'Campo nuevo'}
          {reserved && <Badge tone="primary">Define la carpeta de soportes</Badge>}
          {field.type === 'SUPPORT' && <Badge tone="info">Soporte</Badge>}
        </div>
        {!readOnly && (
          <div className="flex gap-1">
            <IconButton icon={ArrowUp} label="Subir" variant="ghost" disabled={index === 0} onClick={() => onMove(index - 1)} />
            <IconButton icon={ArrowDown} label="Bajar" variant="ghost" disabled={index === count - 1} onClick={() => onMove(index + 1)} />
            {!reserved && <IconButton icon={Trash2} label="Eliminar campo" variant="ghost" onClick={onRemove} />}
          </div>
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <FloatingInput label="Etiqueta" value={field.label} disabled={locked} maxLength={200}
          onChange={(e) => onChange({ label: e.target.value, ...(field.key === slug(field.label) ? { key: slug(e.target.value) } : {}) })} />
        <FloatingInput label="Clave (identificador estable)" value={field.key} disabled={locked} maxLength={60}
          onChange={(e) => onChange({ key: e.target.value })} />
        <FloatingSelect label="Tipo" value={field.type} disabled={locked} onChange={(e) => changeType(e.target.value as FieldType)}>
          {reserved ? <option value="CEDULA">{FIELD_TYPE.CEDULA}</option> : TYPES.map((t) => <option key={t} value={t}>{FIELD_TYPE[t]}</option>)}
        </FloatingSelect>
        <FloatingSelect label="¿Es obligatorio?" value={field.required_to_submit ? 'yes' : 'no'} disabled={locked}
          onChange={(e) => onChange({ required_to_submit: e.target.value === 'yes' })}>
          <option value="no">No, es opcional</option>
          <option value="yes">Sí, hay que llenarlo para enviar</option>
        </FloatingSelect>
      </div>
      <FloatingInput label="Texto de ayuda (opcional)" value={field.help_text ?? ''} disabled={readOnly} maxLength={500}
        onChange={(e) => onChange({ help_text: e.target.value || null })} />
      {field.type === 'SUPPORT' && (
        <div className="space-y-3 rounded-md bg-surface-muted p-3">
          <Alert tone="info">
            <AlertDescription>
              Es un <strong>soporte</strong>: el mentor no escribe un texto, adjunta archivos. Elige qué tipos de
              documento puede subir en este campo.
              {field.required_to_submit && ' Como es obligatorio, tendrá que subir al menos un archivo para enviar.'}
            </AlertDescription>
          </Alert>
          <div>
            <Label>Tipos de documento permitidos</Label>
            <ChipSelector options={DOCUMENT_TYPES} value={field.allowed_types} allowEmpty
              onValueChange={(allowed_types) => onChange({ allowed_types })}
              className={readOnly ? 'pointer-events-none opacity-60' : undefined} />
            {field.allowed_types.length === 0 && <p className="mt-1 text-xs text-danger">Elige al menos un tipo de documento.</p>}
          </div>
        </div>
      )}
      {LENGTHS.includes(field.type) && (
        <div className="grid gap-3 sm:grid-cols-2">
          <FloatingInput label="Longitud mínima" type="number" min={0} value={field.min_length ?? ''} disabled={readOnly}
            onChange={(e) => onChange({ min_length: num(e.target.value) })} />
          <FloatingInput label="Longitud máxima" type="number" min={1} value={field.max_length ?? ''} disabled={readOnly}
            onChange={(e) => onChange({ max_length: num(e.target.value) })} />
        </div>
      )}
      {RANGES.includes(field.type) && (
        <div className="grid gap-3 sm:grid-cols-2">
          <FloatingInput label="Valor mínimo" type="number" step="any" value={field.min_value ?? ''} disabled={readOnly}
            onChange={(e) => onChange({ min_value: num(e.target.value) })} />
          <FloatingInput label="Valor máximo" type="number" step="any" value={field.max_value ?? ''} disabled={readOnly}
            onChange={(e) => onChange({ max_value: num(e.target.value) })} />
        </div>
      )}
      {SELECTS.includes(field.type) && <OptionsEditor options={field.options} readOnly={readOnly} onChange={(options) => onChange({ options })} />}
    </div>
  )
}

interface Props { sections: FormSection[]; readOnly: boolean; onChange: (sections: FormSection[]) => void }

/** Editor del documento completo del formulario (secciones → campos → opciones). */
export function FormBuilder({ sections, readOnly, onChange }: Props) {
  const setSection = (i: number, changes: Partial<FormSection>) => onChange(patch(sections, i, changes))
  return (
    <div className="space-y-6">
      {sections.map((section, si) => (
        <Card key={si}>
          <CardContent className="space-y-4 pt-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-fg-muted">Sección {si + 1}</h2>
              {!readOnly && (
                <div className="flex gap-1">
                  <IconButton icon={ArrowUp} label="Subir sección" variant="ghost" disabled={si === 0} onClick={() => onChange(move(sections, si, si - 1))} />
                  <IconButton icon={ArrowDown} label="Bajar sección" variant="ghost" disabled={si === sections.length - 1} onClick={() => onChange(move(sections, si, si + 1))} />
                  <IconButton icon={Trash2} label="Eliminar sección" variant="ghost" onClick={() => onChange(sections.filter((_, j) => j !== si))} />
                </div>
              )}
            </div>
            <FloatingInput label="Título de la sección" value={section.title} disabled={readOnly} maxLength={200}
              onChange={(e) => setSection(si, { title: e.target.value })} />
            <FloatingTextarea label="Descripción (opcional)" rows={2} value={section.description ?? ''} disabled={readOnly} maxLength={500}
              onChange={(e) => setSection(si, { description: e.target.value || null })} />
            <Separator />
            {section.fields.map((field, fi) => (
              <FieldEditor key={fi} field={field} index={fi} count={section.fields.length} readOnly={readOnly}
                onChange={(changes) => setSection(si, { fields: patch(section.fields, fi, changes) })}
                onMove={(to) => setSection(si, { fields: move(section.fields, fi, to) })}
                onRemove={() => setSection(si, { fields: section.fields.filter((_, j) => j !== fi) })} />
            ))}
            {!readOnly && (
              <Button variant="outline" onClick={() => setSection(si, { fields: [...section.fields, newField()] })}>Agregar campo</Button>
            )}
          </CardContent>
        </Card>
      ))}
      {!readOnly && (
        <Button variant="outline" onClick={() => onChange([...sections, { title: '', description: null, fields: [] }])}>Agregar sección</Button>
      )}
    </div>
  )
}
