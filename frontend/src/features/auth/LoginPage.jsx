import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { Button, Input, Loading } from '@/components/ui'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { useAuth } from '@/hooks/useAuth'
import { useDocumentTitle } from '@/hooks/useDebounce'

import './login.css'

export function LoginPage() {
  const { login, isAuthenticated, loading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  useDocumentTitle('تسجيل الدخول')

  if (loading) return <Loading message="جارٍ التحقق…" />

  // Someone who is already signed in and navigates here should land on the
  // application, not on a form asking them to sign in again.
  if (isAuthenticated) {
    return <Navigate to={location.state?.from?.pathname || '/'} replace />
  }

  const submit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await login(email, password)
      navigate(location.state?.from?.pathname || '/', { replace: true })
    } catch (caught) {
      setError(caught.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login">
      <div className="login__theme">
        <ThemeToggle />
      </div>

      <main className="login__panel">
        <div className="login__brand">
          <span className="login__mark" aria-hidden="true">
            ⊕
          </span>
          <h1 className="login__title">نظام إدارة العيادة</h1>
          <p className="login__subtitle">سجّل الدخول للمتابعة</p>
        </div>

        <form className="login__form" onSubmit={submit}>
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}

          <Input
            label="البريد الإلكتروني"
            type="email"
            dir="ltr"
            required
            autoFocus
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />

          <Input
            label="كلمة المرور"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          <Button type="submit" variant="primary" block loading={submitting}>
            تسجيل الدخول
          </Button>
        </form>

        <p className="login__note">
          إذا نسيت كلمة المرور، تواصل مع مدير العيادة لإعادة تعيينها.
        </p>
      </main>
    </div>
  )
}
