import './description.css'

/**
 * Label/value pairs, for every detail screen.
 *
 * `items` is `[{ label, value, span?, hide? }]`. Entries with no value are
 * dropped rather than shown as "—", so a patient record with three fields
 * filled in looks like three facts and not like twelve mostly-empty ones.
 * Pass `keepEmpty` where a blank genuinely means something.
 */
export function DescriptionList({ items, columns = 2, keepEmpty = false }) {
  const visible = items.filter((item) => {
    if (item.hide) return false
    if (keepEmpty) return true
    return item.value !== null && item.value !== undefined && item.value !== ''
  })

  if (visible.length === 0) return null

  return (
    <dl className="dl" style={{ '--dl-columns': columns }}>
      {visible.map((item) => (
        <div
          className="dl__item"
          key={item.label}
          style={item.span ? { gridColumn: `span ${item.span}` } : undefined}
        >
          <dt className="dl__label">{item.label}</dt>
          <dd className="dl__value">{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}
