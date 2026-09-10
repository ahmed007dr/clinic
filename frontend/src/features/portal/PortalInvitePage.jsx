import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button, Input } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDebounce'

import { usePortal } from './PortalContext'

/**
 * Set a password from an invitation link.
 *
 * The token arrives in the URL fragment (`#…`), which the browser never sends
 * to the server — so it is read here and posted, and never lands in a log.
 */
export function PortalInvitePage() {
  const { api, setMe, slug } = usePortal()
  const navigate = useNavigate()
  const [token] = useState(() => window.location.hash.replace(/^#/, ''))
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useDocumentTitle('تفعيل حساب البوابة')

  const submit = async (event) => {
    event.preventDefault()
    if (password !== confirm) {
      setError('كلمتا المرور غير متطابقتين.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      setMe(await api.acceptInvite(token, password))
      // Drops the token from the address bar and from history.
      navigate(`/portal/${slug}`, { replace: true })
    } catch (caught) {
      setError(caught.fields?.password || caught.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="portal-auth">
      <main className="portal-auth__panel">
        <span className="portal-auth__mark" aria-hidden="true">⊕</span>
        <h1 className="portal-auth__title">تفعيل حسابك</h1>
        {!token ? (
          <p className="form-error">الرابط غير مكتمل. افتح الرابط كما وصلك من العيادة.</p>
        ) : (
          <>
            <p className="ui-muted">اختر كلمة مرور للدخول إلى ملفك في العيادة.</p>
            <form className="portal-auth__form" onSubmit={submit}>
              {error && <div className="form-error" role="alert">{error}</div>}
              <Input label="كلمة المرور" type="password" required minLength={8} autoFocus
                autoComplete="new-password" hint="٨ أحرف على الأقل."
                value={password} onChange={(e) => setPassword(e.target.value)} />
              <Input label="تأكيد كلمة المرور" type="password" required autoComplete="new-password"
                value={confirm} onChange={(e) => setConfirm(e.target.value)} />
              <Button type="submit" variant="primary" block loading={busy}>تفعيل الحساب</Button>
            </form>
          </>
        )}
      </main>
    </div>
  )
}
