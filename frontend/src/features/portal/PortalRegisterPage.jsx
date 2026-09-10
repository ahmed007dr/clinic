import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'

import { EmptyState, Loading } from '@/components/ui'
import { LanguageToggle } from '@/components/layout/LanguageToggle'
import { IntakeWizard } from '@/features/intake/IntakeWizard'
import { useAsync } from '@/hooks/useApi'
import { useDocumentTitle } from '@/hooks/useDebounce'
import { useT } from '@/i18n'

import { usePortal } from './PortalContext'

/**
 * A new patient registering themselves — available only when the group has
 * turned it on. What they send waits for the clinic's review; the answer is
 * the same whether or not they were already on file.
 */
export function PortalRegisterPage() {
  const { t } = useT()
  const { api, me, slug } = usePortal()
  const [done, setDone] = useState(false)
  const { data, loading, error } = useAsync(() => api.registerOptions(), [api])
  useDocumentTitle(t('intake.portal_title'))

  if (me) return <Navigate to={`/portal/${slug}`} replace />

  return (
    <div className="portal">
      <header className="portal__header">
        <strong className="portal__clinic">{data?.clinic ?? t('intake.portal_title')}</strong>
        <LanguageToggle />
      </header>
      <main className="portal__content portal__content--wide">
        {loading && <Loading />}
        {error && <EmptyState title={t('intake.portal_closed')} />}
        {done && (
          <div className="intake-success">
            <span className="intake-success__mark" aria-hidden="true">✓</span>
            <h1>{t('intake.portal_success_title')}</h1>
            <p>{t('intake.portal_success_body')}</p>
          </div>
        )}
        {data && !done && (
          <>
            <h1 className="portal__hello">{t('intake.portal_title')}</h1>
            <IntakeWizard
              mode="portal"
              options={{
                choices: data.choices,
                branches: data.branches,
                specializations: data.specializations,
                doctors: data.doctors,
                canChooseBranch: true,
              }}
              onSubmit={api.register}
              onSuccess={() => setDone(true)}
            />
          </>
        )}
        <p className="portal-auth__note">
          <Link to={`/portal/${slug}/login`}>{t('intake.portal_have_account')}</Link>
        </p>
      </main>
    </div>
  )
}
