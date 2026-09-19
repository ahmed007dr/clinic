import { useState } from 'react'

import { api } from '@/api'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { EmptyState, ErrorState, Loading, SearchInput } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useDebounce, useDocumentTitle } from '@/hooks/useDebounce'
import { APP_BASENAME, serverUrl } from '@/lib/config'
import { formatMoney } from '@/lib/format'

import '@/features/portal/portal.css'
import './directory.css'

/** An address inside the application: it lives under `/app`, and this page — served at
 * the bare domain, outside the router — reaches it with a full page load. */
const inApp = (path) => `${APP_BASENAME}${path}`

/**
 * The site's front door: every clinic group that chose to be listed.
 *
 * The site's main address — the bare domain, no path. Public, no sign-in. Each card is what the group already publishes — logo,
 * cover, its clinics and where they are, the specialties and the services that
 * can be booked with the lowest price — and leads to the group's own public
 * page (`/app/portal/<slug>`), where the visitor browses, signs up and books.
 * Nothing private is in the response (api/directory.py).
 */
export function DirectoryPage() {
  useDocumentTitle('العيادات')
  const [text, setText] = useState('')
  const q = useDebounce(text.trim(), 300)
  const { data, loading, error, reload } = useAsync(() => api.directory.list({ q }), [q])
  const groups = data?.results ?? []

  return (
    <div className="portal directory">
      <header className="portal__header">
        <strong className="portal__clinic">العيادات</strong>
        <div className="directory__tools">
          <a className="directory__staff" href={inApp('/login')}>دخول الموظفين</a>
          <ThemeToggle />
        </div>
      </header>

      <div className="directory__intro">
        <h1 className="directory__title">ابحث عن عيادتك واحجز موعدك</h1>
        <p className="directory__lead">
          اختر المجمع الطبي، تعرّف على عياداته وخدماته وأسعارها، ثم اطلب موعدك بنفسك.
        </p>
        <SearchInput
          className="directory__search"
          value={text}
          onChange={setText}
          placeholder="ابحث باسم العيادة أو التخصص أو الخدمة أو المدينة…"
        />
      </div>

      <main className="portal__content portal__content--wide">
        {loading && !data ? (
          <Loading />
        ) : error ? (
          <ErrorState error={error} onRetry={reload} />
        ) : groups.length === 0 ? (
          <EmptyState
            title={q ? 'لا توجد نتائج مطابقة' : 'لا توجد عيادات معروضة بعد'}
            message={q ? 'جرّب كلمة أخرى، أو امسح البحث لترى الكل.' : undefined}
          />
        ) : (
          <>
            <p className="directory__count" aria-live="polite">
              {groups.length} {groups.length === 1 ? 'مجمع' : 'مجمعات'}
            </p>
            <ul className="directory__grid">
              {groups.map((group) => (
                <li key={group.slug}>
                  <GroupCard group={group} />
                </li>
              ))}
            </ul>
          </>
        )}
      </main>

      <footer className="directory__foot">
        <a href={inApp('/signup')}>افتح عيادتك على المنصة</a>
      </footer>
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
