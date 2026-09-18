import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell } from 'lucide-react'
import { Badge, Button, EmptyState, Popover, PopoverContent, PopoverTrigger, Skeleton, toast } from '@juanarenas31/metrik-ui'
import { notificationsApi } from '../api'
import type { AppNotification } from '../api/types'
import { formatDateTime } from '../constants'
import { StatusBadge } from './StatusBadge'

const POLL_MS = 30_000

/** Campana de avisos del mentor: cuenta las no leídas (consulta cada 30 s) y lista los últimos cambios de estado. */
export function NotificationsBell() {
  const navigate = useNavigate()
  const [unread, setUnread] = useState(0)
  const [items, setItems] = useState<AppNotification[] | null>(null)
  const [open, setOpen] = useState(false)
  const last = useRef<number | null>(null)

  const refreshCount = useCallback(async () => {
    try {
      const { unread: n } = await notificationsApi.unreadCount()
      // Un aviso nuevo llega como toast; el primer conteo al abrir la app no.
      if (last.current !== null && n > last.current) toast.info('Tu solicitud cambió de estado')
      last.current = n
      setUnread(n)
    } catch { /* sin red: se reintenta en el siguiente ciclo */ }
  }, [])

  useEffect(() => {
    void refreshCount()
    const id = setInterval(() => { if (!document.hidden) void refreshCount() }, POLL_MS)
    return () => clearInterval(id)
  }, [refreshCount])

  const load = useCallback(async () => {
    try { setItems((await notificationsApi.list()).items) } catch { setItems([]) }
  }, [])

  const onOpenChange = (next: boolean) => {
    setOpen(next)
    if (next) { setItems(null); void load() }
  }

  const openRequest = async (n: AppNotification) => {
    setOpen(false)
    if (!n.read_at) { await notificationsApi.markRead([n.id]).catch(() => {}); void refreshCount() }
    navigate(`/solicitudes/${n.request_id}`)
  }

  const markAll = async () => {
    await notificationsApi.markRead().catch(() => {})
    void load()
    void refreshCount()
  }

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="relative" aria-label={unread ? `Notificaciones: ${unread} sin leer` : 'Notificaciones'}>
          <Bell className="size-5" aria-hidden />
          {unread > 0 && (
            <Badge tone="danger" className="absolute -right-1 -top-1 h-4 min-w-4 justify-center px-1 text-[10px]">
              {unread > 9 ? '9+' : unread}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" side="right" className="w-80 p-0">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <span className="text-sm font-semibold">Notificaciones</span>
          <Button size="sm" variant="ghost" disabled={unread === 0} onClick={markAll}>Marcar leídas</Button>
        </div>
        <div className="max-h-96 overflow-y-auto">
          {items === null ? (
            <div className="space-y-2 p-4"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
          ) : items.length === 0 ? (
            <EmptyState title="Sin novedades" description="Aquí verás cuando revisen tus solicitudes." />
          ) : (
            <ul>
              {items.map((n) => (
                <li key={n.id}>
                  <button type="button" onClick={() => openRequest(n)}
                    className="flex w-full items-start gap-3 border-b border-border px-4 py-3 text-left last:border-b-0 hover:bg-surface-muted">
                    <StatusBadge status={n.status} />
                    <span className="min-w-0 flex-1">
                      <span className={n.read_at ? 'block text-sm' : 'block text-sm font-semibold'}>{n.request_number}</span>
                      {n.reason && <span className="block truncate text-xs text-fg-muted">{n.reason}</span>}
                      <span className="block text-xs text-fg-muted">{formatDateTime(n.created_at)}</span>
                    </span>
                    {!n.read_at && <span className="mt-1.5 size-2 shrink-0 rounded-full bg-primary" aria-label="Sin leer" />}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
