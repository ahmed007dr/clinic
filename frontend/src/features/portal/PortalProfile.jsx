import { useEffect, useState } from 'react'

import { Button, Checkbox, ErrorState, Input, Loading } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'

import { usePortal } from './PortalContext'

const EDITABLE = [
  ['address', 'العنوان'],
  ['governorate', 'المحافظة'],
  ['area', 'المنطقة'],
  ['whatsapp', 'واتساب'],
  ['emergency_contact_name', 'شخص للطوارئ — الاسم'],
  ['emergency_contact_phone', 'شخص للطوارئ — الهاتف'],
  ['emergency_contact_relation', 'صلة القرابة'],
]

const PREFERENCES = [
  ['contact_by_phone', 'الاتصال الهاتفي'],
  ['contact_by_whatsapp', 'واتساب'],
  ['contact_by_sms', 'رسائل SMS'],
  ['contact_by_email', 'البريد الإلكتروني'],
]

const isPhone = (name) => name.includes('phone') || name === 'whatsapp'

/**
 * "My account": the patient's own contact details (docs/15, Phase 2).
 *
 * Name and phone number are shown but not editable here — the clinic changes
 * those. A new e-mail address is confirmed with a code sent to it before it
 * replaces the old one.
 */
export function PortalProfile() {
  const { api } = usePortal()
  const { data, loading, error, reload } = useAsync(() => api.profile(), [api])

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />
  return <ProfileForm profile={data} reload={reload} />
}

function fieldMessages(caught) {
  return Object.fromEntries(
    Object.entries(caught.fields ?? {}).map(([name, messages]) => [
      name,
      Array.isArray(messages) ? messages.join(' ') : String(messages),
    ]),
  )
}

function ProfileForm({ profile, reload }) {
  const { api } = usePortal()
  const toast = useToast()
  const [values, setValues] = useState(profile)
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState({})

  useEffect(() => setValues(profile), [profile])

  const set = (name) => (event) =>
    setValues((previous) => ({
      ...previous,
      [name]: event.target.type === 'checkbox' ? event.target.checked : event.target.value,
    }))

  const save = async (event) => {
    event.preventDefault()
    setSaving(true)
    setErrors({})
    try {
      const body = Object.fromEntries([...EDITABLE, ...PREFERENCES].map(([name]) => [name, values[name]]))
      await api.saveProfile(body)
      toast.success('تم حفظ بياناتك.')
      reload()
    } catch (caught) {
      setErrors(fieldMessages(caught))
      toast.error(caught.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="portal-card">
      <dl className="portal-about__facts">
        <dt>الاسم</dt>
        <dd>{profile.name}</dd>
        <dt>رقم الملف</dt>
        <dd dir="ltr">{profile.serial_number}</dd>
        <dt>الهاتف</dt>
        <dd dir="ltr">{profile.phone || '—'}</dd>
      </dl>
      <p className="ui-muted">لتغيير الاسم أو رقم الهاتف تواصل مع استقبال العيادة.</p>

      <EmailChange current={profile.email} onChanged={reload} />

      <form className="ui-stack" onSubmit={save}>
        {EDITABLE.map(([name, label]) => (
          <Input key={name} label={label} value={values[name] ?? ''} error={errors[name]}
            dir={isPhone(name) ? 'ltr' : undefined} onChange={set(name)} />
        ))}
        <strong>وسائل التواصل المفضّلة</strong>
        {PREFERENCES.map(([name, label]) => (
          <Checkbox key={name} label={label} checked={Boolean(values[name])} onChange={set(name)} />
        ))}
        <Button type="submit" variant="primary" loading={saving}>حفظ</Button>
      </form>
    </div>
  )
}

function EmailChange({ current, onChanged }) {
  const { api } = usePortal()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [ticket, setTicket] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const reset = () => {
    setOpen(false)
    setEmail('')
    setTicket('')
    setCode('')
    setError(null)
  }

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (!ticket) {
        const result = await api.changeEmail(email)
        setTicket(result.ticket)
        toast.success(result.detail)
      } else {
        await api.verifyEmail(ticket, code)
        toast.success('تم تغيير بريدك الإلكتروني.')
        reset()
        onChanged()
      }
    } catch (caught) {
      setError(fieldMessages(caught).email || caught.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="ui-stack">
      <div>
        <strong>البريد الإلكتروني: </strong>
        <span dir="ltr">{current || 'غير مسجّل'}</span>{' '}
        {!open && (
          <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(true)}>
            {current ? 'تغيير' : 'إضافة'}
          </Button>
        )}
      </div>
      {open && (
        <form className="ui-stack" onSubmit={submit}>
          {error && <div className="form-error" role="alert">{error}</div>}
          <Input label="البريد الجديد" type="email" dir="ltr" required disabled={Boolean(ticket)}
            value={email} onChange={(e) => setEmail(e.target.value)} />
          {ticket && (
            <Input label="الرمز المرسل إلى البريد الجديد" dir="ltr" inputMode="numeric" required autoFocus
              maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />
          )}
          <div className="ui-row">
            <Button type="submit" variant="primary" loading={busy}>{ticket ? 'تأكيد' : 'إرسال الرمز'}</Button>
            <Button type="button" variant="ghost" onClick={reset}>إلغاء</Button>
          </div>
        </form>
      )}
    </div>
  )
}
