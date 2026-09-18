import { useState, type FormEvent } from 'react'
import { KeyRound, Pencil, UserCheck } from 'lucide-react'
import {
  Alert, AlertDescription, Badge, Button, Checkbox, Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, FloatingInput, FloatingSelect, Label, Switch, useDebounce,
} from '@juanarenas31/metrik-ui'
import { catalogApi, usersApi } from '../api'
import type { NewUser, Role, User } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { IconButton } from '../components/IconButton'
import { PageHeader } from '../components/PageHeader'
import { QueryState } from '../components/QueryState'
import { ServerTable, type Column } from '../components/ServerTable'
import { ROLE_LABEL, formatDateTime } from '../constants'
import { useAsync } from '../hooks/useAsync'
import { useSubmit } from '../hooks/useSubmit'

const EMPTY: NewUser = { first_name: '', last_name: '', email: '', role: 'MENTOR', password: '' }

/** Crea (sin `user`) o edita (con `user`) una cuenta. La contraseña solo se pide al crear. */
function UserDialog({ user, onClose, onDone }: { user?: User; onClose: () => void; onDone: () => void }) {
  const [form, setForm] = useState<NewUser>(user ? { ...user, password: '' } : EMPTY)
  const [productIds, setProductIds] = useState<number[]>([])
  const products = useAsync(catalogApi.productTypes, [])
  const save = useSubmit(
    async (f: NewUser) => {
      if (user) return usersApi.update(user.id, { first_name: f.first_name, last_name: f.last_name, email: f.email, role: f.role })
      const created = await usersApi.create(f)
      // Un administrativo sin productos no ve solicitudes: se asignan desde el alta.
      if (created.role === 'ADMINISTRATIVO' && productIds.length) await usersApi.setProducts(created.id, productIds)
      return created
    },
    user ? 'Usuario actualizado' : 'Usuario creado',
  )
  const set = <K extends keyof NewUser>(key: K, value: NewUser[K]) => setForm((f) => ({ ...f, [key]: value }))

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (await save.run(form)) { onDone(); onClose() }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{user ? 'Editar usuario' : 'Nuevo usuario'}</DialogTitle></DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <FloatingInput label="Nombres" required value={form.first_name} onChange={(e) => set('first_name', e.target.value)} />
            <FloatingInput label="Apellidos" required value={form.last_name} onChange={(e) => set('last_name', e.target.value)} />
          </div>
          <FloatingInput label="Correo" type="email" required value={form.email} onChange={(e) => set('email', e.target.value)} />
          <FloatingSelect label="Rol" value={form.role} onChange={(e) => set('role', e.target.value as Role)}>
            {Object.entries(ROLE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </FloatingSelect>
          {!user && form.role === 'ADMINISTRATIVO' && (
            <div className="space-y-2">
              <Label>Productos que revisará</Label>
              {products.data?.items.map((p) => (
                <div key={p.id} className="flex items-center gap-2">
                  <Checkbox id={`new-p-${p.id}`} checked={productIds.includes(p.id)}
                    onCheckedChange={(c) => setProductIds(c === true ? [...productIds, p.id] : productIds.filter((x) => x !== p.id))} />
                  <Label htmlFor={`new-p-${p.id}`}>{p.name}</Label>
                </div>
              ))}
            </div>
          )}
          {!user && (
            <FloatingInput label="Contraseña inicial" type="password" autoComplete="new-password" required
              value={form.password} onChange={(e) => set('password', e.target.value)} />
          )}
          {save.error && <Alert tone="danger"><AlertDescription>{save.error.message}</AlertDescription></Alert>}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>Cancelar</Button>
            <Button type="submit" loading={save.pending}>{user ? 'Guardar' : 'Crear'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Qué productos (formularios) revisa un administrativo: solo verá y podrá revisar solicitudes de esos. */
function ProductsDialog({ user, onClose, onSaved }: { user: User; onClose: () => void; onSaved: () => void }) {
  const products = useAsync(catalogApi.productTypes, [])
  const assigned = useAsync(() => usersApi.products(user.id), [user.id])
  const [picked, setPicked] = useState<number[] | null>(null)
  const current = picked ?? assigned.data?.product_type_ids ?? []
  const save = useSubmit((ids: number[]) => usersApi.setProducts(user.id, ids).then(() => true), 'Productos asignados')
  const toggle = (id: number, on: boolean) => setPicked(on ? [...current, id] : current.filter((p) => p !== id))
  const onSave = async () => { if (await save.run(current)) { onSaved(); onClose() } }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Productos asignados</DialogTitle>
          <DialogDescription>
            {user.first_name} {user.last_name} solo verá y revisará las solicitudes de los productos marcados.
            Sin ninguno marcado no verá solicitudes.
          </DialogDescription>
        </DialogHeader>
        <QueryState query={assigned}>
          {() => (
            <QueryState query={products}>
              {(page) => (
                <div className="max-h-72 space-y-3 overflow-y-auto">
                  {page.items.map((p) => (
                    <div key={p.id} className="flex items-center gap-2">
                      <Checkbox id={`product-${p.id}`} checked={current.includes(p.id)}
                        onCheckedChange={(c) => toggle(p.id, c === true)} />
                      <Label htmlFor={`product-${p.id}`}>
                        {p.name}{!p.is_active && <span className="text-fg-muted"> (no disponible)</span>}
                      </Label>
                    </div>
                  ))}
                </div>
              )}
            </QueryState>
          )}
        </QueryState>
        {save.error && <Alert tone="danger"><AlertDescription>{save.error.message}</AlertDescription></Alert>}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button loading={save.pending} disabled={!assigned.data} onClick={onSave}>Guardar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ResetPasswordDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const [password, setPassword] = useState('')
  const reset = useSubmit((p: string) => usersApi.resetPassword(user.id, p).then(() => true), 'Contraseña temporal asignada')
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (await reset.run(password)) onClose()
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Contraseña temporal</DialogTitle>
          <DialogDescription>{user.email} · se cerrarán todas sus sesiones abiertas.</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <FloatingInput label="Nueva contraseña" type="password" autoComplete="new-password" required
            value={password} onChange={(e) => setPassword(e.target.value)} />
          {reset.error && <Alert tone="danger"><AlertDescription>{reset.error.message}</AlertDescription></Alert>}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>Cancelar</Button>
            <Button type="submit" loading={reset.pending}>Asignar</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default function UsersPage() {
  const { user: me } = useAuth()
  const [page, setPage] = useState(1)
  const [role, setRole] = useState<Role | ''>('')
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search.trim(), 400)
  const query = useAsync(
    () => usersApi.list(page, { role: role || undefined, search: debouncedSearch || undefined }),
    [page, role, debouncedSearch],
  )
  const [dialog, setDialog] = useState<'new' | User | null>(null)
  const [resetting, setResetting] = useState<User | null>(null)
  const [assigning, setAssigning] = useState<User | null>(null)
  const assignments = useAsync(usersApi.assignments, [])
  const products = useAsync(catalogApi.productTypes, [])
  const toggle = useSubmit(async (id: string, active: boolean) => { await usersApi.setActive(id, active); return true })

  // Los usuarios no se eliminan: se activan/desactivan. Uno no puede desactivarse a sí mismo.
  const columns: Column<User>[] = [
    { header: 'Nombre', cell: (u) => `${u.first_name} ${u.last_name}` },
    { header: 'Correo', cell: (u) => u.email },
    { header: 'Rol', cell: (u) => <Badge tone="neutral">{ROLE_LABEL[u.role]}</Badge> },
    {
      header: 'Productos',
      cell: (u) => {
        if (u.role !== 'ADMINISTRATIVO') return <span className="text-fg-muted">—</span>
        const ids = assignments.data?.[u.id] ?? []
        if (!assignments.data) return <span className="text-fg-muted">…</span>
        if (ids.length === 0) return <Badge tone="warning" dot title="Sin productos asignados no ve ninguna solicitud">Sin productos</Badge>
        const names = ids.map((id) => products.data?.items.find((p) => p.id === id)?.name ?? `#${id}`)
        return <div className="flex flex-wrap gap-1">{names.map((n) => <Badge key={n} tone="primary">{n}</Badge>)}</div>
      },
    },
    { header: 'Último acceso', cell: (u) => (u.last_login_at ? formatDateTime(u.last_login_at) : 'Nunca') },
    {
      header: 'Activo',
      cell: (u) => (
        <Switch checked={u.is_active} disabled={u.id === me?.id || toggle.pending} aria-label={`Activar ${u.email}`}
          onCheckedChange={async (active) => { if (await toggle.run(u.id, active)) query.reload() }} />
      ),
    },
    {
      header: 'Acciones',
      cell: (u) => (
        <div className="flex gap-2">
          <IconButton icon={Pencil} label="Editar usuario" onClick={() => setDialog(u)} />
          {u.role === 'ADMINISTRATIVO' && (
            <IconButton icon={UserCheck} label="Asignar productos que revisa" onClick={() => setAssigning(u)} />
          )}
          <IconButton icon={KeyRound} label="Contraseña temporal" variant="ghost" onClick={() => setResetting(u)} />
        </div>
      ),
    },
  ]

  return (
    <>
      <PageHeader title="Usuarios" description="Cuentas con acceso al sistema."
        actions={<Button onClick={() => setDialog('new')}>Nuevo usuario</Button>} />
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <FloatingInput label="Buscar por nombre o correo" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
        <FloatingSelect label="Rol" value={role} onChange={(e) => { setRole(e.target.value as Role | ''); setPage(1) }}>
          <option value="">Todos</option>
          {Object.entries(ROLE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </FloatingSelect>
      </div>
      {toggle.error && <Alert tone="danger" className="mb-4"><AlertDescription>{toggle.error.message}</AlertDescription></Alert>}
      <QueryState query={query}>
        {(data) => (
          <ServerTable data={data} columns={columns} rowKey={(u) => u.id} noun="usuarios" onPage={setPage} />
        )}
      </QueryState>
      {dialog && <UserDialog user={dialog === 'new' ? undefined : dialog} onClose={() => setDialog(null)} onDone={() => { query.reload(); assignments.reload() }} />}
      {assigning && <ProductsDialog user={assigning} onClose={() => setAssigning(null)} onSaved={assignments.reload} />}
      {resetting && <ResetPasswordDialog user={resetting} onClose={() => setResetting(null)} />}
    </>
  )
}
