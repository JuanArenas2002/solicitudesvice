import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, AlertDescription, Button, Card, CardContent, FloatingInput } from '@juanarenas31/metrik-ui'
import { authApi } from '../api'
import { PageHeader } from '../components/PageHeader'
import { useSubmit } from '../hooks/useSubmit'

export default function ChangePasswordPage() {
  const navigate = useNavigate()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const submit = useSubmit(async (c: string, n: string) => { await authApi.changePassword(c, n); return true }, 'Contraseña actualizada')
  const mismatch = confirm !== '' && next !== confirm

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    // El backend cierra las demás sesiones pero conserva la actual.
    if (await submit.run(current, next)) navigate('/')
  }

  return (
    <div className="mx-auto max-w-md">
      <PageHeader title="Cambiar contraseña" />
      <Card>
        <CardContent className="pt-6">
          <form onSubmit={onSubmit} className="space-y-4">
            <FloatingInput label="Contraseña actual" type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
            <FloatingInput label="Nueva contraseña" type="password" autoComplete="new-password" required value={next} onChange={(e) => setNext(e.target.value)} />
            <FloatingInput label="Confirmar nueva contraseña" type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} aria-invalid={mismatch} />
            {mismatch && <p className="text-xs text-danger">Las contraseñas no coinciden.</p>}
            {submit.error && <Alert tone="danger"><AlertDescription>{submit.error.message}</AlertDescription></Alert>}
            <Button type="submit" loading={submit.pending} disabled={mismatch || !next}>Actualizar</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
