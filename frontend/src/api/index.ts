import { api, download } from './client'
import type {
  Answers, Attachment, FormVersion, FormVersionSummary, HistoryEntry, NewProductType, NewUser, Page,
  ProductType, RequestAction, RequestDetail, RequestFilters, RequestStatus, RequestSummary, Role, Session,
  User, UserFilters, FormSection, Journal, AppNotification,
} from './types'

const query = (params: Record<string, string | number | boolean | undefined>) => {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') q.set(k, String(v))
  return q.toString()
}

export const authApi = {
  login: (email: string, password: string) =>
    api<Session>('/auth/login', { method: 'POST', json: { email, password } }),
  me: () => api<User>('/auth/me'),
  logout: () => api<void>('/auth/logout', { method: 'POST' }),
  changePassword: (current_password: string, new_password: string) =>
    api<void>('/auth/change-password', { method: 'POST', json: { current_password, new_password } }),
}

export const requestsApi = {
  list: (page: number, filters: RequestFilters = {}) =>
    api<Page<RequestSummary>>(`/requests?${query({ page, page_size: 20, ...filters })}`),
  get: (id: string) => api<RequestDetail>(`/requests/${id}`),
  history: (id: string) => api<HistoryEntry[]>(`/requests/${id}/history`),
  create: (product_type_id: number) =>
    api<RequestDetail>('/requests', { method: 'POST', json: { product_type_id } }),
  saveAnswers: (id: string, version: number, answers: Answers) =>
    api<RequestDetail>(`/requests/${id}/answers`, { method: 'PATCH', json: { version, answers } }),
  /** Personal administrativo: pasa a cualquier estado (menos borrador) con un motivo. */
  changeStatus: (id: string, status: RequestStatus, reason: string) =>
    api<RequestDetail>(`/requests/${id}/change-status`, { method: 'POST', json: { status, reason } }),
  /** El flujo normal no envía estados: cada transición es su propio endpoint. */
  act: (id: string, action: RequestAction, text?: string) => {
    const body =
      action === 'request-correction' ? { description: text }
        : action === 'approve' || action === 'reject' ? { reason: text || undefined }
          : undefined
    return api<RequestDetail>(`/requests/${id}/${action}`, { method: 'POST', json: body })
  },
}

export const journalsApi = {
  lookup: (issn: string) => api<Journal>(`/journals/${encodeURIComponent(issn)}`),
}

export const notificationsApi = {
  list: (unreadOnly = false) =>
    api<Page<AppNotification> & { unread: number }>(`/notifications?page_size=15${unreadOnly ? '&unread_only=true' : ''}`),
  unreadCount: () => api<{ unread: number }>('/notifications/unread-count'),
  /** Sin ids marca todas como leídas. */
  markRead: (ids?: string[]) => api<void>('/notifications/read', { method: 'POST', json: ids ? { ids } : {} }),
}

export const attachmentsApi = {
  list: (requestId: string) => api<Attachment[]>(`/requests/${requestId}/attachments`),
  upload: (requestId: string, fieldKey: string, file: File) => {
    const body = new FormData()
    body.append('field_key', fieldKey)
    body.append('file', file)
    return api<Attachment>(`/requests/${requestId}/attachments`, { method: 'POST', body })
  },
  download: (requestId: string, a: Attachment) =>
    download(`/requests/${requestId}/attachments/${a.id}/download`, a.file_name),
  remove: (requestId: string, id: string) =>
    api<void>(`/requests/${requestId}/attachments/${id}`, { method: 'DELETE' }),
}

export const catalogApi = {
  productTypes: () => api<Page<ProductType>>('/product-types?page=1&page_size=100'),
  createProduct: (p: NewProductType) => api<ProductType>('/product-types', { method: 'POST', json: p }),
  setProductActive: (id: number, is_active: boolean) =>
    api<ProductType>(`/product-types/${id}`, { method: 'PATCH', json: { is_active } }),
  publishedForm: (productId: number) => api<FormVersion>(`/product-types/${productId}/form`),
  versions: (productId: number) => api<FormVersionSummary[]>(`/product-types/${productId}/form-versions`),
  openDraft: (productId: number) =>
    api<FormVersion>(`/product-types/${productId}/form-versions`, { method: 'POST' }),
  version: (versionId: number) => api<FormVersion>(`/form-versions/${versionId}`),
  saveDraft: (versionId: number, sections: FormSection[]) =>
    api<FormVersion>(`/form-versions/${versionId}`, { method: 'PUT', json: { sections } }),
  publish: (versionId: number) => api<FormVersion>(`/form-versions/${versionId}/publish`, { method: 'POST' }),
}

export const usersApi = {
  list: (page: number, filters: UserFilters = {}, pageSize = 20) =>
    api<Page<User>>(`/users?${query({ page, page_size: pageSize, ...filters })}`),
  /** Productos que revisa cada administrativo: { id de usuario: [ids de producto] }. */
  assignments: () => api<Record<string, number[]>>('/users/product-assignments'),
  create: (user: NewUser) => api<User>('/users', { method: 'POST', json: user }),
  update: (id: string, changes: Partial<{ first_name: string; last_name: string; email: string; role: Role }>) =>
    api<User>(`/users/${id}`, { method: 'PATCH', json: changes }),
  setActive: (id: string, active: boolean) =>
    api<User>(`/users/${id}/${active ? 'activate' : 'deactivate'}`, { method: 'PATCH' }),
  products: (id: string) => api<{ product_type_ids: number[] }>(`/users/${id}/products`),
  setProducts: (id: string, product_type_ids: number[]) =>
    api<{ product_type_ids: number[] }>(`/users/${id}/products`, { method: 'PUT', json: { product_type_ids } }),
  resetPassword: (id: string, new_password: string) =>
    api<void>(`/users/${id}/reset-password`, { method: 'POST', json: { new_password } }),
}
