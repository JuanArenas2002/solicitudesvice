export type Role = 'ADMIN' | 'ADMINISTRATIVO' | 'MENTOR'

export type RequestStatus =
  | 'BORRADOR' | 'ENVIADA' | 'EN_REVISION' | 'CORRECCION_SOLICITADA'
  | 'REENVIADA' | 'APROBADA' | 'RECHAZADA'

export type FieldType =
  | 'CEDULA' | 'SUPPORT' | 'TEXT' | 'LONG_TEXT' | 'INTEGER' | 'DECIMAL' | 'DATE' | 'BOOLEAN'
  | 'SINGLE_SELECT' | 'MULTI_SELECT' | 'URL' | 'DOI' | 'ISSN' | 'EMAIL'

export type FormStatus = 'BORRADOR' | 'PUBLICADA' | 'RETIRADA'

export interface User {
  id: string
  first_name: string
  last_name: string
  email: string
  role: Role
  is_active: boolean
  permissions: string[]
  created_at: string
  updated_at: string
  last_login_at: string | null
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface Session { access_token: string; expires_in: number; user: User }
export interface Token { access_token: string; expires_in: number }

// ---------- formularios ----------
export interface FormOption { value: string; label: string }

export interface FormField {
  key: string
  label: string
  type: FieldType
  required_to_submit: boolean
  help_text: string | null
  min_length: number | null
  max_length: number | null
  /** Decimal serializado como texto. */
  min_value: string | number | null
  max_value: string | number | null
  options: FormOption[]
  /** Solo SUPPORT: extensiones de archivo que admite el campo. */
  allowed_types: string[]
}

export interface FormSection { title: string; description: string | null; fields: FormField[] }

export interface FormVersion {
  id: number
  product_type_id: number
  version_number: number
  status: FormStatus
  created_at: string
  published_at: string | null
  retired_at: string | null
  sections: FormSection[]
}

export interface FormVersionSummary {
  id: number
  version_number: number
  status: FormStatus
  created_at: string
  published_at: string | null
  retired_at: string | null
}

export interface ProductType {
  id: number
  code: string
  name: string
  description: string | null
  folder_name: string
  is_active: boolean
}

export interface NewProductType { code: string; name: string; description?: string; folder_name?: string }

// ---------- solicitudes ----------
export type AnswerValue = string | number | boolean | string[] | null
export type Answers = Record<string, AnswerValue>

export interface Person { id: string; name: string }

export interface RequestSummary {
  id: string
  request_number: string
  status: RequestStatus
  mentor: Person
  product_type_id: number
  product_type_code: string
  product_type_name: string
  version: number
  created_at: string
  updated_at: string
  submitted_at: string | null
  reviewed_at: string | null
}

export interface Correction {
  id: string
  description: string
  status: 'ABIERTA' | 'RESUELTA'
  requested_by: string
  created_at: string
  resolved_at: string | null
}

export interface RequestDetail {
  id: string
  request_number: string
  status: RequestStatus
  mentor: Person
  product_type: ProductType
  form_version_id: number
  version: number
  is_editable: boolean
  created_at: string
  updated_at: string
  submitted_at: string | null
  reviewed_at: string | null
  form: FormVersion
  answers: Answers
  missing_required: string[]
  open_correction: Correction | null
}

export interface HistoryEntry {
  previous_status: RequestStatus | null
  new_status: RequestStatus
  changed_by: string
  reason: string | null
  occurred_at: string
}

export interface RequestFilters {
  status?: RequestStatus
  product_type_id?: number
  request_number?: string
}

export type RequestAction = 'submit' | 'review' | 'request-correction' | 'resubmit' | 'approve' | 'reject'

export interface Attachment {
  id: string
  /** Campo de soporte del formulario al que pertenece. */
  field_key: string
  file_name: string
  mime_type: string
  file_size: number
  sha256: string
  /** Carpeta lógica: `<cédula>/<producto>/Solicitud N`. */
  folder: string
  uploaded_by: string
  created_at: string
}

// ---------- usuarios ----------
export interface NewUser {
  first_name: string
  last_name: string
  email: string
  role: Role
  password: string
}

export interface Journal {
  title: string
  publisher: string | null
  country: string | null
  issn_print: string | null
  eissn: string | null
  open_access: boolean | null
}

export interface AppNotification {
  id: string
  request_id: string
  request_number: string
  /** Estado al que pasó la solicitud. */
  status: RequestStatus
  reason: string | null
  created_at: string
  read_at: string | null
}

export interface UserFilters { role?: Role; is_active?: boolean; search?: string }
