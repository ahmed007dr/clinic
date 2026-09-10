import { Navigate, useLocation } from 'react-router-dom'

import { EmptyState, Loading } from '@/components/ui'
import { useAuth } from '@/hooks/useAuth'

/**
 * Route guards.
 *
 * These decide what is **rendered**, never what is **permitted**. Every route
 * behind them fetches from an API that authorises the same request again, so
 * removing these guards would produce empty screens and 403s — not access.
 * They exist so a user is sent to the login page instead of watching a
 * dashboard fill up with errors, and told plainly when a section is not
 * theirs.
 */

export function RequireAuth({ children }) {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()

  // The session check is one request; rendering the login form before it
  // returns would bounce an already-signed-in user out of a link they opened.
  if (loading) return <Loading message="جارٍ التحقق من الجلسة…" />

  if (!isAuthenticated) {
    // `state.from` so signing in returns to the page that was asked for,
    // rather than dumping everyone on the dashboard.
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return children
}

export function RequirePermission({ permission, children }) {
  const { permissions } = useAuth()

  if (!permissions[permission]) {
    return (
      <EmptyState
        icon="🔒"
        title="لا تملك صلاحية الوصول"
        message="هذا القسم مقصور على صلاحيات أخرى. تواصل مع مدير العيادة إذا كنت تحتاج إليه."
      />
    )
  }

  return children
}
