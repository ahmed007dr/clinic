/**
 * Tabs, with the arrow-key behaviour the ARIA pattern expects.
 *
 * `items` is `[{ id, label, badge? }]`. The badge carries a count — how many
 * unacknowledged results, how many sessions left — which is often the reason
 * someone opens the tab at all.
 */
export function Tabs({ items, active, onChange }) {
  const move = (offset) => {
    const index = items.findIndex((item) => item.id === active)
    // Wraps, so the keyboard never dead-ends at either edge.
    const next = (index + offset + items.length) % items.length
    onChange(items[next].id)
  }

  return (
    <div
      className="ui-tabs"
      role="tablist"
      onKeyDown={(event) => {
        // Reversed in RTL: the arrow that points right moves to the *previous*
        // tab, because that is where it sits on screen.
        if (event.key === 'ArrowLeft') move(1)
        else if (event.key === 'ArrowRight') move(-1)
        else return
        event.preventDefault()
      }}
    >
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          className="ui-tab"
          aria-selected={item.id === active}
          tabIndex={item.id === active ? 0 : -1}
          onClick={() => onChange(item.id)}
        >
          {item.label}
          {item.badge !== undefined && item.badge !== null && item.badge !== 0 && (
            <span className="ui-badge ui-badge--neutral" style={{ marginInlineStart: 6 }}>
              {item.badge}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}
