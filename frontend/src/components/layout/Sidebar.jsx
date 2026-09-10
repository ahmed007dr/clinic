import { NavLink } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'
import { useT } from '@/i18n'

/**
 * Navigation, filtered by what the signed-in user may actually open.
 *
 * The filtering is a courtesy, not a control: every one of these routes is
 * re-authorised by the server on each request. Hiding a link the user would
 * only be refused is better than offering it, but it is not what refuses them.
 */

const SECTIONS = [
  {
    title: null,
    items: [{ to: '/', label: 'nav.home', icon: '⌂', end: true }],
  },
  {
    title: 'nav.group',
    permission: 'is_owner',
    items: [{ to: '/owner', label: 'nav.owner', icon: '▦' }],
  },
  {
    title: 'nav.clinic',
    items: [
      { to: '/patients', label: 'nav.patients', icon: '👤' },
      { to: '/appointments', label: 'nav.appointments', icon: '📅' },
      { to: '/queue', label: 'nav.queue', icon: '⏳' },
      { to: '/patients/review', label: 'nav.review', icon: '📝', permission: 'front_desk' },
    ],
  },
  {
    title: 'nav.medical',
    permission: 'view_clinical',
    items: [
      { to: '/visits', label: 'nav.visits', icon: '🩺' },
      { to: '/prescriptions', label: 'nav.prescriptions', icon: '℞' },
      { to: '/treatment-plans', label: 'nav.treatment_plans', icon: '📋' },
      { to: '/procedures', label: 'nav.procedures', icon: '⚕' },
      { to: '/lab-results', label: 'nav.lab_results', icon: '🧪' },
      { to: '/attachments', label: 'nav.attachments', icon: '📎' },
    ],
  },
  {
    title: 'nav.accounts',
    items: [
      { to: '/payments', label: 'nav.payments', icon: '💵' },
      { to: '/expenses', label: 'nav.expenses', icon: '🧾', permission: 'manage_billing' },
      { to: '/reports/financial', label: 'nav.financial_report', icon: '📊' },
    ],
  },
  {
    title: 'nav.admin',
    permission: 'is_admin',
    items: [
      { to: '/staff', label: 'nav.users', icon: '👥' },
      { to: '/employees', label: 'nav.employees', icon: '🧑‍⚕️' },
      { to: '/attendance', label: 'nav.attendance', icon: '🕘' },
      { to: '/branches', label: 'nav.branches', icon: '🏥', permission: 'is_owner' },
      { to: '/services', label: 'nav.services', icon: '🗂' },
      { to: '/subscription', label: 'nav.subscription', icon: '🎫', permission: 'is_owner' },
      { to: '/settings', label: 'nav.settings', icon: '⚙' },
    ],
  },
]

export function Sidebar({ onNavigate }) {
  const { user, permissions } = useAuth()
  const { t } = useT()

  const allowed = (entry) => !entry.permission || permissions[entry.permission]

  return (
    <nav className="sidebar" aria-label={t('nav.main')}>
      <div className="sidebar__brand">
        <span className="sidebar__mark" aria-hidden="true">
          ⊕
        </span>
        <span className="sidebar__clinic" title={user?.clinic || ''}>
          {user?.clinic || t('nav.clinic')}
        </span>
      </div>

      <div className="sidebar__scroll">
        {SECTIONS.filter(allowed).map((section, index) => {
          const items = section.items.filter(allowed)
          if (items.length === 0) return null
          return (
            <div className="sidebar__section" key={section.title ?? index}>
              {section.title && <div className="sidebar__heading">{t(section.title)}</div>}
              {items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    `sidebar__link ${isActive ? 'sidebar__link--active' : ''}`
                  }
                >
                  <span className="sidebar__icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  <span>{t(item.label)}</span>
                </NavLink>
              ))}
            </div>
          )
        })}
      </div>

      {user?.branch && (
        <div className="sidebar__footer">
          <span className="ui-muted">{t('nav.branch')}</span>
          <strong>{user.branch.name}</strong>
        </div>
      )}
    </nav>
  )
}
