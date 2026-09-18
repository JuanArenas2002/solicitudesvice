import type { BadgeProps } from '@juanarenas31/metrik-ui'
import type { FieldType, FormStatus, RequestAction, RequestStatus, Role } from './api/types'

type Tone = NonNullable<BadgeProps['tone']>

export const STATUS: Record<RequestStatus, { label: string; tone: Tone }> = {
  BORRADOR: { label: 'Borrador', tone: 'neutral' },
  ENVIADA: { label: 'Enviada', tone: 'info' },
  EN_REVISION: { label: 'En revisión', tone: 'primary' },
  CORRECCION_SOLICITADA: { label: 'Corrección solicitada', tone: 'warning' },
  REENVIADA: { label: 'Reenviada', tone: 'info' },
  APROBADA: { label: 'Aprobada', tone: 'success' },
  RECHAZADA: { label: 'Rechazada', tone: 'danger' },
}

export const FORM_STATUS: Record<FormStatus, { label: string; tone: Tone }> = {
  BORRADOR: { label: 'Borrador', tone: 'warning' },
  PUBLICADA: { label: 'Publicada', tone: 'success' },
  RETIRADA: { label: 'Retirada', tone: 'neutral' },
}

/** Etiqueta de cada acción y si pide texto (motivo / descripción de la corrección). */
export const ACTIONS: Record<RequestAction, { label: string; variant: 'primary' | 'outline' | 'danger'; text?: 'required' | 'optional'; textLabel?: string }> = {
  submit: { label: 'Enviar', variant: 'primary' },
  resubmit: { label: 'Reenviar', variant: 'primary' },
  review: { label: 'Tomar en revisión', variant: 'primary' },
  approve: { label: 'Aprobar', variant: 'primary', text: 'optional', textLabel: 'Motivo' },
  'request-correction': { label: 'Solicitar corrección', variant: 'outline', text: 'required', textLabel: 'Qué debe corregir el mentor' },
  reject: { label: 'Rechazar', variant: 'danger', text: 'required', textLabel: 'Motivo del rechazo' },
}

export const ROLE_LABEL: Record<Role, string> = {
  ADMIN: 'Administrador',
  ADMINISTRATIVO: 'Administrativo',
  MENTOR: 'Mentor',
}

export const FIELD_TYPE: Record<FieldType, string> = {
  CEDULA: 'Cédula',
  SUPPORT: 'Soporte (archivo adjunto)',
  TEXT: 'Texto corto',
  LONG_TEXT: 'Texto largo',
  INTEGER: 'Número entero',
  DECIMAL: 'Número decimal',
  DATE: 'Fecha',
  BOOLEAN: 'Sí / No',
  SINGLE_SELECT: 'Selección única',
  MULTI_SELECT: 'Selección múltiple',
  URL: 'Enlace (URL)',
  DOI: 'DOI',
  ISSN: 'ISSN',
  EMAIL: 'Correo',
}

/** Tipos de documento que puede admitir un campo de soporte (extensión -> cómo se muestra). */
export const DOCUMENT_TYPES: { value: string; label: string }[] = [
  { value: 'pdf', label: 'PDF (.pdf)' },
  { value: 'docx', label: 'Word (.docx)' },
  { value: 'doc', label: 'Word antiguo (.doc)' },
  { value: 'xlsx', label: 'Excel (.xlsx)' },
  { value: 'xls', label: 'Excel antiguo (.xls)' },
  { value: 'pptx', label: 'PowerPoint (.pptx)' },
  { value: 'ppt', label: 'PowerPoint antiguo (.ppt)' },
  { value: 'png', label: 'Imagen (.png)' },
  { value: 'jpg', label: 'Imagen (.jpg)' },
  { value: 'jpeg', label: 'Imagen (.jpeg)' },
  { value: 'zip', label: 'Comprimido (.zip)' },
]

/** Todo formulario tiene un campo con esta clave y tipo CEDULA: define la carpeta de soportes. */
export const IDENTITY_KEY = 'cedula'

/** Nombres de permiso del backend (app/domain/enums/permission.py). */
export const PERM = {
  manageUsers: 'MANAGE_USERS',
  manageForms: 'MANAGE_FORMS',
  createRequest: 'CREATE_REQUEST',
  reviewRequest: 'REVIEW_REQUEST',
  requestCorrection: 'REQUEST_CORRECTION',
  approveRequest: 'APPROVE_REQUEST',
  rejectRequest: 'REJECT_REQUEST',
  downloadAttachments: 'DOWNLOAD_ATTACHMENTS',
  changeStatus: 'CHANGE_REQUEST_STATUS',
} as const

export const formatDateTime = (iso: string) =>
  new Date(iso).toLocaleString('es', { dateStyle: 'medium', timeStyle: 'short' })

export const formatSize = (bytes: number) =>
  bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(0)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`
