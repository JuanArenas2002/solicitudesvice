import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { authApi } from '../api'
import { refresh, setAccessToken, setSessionLostHandler } from '../api/client'
import type { Session, User } from '../api/types'

interface AuthState {
  user: User | null
  /** true mientras se intenta restaurar la sesión con la cookie de refresh. */
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  can: (permission: string) => boolean
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const start = useCallback((s: Session) => { setAccessToken(s.access_token); setUser(s.user) }, [])
  const clear = useCallback(() => { setAccessToken(null); setUser(null) }, [])

  useEffect(() => {
    setSessionLostHandler(clear)
    // Restaurar sesión: la cookie de refresh entrega un access token y con él se pide el usuario.
    refresh()
      .then(async (ok) => { if (!ok) throw new Error('sin sesión'); setUser(await authApi.me()) })
      .catch(clear)
      .finally(() => setLoading(false))
  }, [start, clear])

  const value = useMemo<AuthState>(() => ({
    user,
    loading,
    login: async (email, password) => start(await authApi.login(email, password)),
    logout: async () => { await authApi.logout().catch(() => {}); clear() },
    can: (permission) => !!user?.permissions.includes(permission),
  }), [user, loading, start, clear])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  return ctx
}
