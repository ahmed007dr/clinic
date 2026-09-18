import { Link } from 'react-router-dom'

import { LanguageToggle } from '@/components/layout/LanguageToggle'
import { useDocumentTitle } from '@/hooks/useDebounce'

import { PortalAbout } from './PortalAbout'
import { usePortal } from './PortalContext'

/**
 * "About the clinic" for someone who has not signed in — a new client or
 * visitor deciding where to go. Public: it shows only what each branch chose to
 * publish (api/portal about).
 */
export function PortalAboutPage() {
  const { slug, me } = usePortal()
  useDocumentTitle('عن العيادة')

  return (
    <div className="portal">
      <header className="portal__header">
        <strong className="portal__clinic">عن العيادة</strong>
        <LanguageToggle />
      </header>
      <main className="portal__content portal__content--wide">
        <PortalAbout />
        <p className="portal-auth__note">
          <Link to={`/portal/${slug}`}>{me ? 'العودة إلى حسابي' : 'الدخول إلى بوابة المرضى'}</Link>
        </p>
      </main>
    </div>
  )
}
