import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Spinner } from '@juanarenas31/metrik-ui'
import { useAuth } from './AuthProvider'

/** Exige sesión; con `permission` exige además ese permiso (el backend sigue siendo la autoridad). */
export function RequireAuth({ permission }: { permission?: string }) {
  const { user, loading, can } = useAuth()
  const location = useLocation()

  if (loading) return <div className="grid min-h-screen place-items-center"><Spinner size="lg" label="Cargando" /></div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (permission && !can(permission)) return <Navigate to="/" replace />
  return <Outlet />
}
