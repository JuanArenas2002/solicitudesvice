import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Spinner, Toaster, TooltipProvider } from '@juanarenas31/metrik-ui'
import { AuthProvider } from './auth/AuthProvider'
import { RequireAuth } from './auth/guards'
import { AppShell } from './components/AppShell'
import { PERM } from './constants'

const LoginPage = lazy(() => import('./pages/LoginPage'))
const RequestsPage = lazy(() => import('./pages/RequestsPage'))
const RequestPage = lazy(() => import('./pages/RequestPage'))
const UsersPage = lazy(() => import('./pages/UsersPage'))
const ProductsPage = lazy(() => import('./pages/ProductsPage'))
const ProductFormsPage = lazy(() => import('./pages/ProductFormsPage'))
const FormEditorPage = lazy(() => import('./pages/FormEditorPage'))
const ChangePasswordPage = lazy(() => import('./pages/ChangePasswordPage'))

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <TooltipProvider delayDuration={150}>
        <Suspense fallback={<div className="grid min-h-screen place-items-center"><Spinner size="lg" label="Cargando" /></div>}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<RequireAuth />}>
              <Route element={<AppShell />}>
                <Route index element={<RequestsPage />} />
                <Route path="solicitudes/:id" element={<RequestPage />} />
                <Route path="cambiar-clave" element={<ChangePasswordPage />} />
                <Route element={<RequireAuth permission={PERM.manageForms} />}>
                  <Route path="productos" element={<ProductsPage />} />
                  <Route path="productos/:productId" element={<ProductFormsPage />} />
                  <Route path="productos/:productId/versiones/:versionId" element={<FormEditorPage />} />
                </Route>
                <Route element={<RequireAuth permission={PERM.manageUsers} />}>
                  <Route path="usuarios" element={<UsersPage />} />
                </Route>
              </Route>
            </Route>
          </Routes>
        </Suspense>
        <Toaster />
        </TooltipProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
