import { Link, Outlet, useNavigate } from 'react-router-dom'

import { Button, Toasts } from '@/components/ui'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { useAuth } from '@/hooks/useAuth'

import './platform.css'

/**
 * The owner portal's frame.
 *
 * Deliberately not the clinic shell: an operator belongs to no clinic, and a
 * sidebar of patients and appointments would be a menu of screens that refuse
 * them. It also makes it unmistakable, at a glance, which of the two a person
 * is looking at.
 */
export function PlatformShell() {
  const { platformUser, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <div className="platform">
      <header className="platform__header">
        <Link to="/platform" className="platform__brand">
          <span aria-hidden="true">⊕</span> لوحة مالك المنصة
        </Link>
        <div className="platform__spacer" />
        <ThemeToggle />
        <span className="ui-muted platform__who" dir="ltr">
          {platformUser?.email}
        </span>
        <Button
          size="sm"
          variant="ghost"
          onClick={async () => {
            await logout()
            navigate('/login', { replace: true })
          }}
        >
          تسجيل الخروج
        </Button>
      </header>
      <main className="platform__content">
        <Outlet />
      </main>
      <Toasts />
    </div>
  )
}
