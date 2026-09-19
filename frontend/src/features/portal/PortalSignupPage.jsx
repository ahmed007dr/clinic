import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { Button, Checkbox, Input, Loading, Select } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useDocumentTitle } from '@/hooks/useDebounce'

import { safeNext } from './next'
import { usePortal } from './PortalContext'

const GENDERS = [
  { value: 'female', label: 'أنثى' },
  { value: 'male', label: 'ذكر' },
]

/**
 * Creating a portal account (docs/15, Phase 2): the form, then a code.
 *
 * The code goes to the e-mail address on the patient's file when this person
 * is already a patient of the clinic, and otherwise to the address typed here —
 * the wording never says which, so it reveals nothing about who is registered.
 * Only the right code creates the account and signs the person in. Available
 * only when the group has turned online registration on.
 */
export function PortalSignupPage() {
  const { api, me, setMe, slug } = usePortal()
  const navigate = useNavigate()
  const { search } = useLocation()
  const after = safeNext(search, slug) ?? `/portal/${slug}`
  const options = useAsync(() => api.registerOptions(), [api])
  const [values, setValues] = useState({
    name: '', phone: '', email: '', gender: 'female', birth_date: '', branch: '', password: '',
    consent: false,
  })
  const [step, setStep] = useState('form') // 'form' | 'code'
  const [ticket, setTicket] = useState('')
  const [code, setCode] = useState('')
  const [notice, setNotice] = useState(null)
  const [error, setError] = useState(null)
  const [fields, setFields] = useState({})
  const [busy, setBusy] = useState(false)
  useDocumentTitle('إنشاء حساب')

  if (me) return <Navigate to={after} replace />

  const set = (name) => (event) =>
    setValues((previous) => ({
      ...previous,
      [name]: event.target.type === 'checkbox' ? event.target.checked : event.target.value,
    }))

  const branches = options.data?.branches ?? []
  // A single clinic needs no choice.
  const branch = values.branch || (branches.length === 1 ? branches[0].uuid : '')

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setFields({})
    try {
      if (step === 'form') {
        const result = await api.accountStart({
          ...values,
          branch,
          birth_date: values.birth_date || null,
        })
        setTicket(result.ticket)
        setNotice(result.detail)
        setStep('code')
      } else {
        setMe(await api.accountVerify(ticket, code))
        navigate(after, { replace: true })
      }
    } catch (caught) {
      setError(caught.message)
      if (caught.fields) {
        setFields(
          Object.fromEntries(
            Object.entries(caught.fields).map(([name, messages]) => [
              name,
              Array.isArray(messages) ? messages.join(' ') : String(messages),
            ]),
          ),
        )
      }
    } finally {
      setBusy(false)
    }
  }

  if (options.loading) return <Loading />

  return (
    <div className="portal-auth">
      <main className="portal-auth__panel">
        <span className="portal-auth__mark" aria-hidden="true">⊕</span>
        <h1 className="portal-auth__title">إنشاء حساب</h1>
        {options.error ? (
          <p className="ui-muted">التسجيل الإلكتروني غير متاح لهذه العيادة حالياً. تواصل مع الاستقبال.</p>
        ) : (
          <form className="portal-auth__form" onSubmit={submit}>
            {error && !Object.keys(fields).length && <div className="form-error" role="alert">{error}</div>}
            {notice && step === 'code' && <div className="ui-muted" role="status">{notice}</div>}

            {step === 'form' ? (
              <>
                <Input label="الاسم الكامل" required autoComplete="name" value={values.name}
                  error={fields.name} onChange={set('name')} />
                <Input label="رقم الهاتف" type="tel" inputMode="tel" dir="ltr" required autoComplete="tel"
                  value={values.phone} error={fields.phone} onChange={set('phone')} />
                <Input label="البريد الإلكتروني" type="email" dir="ltr" required autoComplete="email"
                  hint="سنرسل إليه رمز التأكيد" value={values.email} error={fields.email} onChange={set('email')} />
                <Select label="النوع" value={values.gender} options={GENDERS} error={fields.gender}
                  onChange={set('gender')} />
                <Input label="تاريخ الميلاد" type="date" value={values.birth_date}
                  error={fields.birth_date} onChange={set('birth_date')} />
                {branches.length > 1 && (
                  <Select label="العيادة" required value={branch} placeholder="— اختر العيادة —"
                    options={branches.map((b) => ({ value: b.uuid, label: b.name }))}
                    error={fields.branch} onChange={set('branch')} />
                )}
                <Input label="كلمة المرور" type="password" required autoComplete="new-password"
                  hint="٨ أحرف على الأقل" value={values.password} error={fields.password}
                  onChange={set('password')} />
                <Checkbox
                  label="أوافق على معالجة بياناتي الشخصية والطبية لدى العيادة"
                  checked={values.consent} onChange={set('consent')} />
                {fields.consent && <div className="form-error" role="alert">{fields.consent}</div>}
                <Button type="submit" variant="primary" block loading={busy}>إرسال رمز التأكيد</Button>
              </>
            ) : (
              <>
                <Input label="رمز التأكيد" dir="ltr" inputMode="numeric" required autoFocus
                  autoComplete="one-time-code" maxLength={6} value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />
                <Button type="submit" variant="primary" block loading={busy}>تأكيد وإنشاء الحساب</Button>
                <Button type="button" variant="ghost" block onClick={() => { setStep('form'); setCode(''); setError(null) }}>
                  رجوع وتعديل البيانات
                </Button>
              </>
            )}
          </form>
        )}
        <p className="portal-auth__note">
          لديك حساب؟ <Link to={`/portal/${slug}/login${search}`}>تسجيل الدخول</Link>
        </p>
      </main>
    </div>
  )
}
