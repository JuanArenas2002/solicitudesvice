import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  Avatar, AvatarFallback, Button, Container, DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger, ScrollArea, Sheet, SheetContent, SheetDescription,
  SheetTitle, Switch, cn, useTheme,
} from '@juanarenas31/metrik-ui'
import { useAuth } from '../auth/AuthProvider'
import { PERM, ROLE_LABEL } from '../constants'
import { NotificationsBell } from './NotificationsBell'

const NAV = [
  { to: '/', label: 'Solicitudes', end: true },
  { to: '/productos', label: 'Productos y formularios', permission: PERM.manageForms },
  { to: '/usuarios', label: 'Usuarios', permission: PERM.manageUsers },
]

/** Contenido del menú lateral; se reutiliza fijo en escritorio y dentro de un Sheet en móvil. */
function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, can, logout } = useAuth()
  const { resolvedTheme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  if (!user) return null
  const initials = `${user.first_name[0]}${user.last_name[0]}`.toUpperCase()

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-16 shrink-0 items-center border-b border-border px-5">
        <img src="/logo.svg" alt="Solicitudes VICE" className="h-8" />
      </div>
      <ScrollArea className="flex-1">
        <nav className="space-y-1 p-3" aria-label="Principal">
          {NAV.filter((n) => !n.permission || can(n.permission)).map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} onClick={onNavigate}
              className={({ isActive }) => cn(
                'block rounded-md px-3 py-2 text-sm font-medium hover:bg-surface-muted',
                isActive ? 'bg-surface-muted text-primary' : 'text-fg-muted',
              )}>
              {n.label}
            </NavLink>
          ))}
        </nav>
      </ScrollArea>
      <div className="shrink-0 space-y-3 border-t border-border p-3">
        <div className="flex items-center justify-between px-3 text-sm text-fg-muted">
          <label className="flex flex-1 items-center justify-between pr-3">
            Modo oscuro
            <Switch checked={resolvedTheme === 'dark'} onCheckedChange={toggleTheme} aria-label="Modo oscuro" />
          </label>
          {can(PERM.createRequest) && <NotificationsBell />}
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-auto w-full justify-start gap-3 px-3 py-2" aria-label="Menú de usuario">
              <Avatar className="h-8 w-8"><AvatarFallback>{initials}</AvatarFallback></Avatar>
              <span className="min-w-0 text-left">
                <span className="block truncate text-sm font-medium">{user.first_name} {user.last_name}</span>
                <span className="block truncate text-xs font-normal text-fg-muted">{ROLE_LABEL[user.role]}</span>
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top">
            <DropdownMenuLabel>{user.email}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => { onNavigate?.(); navigate('/cambiar-clave') }}>Cambiar contraseña</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => logout().then(() => navigate('/login'))}>Cerrar sesión</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  )
}

export function AppShell() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  if (!user) return null

  return (
    <div className="min-h-screen bg-bg lg:flex">
      <aside className="fixed inset-y-0 left-0 z-sticky hidden w-64 border-r border-border bg-surface lg:block">
        <SidebarContent />
      </aside>

      <header className="sticky top-0 z-sticky flex h-14 items-center gap-3 border-b border-border bg-surface px-4 lg:hidden">
        <Button variant="outline" size="sm" onClick={() => setOpen(true)} aria-label="Abrir menú">Menú</Button>
        <img src="/logo.svg" alt="Solicitudes VICE" className="h-7" />
      </header>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-64 p-0">
          <SheetTitle className="sr-only">Menú</SheetTitle>
          <SheetDescription className="sr-only">Navegación principal</SheetDescription>
          <SidebarContent onNavigate={() => setOpen(false)} />
        </SheetContent>
      </Sheet>

      <main className="min-w-0 flex-1 lg:pl-64">
        <Container className="py-8"><Outlet /></Container>
      </main>
    </div>
  )
}
