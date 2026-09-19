import { useCallback, useMemo, useSyncExternalStore } from 'react'

/**
 * «طلباتي» before it is sent — the customer's basket (docs/16).
 *
 * It lives in the browser, per clinic group, so a visitor can put services in
 * without an account and sign in only when sending. Each line remembers what
 * the customer saw (names, unit price, limits) so the basket reads the same on
 * every page; the server re-checks all of it on sending and works the price out
 * itself. Reading `localStorage` is guarded: it can throw (a private window),
 * and then the basket simply lasts for this visit.
 */
const EVENT = 'clinic-portal-cart'
const keyOf = (slug) => `clinic-portal-cart:${slug}`
const memory = new Map()
const parsed = new Map() // raw string → array, so a snapshot keeps its identity between reads

function readRaw(slug) {
  try {
    const raw = localStorage.getItem(keyOf(slug))
    if (raw !== null) return raw
  } catch {
    /* fall through to memory */
  }
  return memory.get(slug) ?? '[]'
}

function write(slug, items) {
  const raw = JSON.stringify(items)
  memory.set(slug, raw)
  try {
    localStorage.setItem(keyOf(slug), raw)
  } catch {
    /* kept in memory for this visit */
  }
  window.dispatchEvent(new Event(EVENT))
}

function snapshot(slug) {
  const raw = readRaw(slug)
  if (!parsed.has(raw)) {
    let value = []
    try {
      const data = JSON.parse(raw)
      if (Array.isArray(data)) value = data
    } catch {
      /* an unreadable basket is an empty one */
    }
    parsed.set(raw, value)
  }
  return parsed.get(raw)
}

const same = (a, b) => a.service === b.service && a.branch === b.branch

/**
 * `{items, count, add, setQuantity, remove, clear}` for one clinic group.
 * A line is `{service, branch, quantity, service_name, branch_name, unit_price,
 * price_is_final, requires_quantity, doctor_sets_quantity, quantity_unit,
 * min_quantity, max_quantity}`.
 */
export function useCart(slug) {
  const subscribe = useCallback((notify) => {
    window.addEventListener(EVENT, notify)
    window.addEventListener('storage', notify)
    return () => {
      window.removeEventListener(EVENT, notify)
      window.removeEventListener('storage', notify)
    }
  }, [])
  const items = useSyncExternalStore(subscribe, () => snapshot(slug), () => [])

  return useMemo(
    () => ({
      items,
      count: items.length,
      /** Put a line in; the same service at the same clinic is replaced, not doubled. */
      add: (line) => write(slug, [...items.filter((item) => !same(item, line)), line]),
      setQuantity: (line, quantity) =>
        write(slug, items.map((item) => (same(item, line) ? { ...item, quantity } : item))),
      remove: (line) => write(slug, items.filter((item) => !same(item, line))),
      clear: () => write(slug, []),
    }),
    [items, slug],
  )
}

/** What a line comes to, or null when there is no figure (priced after evaluation). */
export function lineTotal(line) {
  if (line.unit_price === null || line.unit_price === undefined) return null
  const unit = Number(line.unit_price)
  if (!line.requires_quantity) return unit
  const quantity = Number(line.quantity) > 0 ? Number(line.quantity) : line.doctor_sets_quantity ? Number(line.min_quantity) : 0
  return unit * quantity
}
