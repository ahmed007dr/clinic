import { Link } from 'react-router-dom'

import { EmptyState, ErrorState, Loading } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'

import { priceText, unitOf } from './catalogText'
import { usePortal } from './PortalContext'

/**
 * The group's services — the front of the public page (docs/16).
 *
 * The customer comes for a service, not for a clinic: each card is a service
 * (what it is, how long, what it costs, how it is sold) and leads to the clinics
 * that offer it, nearest first. Only what can really be booked is listed — the
 * same server rule that the rest of the journey uses.
 */
export function PortalServiceGrid({ heading = 'خدماتنا' }) {
  const { api, slug } = usePortal()
  const { data, loading, error, reload } = useAsync(() => api.catalogServices(), [api])

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />
  if (!data.length) return <EmptyState title="لا توجد خدمات متاحة للطلب حالياً" />

  return (
    <section aria-labelledby="portal-services-heading">
      <h2 id="portal-services-heading" className="portal__section-title">{heading}</h2>
      <ul className="portal-services">
        {data.map((service) => (
          <li key={service.uuid} className="portal-card portal-service">
            <Link className="portal-catalog__title" to={`/portal/${slug}/services/${service.uuid}`}>
              {service.name}
            </Link>
            {service.description && <p className="portal-about__text">{service.description}</p>}
            <div className="portal-catalog__meta">
              {service.specialization && <span>{service.specialization}</span>}
              <span>{service.duration_minutes} دقيقة</span>
              <span>{service.branches_count > 1 ? `في ${service.branches_count} عيادات` : 'في عيادة واحدة'}</span>
            </div>
            <div className="portal-service__foot">
              <strong>{priceText(service.price_display, service.from_price, unitOf(service))}</strong>
              <Link className="ui-btn ui-btn--primary ui-btn--sm" to={`/portal/${slug}/services/${service.uuid}`}>
                اختر العيادة
              </Link>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
