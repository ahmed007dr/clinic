import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { Button, Input } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDebounce'
import { useT } from '@/i18n'

import { usePortal } from './PortalContext'

export function PortalLoginPage() {
  const { api, me, setMe, slug } = usePortal()
  const { t } = useT()
  const navigate = useNavigate()
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useDocumentTitle('بوابة المرضى')

  if (me) return <Navigate to={`/portal/${slug}`} replace />

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      setMe(await api.login(phone, password))
      navigate(`/portal/${slug}`, { replace: true })
    } catch (caught) {
      setError(caught.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="portal-auth">
      <main className="portal-auth__panel">
        <span className="portal-auth__mark" aria-hidden="true">⊕</span>
        <h1 className="portal-auth__title">بوابة المرضى</h1>
        <p className="ui-muted">سجّل الدخول برقم هاتفك المسجّل في العيادة</p>
        <form className="portal-auth__form" onSubmit={submit}>
          {error && <div className="form-error" role="alert">{error}</div>}
          <Input label="رقم الهاتف" type="tel" inputMode="tel" dir="ltr" required autoFocus
            autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
          <Input label="كلمة المرور" type="password" required autoComplete="current-password"
            value={password} onChange={(e) => setPassword(e.target.value)} />
          <Button type="submit" variant="primary" block loading={busy}>دخول</Button>
        </form>
        <p className="portal-auth__note">
          ليس لديك حساب أو نسيت كلمة المرور؟ اطلب رابط دعوة جديداً من استقبال العيادة.
        </p>
        <p className="portal-auth__note">
          <Link to={`/portal/${slug}/register`}>{t('intake.portal_register_link')}</Link>
        </p>
      </main>
    </div>
  )
}
