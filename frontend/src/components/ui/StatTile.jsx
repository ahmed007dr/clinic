import { Link } from 'react-router-dom'

import './stat.css'

/**
 * One headline figure.
 *
 * Used only where the number genuinely is the point — the day's bookings, the
 * month's revenue. A row of these across the top of every screen is the
 * classic dashboard mistake: it makes six unimportant numbers look as
 * important as the one that matters.
 *
 * `tone` is for a figure that carries a state, such as results waiting to be
 * read. Ordinary counts stay neutral.
 */
export function StatTile({ label, value, hint, tone = 'neutral', to, icon }) {
  const body = (
    <>
      <div className="stat__label">
        {icon && (
          <span className="stat__icon" aria-hidden="true">
            {icon}
          </span>
        )}
        {label}
      </div>
      <div className="stat__value ui-num">{value}</div>
      {hint && <div className="stat__hint">{hint}</div>}
    </>
  )

  const className = `stat stat--${tone}`

  // A tile that leads somewhere is a link, not a div with a click handler —
  // so it can be opened in a new tab and reached from the keyboard.
  return to ? (
    <Link className={`${className} stat--link`} to={to}>
      {body}
    </Link>
  ) : (
    <div className={className}>{body}</div>
  )
}
