import { Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { Loading } from '@/components/ui'
import { AppShell, RequireAuth, RequirePermission } from '@/components/layout'
import { ErrorBoundary } from '@/components/layout/ErrorBoundary'
import { LoginPage } from '@/features/auth/LoginPage'
import { AuthProvider } from '@/hooks/useAuth'
import { ToastProvider } from '@/hooks/useToast'

import { routes } from './routes'

/**
 * Django mounts the application at `/app/` (see `api/spa.py`), so the router
 * works under that prefix. Keeping the SPA off `/` leaves every existing
 * server-rendered URL exactly where it was while both run side by side.
 */
export const BASENAME = '/app'

function render(route) {
  const Element = route.element
  return route.permission ? (
    <RequirePermission permission={route.permission}>
      <Element />
    </RequirePermission>
  ) : (
    <Element />
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter basename={BASENAME}>
        <ToastProvider>
          <AuthProvider>
            <Suspense fallback={<Loading />}>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route
                  path="/"
                  element={
                    <RequireAuth>
                      <AppShell />
                    </RequireAuth>
                  }
                >
                  {routes.map((route) =>
                    route.index ? (
                      <Route key="index" index element={render(route)} />
                    ) : (
                      <Route key={route.path} path={route.path} element={render(route)} />
                    ),
                  )}
                </Route>
              </Routes>
            </Suspense>
          </AuthProvider>
        </ToastProvider>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
