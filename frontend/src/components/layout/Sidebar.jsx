import { NavLink } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'

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
    items: [{ to: '/', label: 'الرئيسية', icon: '⌂', end: true }],
  },
  {
    title: 'العيادة',
    items: [
      { to: '/patients', label: 'المرضى', icon: '👤' },
      { to: '/appointments', label: 'المواعيد', icon: '📅' },
      { to: '/queue', label: 'قائمة الانتظار', icon: '⏳' },
    ],
  },
  {
    title: 'السجلات الطبية',
    permission: 'view_clinical',
    items: [
      { to: '/visits', label: 'الزيارات', icon: '🩺' },
      { to: '/prescriptions', label: 'الروشتات', icon: '℞' },
      { to: '/treatment-plans', label: 'خطط العلاج', icon: '📋' },
      { to: '/procedures', label: 'الإجراءات', icon: '⚕' },
      { to: '/lab-results', label: 'التحاليل', icon: '🧪' },
      { to: '/attachments', label: 'المستندات', icon: '📎' },
    ],
  },
  {
    title: 'الحسابات',
    items: [
      { to: '/payments', label: 'الدفعات', icon: '💵' },
      { to: '/expenses', label: 'المصروفات', icon: '🧾', permission: 'manage_billing' },
      { to: '/reports/financial', label: 'التقرير المالي', icon: '📊' },
    ],
  },
  {
    title: 'الإدارة',
    permission: 'is_admin',
    items: [
      { to: '/staff', label: 'المستخدمون', icon: '👥' },
      { to: '/employees', label: 'الموظفون', icon: '🧑‍⚕️' },
      { to: '/branches', label: 'الفروع', icon: '🏥' },
      { to: '/services', label: 'الخدمات', icon: '🗂' },
      { to: '/subscription', label: 'الباقة والاشتراك', icon: '🎫' },
      { to: '/settings', label: 'الإعدادات', icon: '⚙' },
    ],
  },
]

export function Sidebar({ onNavigate }) {
  const { user, permissions } = useAuth()

  const allowed = (entry) => !entry.permission || permissions[entry.permission]

  return (
    <nav className="sidebar" aria-label="التنقل الرئيسي">
      <div className="sidebar__brand">
        <span className="sidebar__mark" aria-hidden="true">
          ⊕
        </span>
        <span className="sidebar__clinic" title={user?.clinic || ''}>
          {user?.clinic || 'العيادة'}
        </span>
      </div>

      <div className="sidebar__scroll">
        {SECTIONS.filter(allowed).map((section, index) => {
          const items = section.items.filter(allowed)
          if (items.length === 0) return null
          return (
            <div className="sidebar__section" key={section.title ?? index}>
              {section.title && (
                <div className="sidebar__heading">{section.title}</div>
              )}
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
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          )
        })}
      </div>

      {user?.branch && (
        <div className="sidebar__footer">
          <span className="ui-muted">الفرع</span>
          <strong>{user.branch.name}</strong>
        </div>
      )}
    </nav>
  )
}
