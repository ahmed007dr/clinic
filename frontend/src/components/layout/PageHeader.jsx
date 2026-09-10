import { Link } from 'react-router-dom'

import { useDocumentTitle } from '@/hooks/useDebounce'

/**
 * The title block at the top of every screen.
 *
 * Also sets the browser tab title, because a clinic runs six tabs at once and
 * "نظام إدارة العيادة" six times over is no help in finding the right one.
 */
export function PageHeader({ title, subtitle, actions, back, children }) {
  useDocumentTitle(typeof title === 'string' ? title : undefined)

  return (
    <div className="page-header">
      <div className="page-header__text">
        {back && (
          <Link to={back.to} className="page-header__back">
            <span aria-hidden="true">›</span> {back.label}
          </Link>
        )}
        <h1 className="page-header__title">{title}</h1>
        {subtitle && <p className="page-header__subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
      {children}
    </div>
  )
}
