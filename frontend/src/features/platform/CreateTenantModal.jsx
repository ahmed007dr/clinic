import { useState } from 'react'

import { api } from '@/api'
import { Button, Input, Modal, Select } from '@/components/ui'
import { useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'

const EMPTY = {
  name: '',
  slug: '',
  admin_email: '',
  branch_name: 'الفرع الرئيسي',
  branch_code: 'MAIN',
  status: 'trial',
}

/**
 * Onboard a clinic: the clinic, its roles, its first branch, its
 * administrator and a trial subscription — in one transaction on the server.
 *
 * The administrator's password is generated and shown exactly once, here.
 * It is not stored readable anywhere, so the modal stays on the credentials
 * until the operator closes it deliberately.
 */
export function CreateTenantModal({ open, onClose, onCreated, statuses }) {
  const toast = useToast()
  const [values, setValues] = useState(EMPTY)
  const [created, setCreated] = useState(null)
  const create = useMutation((body) => api.platform.createTenant(body))

  const set = (key) => (event) => setValues((v) => ({ ...v, [key]: event.target.value }))

  const close = () => {
    setValues(EMPTY)
    setCreated(null)
    create.reset()
    onClose()
  }

  const submit = async (event) => {
    event.preventDefault()
    try {
      const result = await create.run(values)
      setCreated(result)
      onCreated?.()
      toast.success(`تم إنشاء عيادة ${result.tenant.name}`)
    } catch {
      /* shown per field */
    }
  }

  if (created) {
    return (
      <Modal
        open={open}
        onClose={close}
        title="تم إنشاء العيادة"
        closeOnBackdrop={false}
        footer={
          <Button variant="primary" onClick={close}>
            نسختُ البيانات، إغلاق
          </Button>
        }
      >
        <div className="platform__credentials ui-stack">
          <strong>بيانات دخول مدير العيادة — تظهر مرة واحدة فقط</strong>
          <div>
            البريد: <code dir="ltr">{created.admin_email}</code>
          </div>
          <div>
            كلمة المرور: <code dir="ltr">{created.admin_password}</code>
          </div>
          <span className="ui-muted" style={{ fontSize: 'var(--text-sm)' }}>
            سلّمها للعميل بطريقة آمنة. لا يمكن استرجاعها بعد إغلاق هذه النافذة — فقط
            إعادة تعيينها.
          </span>
        </div>
      </Modal>
    )
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title="عيادة جديدة"
      footer={
        <>
          <Button variant="primary" onClick={submit} loading={create.submitting}>
            إنشاء العيادة
          </Button>
          <Button variant="ghost" onClick={close}>
            إلغاء
          </Button>
        </>
      }
    >
      <form onSubmit={submit}>
        {create.formError && <div className="form-error">{create.formError}</div>}
        <div className="form-grid">
          <div className="form-grid__cell" style={{ gridColumn: 'span 2' }}>
            <Input label="اسم العيادة" required value={values.name} onChange={set('name')}
              error={create.fieldErrors.name} />
          </div>
          <div className="form-grid__cell">
            <Input label="المعرّف (لاتيني)" dir="ltr" placeholder="dr-ahmed" value={values.slug}
              onChange={set('slug')} error={create.fieldErrors.slug}
              hint="مطلوب إذا كان اسم العيادة بالعربية." />
          </div>
          <div className="form-grid__cell">
            <Input label="بريد مدير العيادة" type="email" dir="ltr" required
              value={values.admin_email} onChange={set('admin_email')}
              error={create.fieldErrors.admin_email} />
          </div>
          <div className="form-grid__cell">
            <Input label="اسم الفرع الأول" value={values.branch_name} onChange={set('branch_name')} />
          </div>
          <div className="form-grid__cell">
            <Input label="كود الفرع" dir="ltr" value={values.branch_code} onChange={set('branch_code')} />
          </div>
          <div className="form-grid__cell">
            <Select label="الحالة" value={values.status} onChange={set('status')}
              options={statuses} error={create.fieldErrors.status} />
          </div>
        </div>
        <p className="ui-muted" style={{ fontSize: 'var(--text-sm)', marginTop: 'var(--s4)' }}>
          تبدأ العيادة بالباقة الأساسية كفترة تجريبية ٣٠ يوماً، ويمكن تغيير الباقة بعد الإنشاء.
        </p>
        <button type="submit" className="u-visually-hidden" tabIndex={-1}>إنشاء</button>
      </form>
    </Modal>
  )
}
