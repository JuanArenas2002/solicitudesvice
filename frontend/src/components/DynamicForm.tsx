import { Checkbox, ChipSelector, FloatingDatePicker, FloatingInput, FloatingSelect, FloatingTextarea, Label } from '@juanarenas31/metrik-ui'
import { JournalHint } from './JournalHint'
import type { AnswerValue, Answers, FormField, FormVersion } from '../api/types'

const HTML_INPUT: Partial<Record<FormField['type'], string>> = {
  INTEGER: 'number', DECIMAL: 'number', URL: 'url', EMAIL: 'email',
}
const HTML_MODE: Partial<Record<FormField['type'], 'numeric' | 'decimal'>> = { CEDULA: 'numeric', INTEGER: 'numeric', DECIMAL: 'decimal' }

const toDate = (v: AnswerValue) => (typeof v === 'string' && v ? new Date(`${v}T00:00:00`) : undefined)
const toIso = (d: Date | undefined) => (d ? d.toISOString().slice(0, 10) : null)

interface FieldProps {
  field: FormField
  value: AnswerValue | undefined
  error?: string
  disabled?: boolean
  /** Texto que explica por qué el campo no se puede cambiar (p. ej. la cédula con soportes). */
  lockedReason?: string
  onChange: (value: AnswerValue) => void
}

/** Un campo del formulario dinámico. Agregar un tipo nuevo = una rama aquí. */
export function DynamicField({ field, value, error, disabled: disabledProp, lockedReason, onChange }: FieldProps) {
  const disabled = disabledProp || !!lockedReason
  const label = field.required_to_submit ? `${field.label} *` : field.label
  const hint = error ?? lockedReason ?? field.help_text
  const hintNode = hint && <p className={error ? 'mt-1 text-xs text-danger' : 'mt-1 text-xs text-fg-muted'}>{hint}</p>
  const common = { label, disabled, 'aria-invalid': !!error }

  let control
  switch (field.type) {
    case 'LONG_TEXT':
      control = <FloatingTextarea {...common} rows={4} maxLength={field.max_length ?? undefined}
        value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)} />
      break
    case 'DATE':
      control = <FloatingDatePicker label={label} disabled={disabled} fromYear={1900} toYear={2100}
        value={toDate(value ?? null)} onValueChange={(d) => onChange(toIso(d))} />
      break
    case 'BOOLEAN':
      control = (
        <div className="flex items-center gap-2">
          <Checkbox id={field.key} disabled={disabled} checked={value === true} onCheckedChange={(c) => onChange(c === true)} />
          <Label htmlFor={field.key}>{label}</Label>
        </div>
      )
      break
    case 'SINGLE_SELECT':
      control = (
        <FloatingSelect {...common} value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value || null)}>
          <option value="" />
          {field.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </FloatingSelect>
      )
      break
    case 'MULTI_SELECT':
      control = (
        <div>
          <Label>{label}</Label>
          <ChipSelector options={field.options} value={(value as string[]) ?? []} allowEmpty onValueChange={onChange} />
        </div>
      )
      break
    default:
      control = (
        <FloatingInput {...common} type={HTML_INPUT[field.type] ?? 'text'}
          step={field.type === 'DECIMAL' ? 'any' : undefined}
          inputMode={HTML_MODE[field.type]} min={field.min_value ?? undefined} max={field.max_value ?? undefined}
          maxLength={field.type === 'CEDULA' ? 15 : field.max_length ?? undefined}
          value={(value as string | number) ?? ''}
          onChange={(e) => onChange(field.type === 'INTEGER' && e.target.value !== '' ? parseInt(e.target.value, 10) : e.target.value)} />
      )
  }
  return <div>{control}{hintNode}{field.type === 'ISSN' && typeof value === 'string' && <JournalHint issn={value} />}</div>
}

interface FormProps {
  form: FormVersion
  answers: Answers
  errors?: Record<string, string>
  disabled?: boolean
  /** clave del campo -> motivo por el que está bloqueado. */
  locked?: Record<string, string>
  onChange: (key: string, value: AnswerValue) => void
}

export function DynamicForm({ form, answers, errors = {}, disabled, locked = {}, onChange }: FormProps) {
  return (
    <div className="space-y-8">
      {form.sections.map((section) => ({ ...section, fields: section.fields.filter((f) => f.type !== 'SUPPORT') })).filter((s) => s.fields.length > 0).map((section) => (
        <section key={section.title} className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold">{section.title}</h2>
            {section.description && <p className="text-sm text-fg-muted">{section.description}</p>}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {section.fields.map((f) => (
              <div key={f.key} className={f.type === 'LONG_TEXT' || f.type === 'MULTI_SELECT' ? 'sm:col-span-2' : undefined}>
                <DynamicField field={f} value={answers[f.key]} error={errors[f.key]} disabled={disabled} lockedReason={locked[f.key]}
                  onChange={(v) => onChange(f.key, v)} />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
