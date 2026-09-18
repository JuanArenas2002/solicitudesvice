import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Alert, AlertDescription, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, FloatingInput } from '@juanarenas31/metrik-ui'
import { useAuth } from '../auth/AuthProvider'
import { useSubmit } from '../hooks/useSubmit'

export default function LoginPage() {
  const { user, login } = useAuth()
  const from = (useLocation().state as { from?: string } | null)?.from ?? '/'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const submit = useSubmit(login)

  if (user) return <Navigate to={from} replace />

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    await submit.run(email, password)
  }

  return (
    <div className="grid min-h-screen place-items-center bg-bg p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <img src="/logo.svg" alt="Solicitudes VICE" className="mb-2 h-8 self-start" />
          <CardTitle>Iniciar sesión</CardTitle>
          <CardDescription>Solicitudes de registro de productos de investigación.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <FloatingInput label="Correo" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
            <FloatingInput label="Contraseña" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            {submit.error && <Alert tone="danger"><AlertDescription>{submit.error.message}</AlertDescription></Alert>}
            <Button type="submit" className="w-full" loading={submit.pending}>Entrar</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
