import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '@/api'
import { Button, Input, Select, Textarea } from '@/components/ui'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { useAsync } from '@/hooks/useApi'
import { useDocumentTitle } from '@/hooks/useDebounce'
import { formatMoney } from '@/lib/format'

import '@/features/auth/login.css'
import './signup.css'

const EMPTY = {
  group_name: '', clinic_name: '', owner_name: '', email: '', phone: '', city: '', specialty: '',
  branches: 1, doctors: 1, plan: '', cycle: 'monthly', message: '', website: '',
}

/**
 * Asking to open a clinic group on the platform. Public; nothing is created
 * until the platform approves the request, after which the owner receives
 * their sign-in by email.
 */
export function SignupPage() {
  useDocumentTitle('طلب فتح عيادة')
  const options = useAsync(() => api.signup.options(), [])
  const [form, setForm] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [sending, setSending] = useState(false)
  const [done, setDone] = useState(false)
  const set = (name) => (event) => setForm({ ...form, [name]: event.target.value })
  const plans = options.data?.plans ?? []

  const submit = async (event) => {
    event.preventDefault()
    setSending(true)
    setErrors({})
    try {
      await api.signup.submit(form)
      setDone(true)
    } catch (caught) {
      const fields = {}
      Object.entries(caught.fields || {}).forEach(([name, messages]) => {
        fields[name] = Array.isArray(messages) ? messages.join(' ') : String(messages)
      })
      setErrors(Object.keys(fields).length ? fields : { detail: caught.message })
    } finally {
      setSending(false)
    }
  }

  if (done) {
    return (
      <div className="login">
        <main className="login__panel">
          <div className="login__brand">
            <span className="login__mark" aria-hidden="true">✓</span>
            <h1 className="login__title">استلمنا طلبك</h1>
            <p className="login__subtitle">
              سنراجع الطلب ونتواصل معك على {form.email}. عند الموافقة تصلك بيانات الدخول بالبريد.
            </p>
          </div>
          <Link to="/login" className="signup__back">الذهاب لتسجيل الدخول</Link>
        </main>
      </div>
    )
  }

  return (
    <div className="login signup">
      <div className="login__theme">
        <ThemeToggle />
      </div>
      <main className="login__panel signup__panel">
        <div className="login__brand">
          <span className="login__mark" aria-hidden="true">⊕</span>
          <h1 className="login__title">طلب فتح عيادة</h1>
          <p className="login__subtitle">املأ البيانات وسنراجع طلبك ونفتح لك الحساب</p>
        </div>

        <form className="signup__form" onSubmit={submit} noValidate>
          {errors.detail && <div className="form-error" role="alert">{errors.detail}</div>}
          <div className="signup__grid">
            <Input id="signup-group" label="اسم المجموعة / العيادة" required value={form.group_name}
              error={errors.group_name} onChange={set('group_name')} />
            <Input id="signup-clinic" label="اسم أول فرع" value={form.clinic_name} onChange={set('clinic_name')} />
            <Input id="signup-owner" label="اسم المالك" required value={form.owner_name}
              error={errors.owner_name} onChange={set('owner_name')} />
            <Input id="signup-email" label="البريد الإلكتروني" type="email" dir="ltr" required value={form.email}
              error={errors.email} onChange={set('email')} />
            <Input id="signup-phone" label="رقم الهاتف" dir="ltr" inputMode="tel" required value={form.phone}
              error={errors.phone} onChange={set('phone')} />
            <Input id="signup-city" label="المدينة" value={form.city} onChange={set('city')} />
            <Input id="signup-specialty" label="التخصص" value={form.specialty} onChange={set('specialty')} />
            <Input id="signup-branches" label="عدد الفروع" type="number" min="1" value={form.branches}
              error={errors.branches} onChange={set('branches')} />
            <Input id="signup-doctors" label="عدد الأطباء" type="number" min="1" value={form.doctors}
              error={errors.doctors} onChange={set('doctors')} />
            <Select id="signup-cycle" label="الدفع" value={form.cycle} onChange={set('cycle')}
              options={[{ value: 'monthly', label: 'شهري' }, { value: 'yearly', label: 'سنوي' }]} />
          </div>

          {plans.length > 0 && (
            <fieldset className="signup__plans">
              <legend>الباقة (اختياري)</legend>
              {errors.plan && <div className="form-error" role="alert">{errors.plan}</div>}
              {plans.map((plan) => (
                <label key={plan.code} className={`signup__plan ${form.plan === plan.code ? 'signup__plan--on' : ''}`}>
                  <input type="radio" name="plan" value={plan.code} checked={form.plan === plan.code}
                    onChange={set('plan')} />
                  <span className="signup__plan-name">{plan.name}</span>
                  <span className="signup__plan-price">
                    {formatMoney(plan.price)} / {plan.billing_period_label}
                  </span>
                  {plan.features.length > 0 && (
                    <span className="signup__plan-features">{plan.features.join(' · ')}</span>
                  )}
                </label>
              ))}
            </fieldset>
          )}

          <Textarea id="signup-message" label="ملاحظات" rows={3} value={form.message} onChange={set('message')} />
          {/* Hidden from people; bots fill it and are dropped. */}
          <input type="text" name="website" tabIndex={-1} autoComplete="off" className="signup__trap"
            value={form.website} onChange={set('website')} aria-hidden="true" />

          <Button type="submit" variant="primary" block loading={sending}>إرسال الطلب</Button>
        </form>
        <p className="login__note">
          لديك حساب؟ <Link to="/login">سجّل الدخول</Link>
        </p>
      </main>
    </div>
  )
}
