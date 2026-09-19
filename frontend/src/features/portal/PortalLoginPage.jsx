import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { Button, Input } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDebounce'
import { useT } from '@/i18n'

import { safeNext } from './next'
import { usePortal } from './PortalContext'

export function PortalLoginPage() {
  const { api, me, setMe, slug } = usePortal()
  const { t } = useT()
  const navigate = useNavigate()
  const { search } = useLocation()
  const after = safeNext(search, slug) ?? `/portal/${slug}`
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  // 'password', or 'code' — a one-time code emailed to the patient.
  const [mode, setMode] = useState('password')
  const [code, setCode] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [notice, setNotice] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useDocumentTitle('بوابة المرضى')

  if (me) return <Navigate to={after} replace />

  const switchMode = (next) => {
    setMode(next)
    setCodeSent(false)
    setCode('')
    setError(null)
    setNotice(null)
  }

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      if (mode === 'code' && !codeSent) {
        const result = await api.requestCode(phone)
        setNotice(result.detail)
        setCodeSent(true)
        return
      }
      setMe(mode === 'code' ? await api.verifyCode(phone, code) : await api.login(phone, password))
      navigate(after, { replace: true })
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
        <p className="ui-muted">
          {mode === 'code'
            ? 'أدخل رقم هاتفك أو بريدك المسجّل في العيادة لنرسل لك رمز الدخول'
            : 'سجّل الدخول برقم هاتفك المسجّل في العيادة'}
        </p>
        <form className="portal-auth__form" onSubmit={submit}>
          {error && <div className="form-error" role="alert">{error}</div>}
          {notice && <div className="ui-muted" role="status">{notice}</div>}
          {mode === 'code' ? (
            <>
              <Input label="رقم الهاتف أو البريد الإلكتروني" dir="ltr" required autoFocus
                autoComplete="username" value={phone} disabled={codeSent}
                onChange={(e) => setPhone(e.target.value)} />
              {codeSent && (
                <Input label="الرمز المرسل إلى بريدك" dir="ltr" inputMode="numeric" required autoFocus
                  autoComplete="one-time-code" maxLength={6} value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />
              )}
              <Button type="submit" variant="primary" block loading={busy}>
                {codeSent ? 'دخول' : 'إرسال الرمز'}
              </Button>
              {codeSent && (
                <Button type="button" variant="ghost" block onClick={() => { setCodeSent(false); setCode('') }}>
                  طلب رمز جديد
                </Button>
              )}
            </>
          ) : (
            <>
              <Input label="رقم الهاتف" type="tel" inputMode="tel" dir="ltr" required autoFocus
                autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
              <Input label="كلمة المرور" type="password" required autoComplete="current-password"
                value={password} onChange={(e) => setPassword(e.target.value)} />
              <Button type="submit" variant="primary" block loading={busy}>دخول</Button>
            </>
          )}
        </form>
        <p className="portal-auth__note">
          <Button type="button" size="sm" variant="ghost" onClick={() => switchMode(mode === 'code' ? 'password' : 'code')}>
            {mode === 'code' ? 'الدخول بكلمة المرور' : 'الدخول برمز يصلك على البريد الإلكتروني'}
          </Button>
        </p>
        <p className="portal-auth__note">
          ليس لديك حساب أو نسيت كلمة المرور؟ اطلب رابط دعوة جديداً من استقبال العيادة.
        </p>
        <p className="portal-auth__note">
          <Link to={`/portal/${slug}/signup${search}`}>إنشاء حساب جديد</Link>
        </p>
        <p className="portal-auth__note">
          <Link to={`/portal/${slug}/register`}>{t('intake.portal_register_link')}</Link>
        </p>
        <p className="portal-auth__note">
          <Link to={`/portal/${slug}/about`}>عن العيادة: الفروع والتخصصات والعناوين</Link>
        </p>
      </main>
    </div>
  )
}
