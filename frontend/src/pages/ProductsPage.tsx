import { useState, type FormEvent } from 'react'
import { FilePenLine, Users } from 'lucide-react'
import {
  Alert, AlertDescription, Badge, Button, Checkbox, DataTable, Dialog, Label, DialogContent, DialogDescription, DialogFooter, DialogHeader,
  DialogTitle, FloatingInput, FloatingTextarea, Switch, type ColumnDef,
} from '@juanarenas31/metrik-ui'
import { catalogApi, usersApi } from '../api'
import type { NewProductType, ProductType, User } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { PERM } from '../constants'
import { IconButton } from '../components/IconButton'
import { PageHeader } from '../components/PageHeader'
import { QueryState } from '../components/QueryState'
import { slug } from '../components/FormBuilder'
import { useAsync } from '../hooks/useAsync'
import { useSubmit } from '../hooks/useSubmit'

const EMPTY = { code: '', name: '', description: '', folder_name: '' }

function NewProductDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState(EMPTY)
  const create = useSubmit((p: NewProductType) => catalogApi.createProduct(p), 'Producto creado')
  const set = (key: keyof typeof EMPTY, value: string) => setForm((f) => ({ ...f, [key]: value }))

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const created = await create.run({
      code: form.code,
      name: form.name,
      description: form.description || undefined,
      folder_name: form.folder_name || undefined,
    })
    if (created) { onCreated(); onClose() }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo producto</DialogTitle>
          <DialogDescription>Al crearlo queda listo su primer borrador de formulario.</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <FloatingInput label="Nombre" required maxLength={120} value={form.name}
            onChange={(e) => {
              set('name', e.target.value)
              if (form.code === slug(form.name).toUpperCase()) set('code', slug(e.target.value).toUpperCase())
            }} />
          <FloatingInput label="Código (MAYÚSCULAS, p. ej. LIBRO)" required maxLength={30} value={form.code}
            onChange={(e) => set('code', e.target.value.toUpperCase())} />
          <div>
            <FloatingInput label="Carpeta de soportes" maxLength={50} value={form.folder_name}
              onChange={(e) => set('folder_name', e.target.value)} />
            <p className="mt-1 text-xs text-fg-muted">
              Los soportes irán en cédula / {form.folder_name || 'Carpeta'} / Solicitud N. Si la dejas vacía se toma del
              nombre. No se puede cambiar después.
            </p>
          </div>
          <FloatingTextarea label="Descripción (opcional)" rows={2} maxLength={500} value={form.description}
            onChange={(e) => set('description', e.target.value)} />
          {create.error && <Alert tone="danger"><AlertDescription>{create.error.message}</AlertDescription></Alert>}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>Cancelar</Button>
            <Button type="submit" loading={create.pending}>Crear</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Qué administrativos revisan un producto (la misma asignación que se ve en Usuarios). */
function ReviewersDialog({ product, onClose, onSaved }: { product: ProductType; onClose: () => void; onSaved: () => void }) {
  const staff = useAsync(() => usersApi.list(1, { role: 'ADMINISTRATIVO' }, 100), [])
  const assigned = useAsync(usersApi.assignments, [])
  const [picked, setPicked] = useState<Set<string> | null>(null)
  const original = new Set(Object.entries(assigned.data ?? {}).filter(([, ids]) => ids.includes(product.id)).map(([id]) => id))
  const current = picked ?? original

  const save = useSubmit(async (users: User[]) => {
    // Solo se tocan los administrativos cuya asignación a ESTE producto cambió; sus otros productos se conservan.
    for (const u of users) {
      const ids = new Set(assigned.data?.[u.id] ?? [])
      if (current.has(u.id)) ids.add(product.id); else ids.delete(product.id)
      await usersApi.setProducts(u.id, [...ids])
    }
    return true
  }, 'Revisores actualizados')
  const onSave = async () => {
    const changed = (staff.data?.items ?? []).filter((u) => current.has(u.id) !== original.has(u.id))
    if (changed.length === 0 || (await save.run(changed))) { onSaved(); onClose() }
  }
  const toggle = (id: string, on: boolean) => {
    const next = new Set(current)
    if (on) next.add(id); else next.delete(id)
    setPicked(next)
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Revisores de {product.name}</DialogTitle>
          <DialogDescription>Solo los administrativos marcados ven y revisan las solicitudes de este producto.</DialogDescription>
        </DialogHeader>
        <QueryState query={staff}>
          {(page) => (
            <QueryState query={assigned}>
              {() => page.items.length === 0 ? (
                <p className="text-sm text-fg-muted">Aún no hay usuarios administrativos.</p>
              ) : (
                <div className="max-h-72 space-y-3 overflow-y-auto">
                  {page.items.map((u) => (
                    <div key={u.id} className="flex items-center gap-2">
                      <Checkbox id={`rev-${u.id}`} checked={current.has(u.id)} onCheckedChange={(c) => toggle(u.id, c === true)} />
                      <Label htmlFor={`rev-${u.id}`}>{u.first_name} {u.last_name} <span className="text-fg-muted">· {u.email}</span></Label>
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
          <Button loading={save.pending} disabled={!staff.data || !assigned.data} onClick={onSave}>Guardar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function ProductsPage() {
  const query = useAsync(catalogApi.productTypes, [])
  const [creating, setCreating] = useState(false)
  const [reviewing, setReviewing] = useState<ProductType | null>(null)
  const { can } = useAuth()
  const isAdmin = can(PERM.manageUsers) // solo el administrador gestiona quién revisa cada producto
  const assignments = useAsync<Record<string, number[]>>(
    () => (isAdmin ? usersApi.assignments() : Promise.resolve({})),
    [isAdmin],
  )
  const toggle = useSubmit(async (id: number, active: boolean) => {
    await catalogApi.setProductActive(id, active)
    return true
  })

  const columns: ColumnDef<ProductType>[] = [
    { accessorKey: 'name', header: 'Producto' },
    { accessorKey: 'code', header: 'Código' },
    { accessorKey: 'folder_name', header: 'Carpeta de soportes' },
    ...(isAdmin ? [{
      id: 'reviewers',
      header: 'Revisores',
      cell: ({ row }: { row: { original: ProductType } }) => {
        const n = Object.values(assignments.data ?? {}).filter((ids) => ids.includes(row.original.id)).length
        return n === 0 ? <Badge tone="warning" dot>Sin revisores</Badge> : <Badge tone="primary">{n}</Badge>
      },
    }] : []),
    {
      accessorKey: 'is_active',
      header: 'Disponible',
      cell: ({ row }) => (
        <Switch checked={row.original.is_active} disabled={toggle.pending} aria-label={`Activar ${row.original.name}`}
          onCheckedChange={async (active) => { if (await toggle.run(row.original.id, active)) query.reload() }} />
      ),
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex justify-end">
          <div className="flex gap-2">
            {isAdmin && <IconButton icon={Users} label="Asignar revisores" onClick={() => setReviewing(row.original)} />}
            <IconButton icon={FilePenLine} label="Formularios" to={`/productos/${row.original.id}`} />
          </div>
        </div>
      ),
    },
  ]

  return (
    <>
      <PageHeader title="Productos y formularios" description="Cada producto tiene su propio formulario, versionado."
        actions={<Button onClick={() => setCreating(true)}>Nuevo producto</Button>} />
      {toggle.error && <Alert tone="danger" className="mb-4"><AlertDescription>{toggle.error.message}</AlertDescription></Alert>}
      <QueryState query={query}>
        {(page) => <DataTable columns={columns} data={page.items} filterColumn="name" filterPlaceholder="Buscar producto" />}
      </QueryState>
      {reviewing && <ReviewersDialog product={reviewing} onClose={() => setReviewing(null)} onSaved={assignments.reload} />}
      {creating && <NewProductDialog onClose={() => setCreating(false)} onCreated={query.reload} />}
    </>
  )
}
