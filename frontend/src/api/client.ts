/** Cliente HTTP único. El access token vive solo en memoria; el refresh va en cookie HttpOnly. */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
    public field?: string,
    public missing?: string[],
  ) {
    super(message)
  }
}

const BASE = '/api/v1'

let accessToken: string | null = null
let onSessionLost: () => void = () => {}

export const setAccessToken = (token: string | null) => { accessToken = token }
export const setSessionLostHandler = (fn: () => void) => { onSessionLost = fn }

const cookie = (name: string) =>
  document.cookie.split('; ').find((c) => c.startsWith(`${name}=`))?.split('=')[1]

async function send(path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers)
  // FormData fija su propio Content-Type (con el boundary); solo el JSON se declara aquí.
  if (typeof init.body === 'string') headers.set('Content-Type', 'application/json')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  if (path === '/auth/refresh') {
    const csrf = cookie('csrf_token') // doble envío: el servidor lo compara con la cookie de refresh
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf))
  }
  return fetch(`${BASE}${path}`, { ...init, headers, credentials: 'include' })
}

// Un único refresh en vuelo: varias peticiones con 401 simultáneas no rotan el token varias veces.
let refreshing: Promise<boolean> | null = null
/** También la usa el arranque: el refresh token es de un solo uso, dos rotaciones a la vez cerrarían la sesión. */
export async function refresh(): Promise<boolean> {
  refreshing ??= send('/auth/refresh', { method: 'POST' })
    .then(async (res) => {
      if (!res.ok) return false
      accessToken = (await res.json()).access_token
      return true
    })
    .finally(() => { refreshing = null })
  return refreshing
}

/** Errores del backend: `{detail, code, field?, missing?}` o, en validación, `{errors:[{loc,message}]}`. */
async function toError(res: Response): Promise<ApiError> {
  const body = await res.json().catch(() => ({}))
  if (body.code === 'ValidationError' && Array.isArray(body.errors) && body.errors.length) {
    const first = body.errors[0] as { loc: string[]; message: string }
    return new ApiError(res.status, first.message, body.code, first.loc[first.loc.length - 1])
  }
  const message = typeof body.detail === 'string' ? body.detail : 'Error inesperado'
  return new ApiError(res.status, message, body.code, body.field, body.missing)
}

async function request(path: string, init: RequestInit): Promise<Response> {
  let res = await send(path, init)
  const isAuth = path.startsWith('/auth/')
  if (res.status === 401 && !isAuth && (await refresh())) res = await send(path, init)
  if (res.status === 401 && !isAuth) onSessionLost()
  if (!res.ok) throw await toError(res)
  return res
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init
  const res = await request(path, { ...rest, body: json === undefined ? rest.body : JSON.stringify(json) })
  return res.status === 204 ? (undefined as T) : res.json()
}

/** Descarga autenticada: el navegador no puede enviar el Bearer en un enlace, se baja como blob. */
export async function download(path: string, fallbackName: string): Promise<void> {
  const res = await request(path, {})
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fallbackName
  link.click()
  URL.revokeObjectURL(url)
}
