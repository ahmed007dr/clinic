import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'

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
/** The developer portal's sections; each phase adds its own. */
export const PLATFORM_NAV = [
  { to: '/platform', label: 'نظرة عامة', end: true },
  { to: '/platform/tenants', label: 'المجموعات' },
  { to: '/platform/online', label: 'أونلاين الآن' },
  { to: '/platform/signups', label: 'طلبات جديدة' },
  { to: '/platform/billing', label: 'الاشتراكات والأرصدة' },
  { to: '/platform/plans', label: 'الباقات' },
  { to: '/platform/integrations', label: 'المفاتيح والتكاملات' },
  { to: '/platform/mailboxes', label: 'الإيميلات' },
]

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
        <span className="ui-muted platform__who">
          <span dir="ltr">{platformUser?.email}</span> · {platformUser?.role_label}
        </span>
        <Button
          size="sm"
          variant="ghost"
          onClick={async () => {
            await logout()
            navigate('/platform/login', { replace: true })
          }}
        >
          تسجيل الخروج
        </Button>
      </header>
      <nav className="platform__nav" aria-label="أقسام بوابة المنصة">
        {PLATFORM_NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `platform__tab ${isActive ? 'platform__tab--active' : ''}`}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main className="platform__content">
        <Outlet />
      </main>
      <Toasts />
    </div>
  )
}
