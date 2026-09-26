import { useState } from 'react'

import { api } from '@/api'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { EmptyState, ErrorState, Loading, SearchInput } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useDebounce, useDocumentTitle } from '@/hooks/useDebounce'
import { APP_BASENAME, serverUrl } from '@/lib/config'
import { formatMoney } from '@/lib/format'
import { priceText } from '@/features/portal/catalogText'

import '@/features/portal/portal.css'
import './directory.css'

/** An address inside the application: it lives under `/app`, and this page — served at
 * the bare domain, outside the router — reaches it with a full page load. */
const inApp = (path) => `${APP_BASENAME}${path}`

/**
 * The site's front door — the store (docs/16, R1).
 *
 * The bare domain opens **the services**, all of them, across every group that
 * chose to be listed: the customer comes for a service, so that is what they see
 * first — its price, how it is sold, and how many clinics offer it. Choosing one
 * goes to that group's service page, where the clinics that offer it are listed
 * nearest first and the customer adds it to «طلباتي» with a clinic, a quantity and
 * a preferred time. The groups themselves come second, below.
 *
 * Public, no sign-in. Nothing private is in the responses (api/directory.py).
 */
export function DirectoryPage() {
  useDocumentTitle('الخدمات والعيادات')
  const [text, setText] = useState('')
  const q = useDebounce(text.trim(), 300)
  const services = useAsync(() => api.directory.services({ q }), [q])
  const groups = useAsync(() => api.directory.list({ q }), [q])
  const rows = services.data?.results ?? []
  const cards = groups.data?.results ?? []

  return (
    <div className="portal directory">
      <header className="portal__header">
        <strong className="portal__clinic">الخدمات والعيادات</strong>
        <div className="directory__tools">
          <ThemeToggle />
        </div>
      </header>

      <div className="directory__intro">
        <h1 className="directory__title">اختر الخدمة، ثم العيادة الأقرب إليك</h1>
        <p className="directory__lead">
          تصفّح الخدمات وأسعارها، وأضف ما تحتاجه إلى طلباتك مع العيادة والكمية والموعد المفضل.
        </p>
        <SearchInput
          className="directory__search"
          value={text}
          onChange={setText}
          placeholder="ابحث عن خدمة أو تخصص أو عيادة أو محافظة…"
        />
      </div>

      <main className="portal__content portal__content--wide">
        <section aria-labelledby="store-services">
          <h2 id="store-services" className="portal__section-title">الخدمات</h2>
          {services.loading && !services.data ? (
            <Loading />
          ) : services.error ? (
            <ErrorState error={services.error} onRetry={services.reload} />
          ) : rows.length === 0 ? (
            <EmptyState
              title={q ? 'لا توجد خدمات مطابقة' : 'لا توجد خدمات معروضة بعد'}
              message={q ? 'جرّب كلمة أخرى، أو امسح البحث لترى الكل.' : undefined}
            />
          ) : (
            <ul className="portal-services">
              {rows.map((service) => (
                <li key={`${service.group}-${service.uuid}`} className="portal-card portal-service">
                  <a className="portal-catalog__title" href={inApp(`/portal/${service.group}/services/${service.uuid}`)}>
                    {service.name}
                  </a>
                  {service.description && <p className="portal-about__text">{service.description}</p>}
                  <div className="portal-catalog__meta">
                    <span>{service.group_name}</span>
                    {service.specialization && <span>{service.specialization}</span>}
                    <span>{service.branches_count > 1 ? `في ${service.branches_count} عيادات` : 'في عيادة واحدة'}</span>
                    {service.governorates.length > 0 && <span>{service.governorates.join('، ')}</span>}
                  </div>
                  <div className="portal-service__foot">
                    <strong>{priceText(service.price_display, service.from_price, service.requires_quantity ? service.quantity_unit || 'وحدة' : null)}</strong>
                    <a className="ui-btn ui-btn--primary ui-btn--sm" href={inApp(`/portal/${service.group}/services/${service.uuid}`)}>
                      اختر العيادة
                    </a>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {cards.length > 0 && (
          <section aria-labelledby="store-groups">
            <h2 id="store-groups" className="portal__section-title">المجمعات الطبية</h2>
            <ul className="directory__grid">
              {cards.map((group) => (
                <li key={group.slug}>
                  <GroupCard group={group} />
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </div>
  )
}

function GroupCard({ group }) {
  const more = group.services_count - group.services.length
  return (
    <article className="portal-card directory-card">
      <a className="directory-card__cover" href={inApp(`/portal/${group.slug}`)} tabIndex={-1} aria-hidden="true">
        {group.cover ? <img src={serverUrl(group.cover)} alt="" loading="lazy" /> : <span />}
      </a>
      <div className="directory-card__body">
        <div className="directory-card__head">
          {group.logo && <img className="directory-card__logo" src={serverUrl(group.logo)} alt="" loading="lazy" />}
          <h2 className="directory-card__name">
            <a href={inApp(`/portal/${group.slug}`)}>{group.name}</a>
          </h2>
        </div>

        <ul className="directory-card__clinics">
          {group.clinics.map((clinic) => (
            <li key={clinic.name}>
              <strong>{clinic.name}</strong>
              {clinic.address && <span className="ui-muted"> — {clinic.address}</span>}
            </li>
          ))}
        </ul>

        {group.specialties.length > 0 && (
          <ul className="portal-about__chips" aria-label="التخصصات">
            {group.specialties.map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        )}

        {group.services.length > 0 && (
          <ul className="directory-card__services" aria-label="الخدمات">
            {group.services.map((service) => (
              <li key={service.name}>
                <span>{service.name}</span>
                {service.from_price && (
                  <span className="directory-card__price">من {formatMoney(service.from_price)}</span>
                )}
              </li>
            ))}
            {more > 0 && <li className="ui-muted">و{more} خدمة أخرى</li>}
          </ul>
        )}

        <div className="directory-card__actions">
          <a className="ui-btn ui-btn--primary" href={inApp(`/portal/${group.slug}`)}>
            الصفحة الكاملة
          </a>
          {group.services_count > 0 && (
            <a className="ui-btn ui-btn--secondary" href={inApp(`/portal/${group.slug}/services`)}>
              الخدمات والحجز
            </a>
          )}
        </div>
      </div>
    </article>
  )
}
