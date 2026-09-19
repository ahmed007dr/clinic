import { Link } from 'react-router-dom'

import { LanguageToggle } from '@/components/layout/LanguageToggle'
import { ErrorState, Loading } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useDocumentTitle } from '@/hooks/useDebounce'
import { serverUrl } from '@/lib/config'

import { PortalAbout } from './PortalAbout'
import { usePortal } from './PortalContext'

/**
 * The group's public front page — what a visitor sees before signing in.
 *
 * The group's approved logo and cover, then one section per running clinic
 * (address, hours, contact, specialties and the doctors who agreed to be
 * shown), then the ways in. Everything comes from one public call that returns
 * only what management chose to publish. Booking joins this page once the
 * catalogue and availability exist (docs/15, Phases 3–5).
 */
export function PortalLandingPage() {
  const { api, slug } = usePortal()
  const { data, loading, error, reload } = useAsync(() => api.about(), [api])
  useDocumentTitle(data?.clinic)

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  return (
    <div className="portal">
      <header className="portal__header">
        <strong className="portal__clinic">{data.clinic}</strong>
        <LanguageToggle />
      </header>

      <div className="portal-hero">
        {data.cover && <img className="portal-hero__cover" src={serverUrl(data.cover)} alt="" />}
        <div className="portal-hero__body">
          {data.logo && <img className="portal-hero__logo" src={serverUrl(data.logo)} alt="" />}
          <h1 className="portal-hero__title">{data.clinic}</h1>
          <div className="portal-hero__actions">
            <Link className="ui-btn ui-btn--primary" to={`/portal/${slug}/login`}>
              تسجيل الدخول
            </Link>
            <Link className="ui-btn ui-btn--secondary" to={`/portal/${slug}/services`}>
              الخدمات والأسعار
            </Link>
            <Link className="ui-btn ui-btn--secondary" to={`/portal/${slug}/signup`}>
              إنشاء حساب
            </Link>
          </div>
        </div>
      </div>

      <main className="portal__content portal__content--wide">
        <PortalAbout data={data} />
      </main>
    </div>
  )
}
