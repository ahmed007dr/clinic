export function Card({ className = '', children, ...rest }) {
  return (
    <section className={`ui-card ${className}`} {...rest}>
      {children}
    </section>
  )
}

export function CardHeader({ title, subtitle, actions, children }) {
  if (children) return <div className="ui-card__header">{children}</div>
  return (
    <div className="ui-card__header">
      <div>
        <h2 className="ui-card__title">{title}</h2>
        {subtitle && <div className="ui-card__subtitle">{subtitle}</div>}
      </div>
      {actions && <div className="ui-row">{actions}</div>}
    </div>
  )
}

/** `flush` for a table, which supplies its own padding. */
export function CardBody({ flush = false, className = '', children }) {
  return (
    <div className={`ui-card__body ${flush ? 'ui-card__body--flush' : ''} ${className}`}>
      {children}
    </div>
  )
}
