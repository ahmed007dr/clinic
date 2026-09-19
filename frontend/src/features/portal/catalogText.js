import { formatMoney } from '@/lib/format'

/** What to say about a price: final, a floor, or not known before evaluation. */
export function priceText(display, price, perUnit) {
  if (display === 'after_evaluation') return 'السعر بعد تقييم الطبيب'
  if (price === null || price === undefined) return '—'
  const money = display === 'starting_from' ? `يبدأ من ${formatMoney(price)}` : formatMoney(price)
  // A service sold by quantity is priced per unit ("لكل نبضة").
  return perUnit ? `${money} لكل ${perUnit}` : money
}

/** The unit a service is sold by, or null when it is sold as one thing. */
export const unitOf = (service) => (service?.requires_quantity ? service.quantity_unit || 'وحدة' : null)
