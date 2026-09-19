import { Link } from 'react-router-dom'

import { useCart } from './cart'
import { usePortal } from './PortalContext'

/** «طلباتي» in a portal header, with how many services are waiting in the basket. */
export function CartLink() {
  const { slug } = usePortal()
  const { count } = useCart(slug)
  return (
    <Link className="portal-cart-link" to={`/portal/${slug}/cart`} aria-label={`طلباتي — ${count} في السلة`}>
      طلباتي{count > 0 && <span className="portal-cart-link__count" aria-hidden="true">{count}</span>}
    </Link>
  )
}
