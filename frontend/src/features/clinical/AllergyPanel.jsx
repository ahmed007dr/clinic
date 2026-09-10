import { useState } from 'react'

import { api } from '@/api'
import { Badge, Button, Card, CardBody, CardHeader, ConfirmDialog, Input, Select } from '@/components/ui'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'

import './allergy.css'

const SEVERITIES = [
  { value: 'mild', label: 'خفيفة' },
  { value: 'moderate', label: 'متوسطة' },
  { value: 'severe', label: 'شديدة' },
]
const TONES = { mild: 'warn', moderate: 'warn', severe: 'urgent' }

/** Fetch one patient's allergies. Used by the panel and by the prescription form. */
export function usePatientAllergies(patientUuid) {
  return useAsync(
    () => api.allergies.list({ patient: patientUuid }),
    [patientUuid],
    { skip: !patientUuid },
  )
}

/**
 * The patient's allergies, readable at a glance and editable in place.
 *
 * Deliberately at the top of the patient file rather than in a tab: an allergy
 * is a standing fact that has to be seen on every encounter, not found by
 * someone who thought to look.
 */
export function AllergyPanel({ patientUuid }) {
  const toast = useToast()
  const { data, loading, reload } = usePatientAllergies(patientUuid)
  const [adding, setAdding] = useState(false)
  const [removing, setRemoving] = useState(null)
  const [values, setValues] = useState({ substance: '', reaction: '', severity: 'moderate' })

  const create = useMutation((body) => api.allergies.create(body))
  const remove = useMutation((uuid) => api.allergies.remove(uuid))
  const rows = Array.isArray(data) ? data : []

  const submit = async (event) => {
    event.preventDefault()
    try {
      await create.run({ ...values, patient: patientUuid })
      toast.success('تم تسجيل الحساسية')
      setValues({ substance: '', reaction: '', severity: 'moderate' })
      setAdding(false)
      reload()
    } catch {
      /* shown against the field */
    }
  }

  return (
    <Card className={rows.length ? 'allergy allergy--present' : 'allergy'}>
      <CardHeader
        title={rows.length ? `⚠ حساسية (${rows.length})` : 'الحساسية'}
        actions={
          !adding && (
            <Button size="sm" onClick={() => setAdding(true)}>
              إضافة
            </Button>
          )
        }
      />
      <CardBody>
        {loading && <span className="ui-muted">جارٍ التحميل…</span>}
        {!loading && rows.length === 0 && !adding && (
          <p className="ui-muted" style={{ margin: 0 }}>
            لا توجد حساسية مسجلة.
          </p>
        )}

        {rows.length > 0 && (
          <ul className="allergy__list">
            {rows.map((row) => (
              <li key={row.uuid} className="allergy__item">
                <div>
                  <strong>{row.substance}</strong>{' '}
                  <Badge tone={TONES[row.severity] ?? 'warn'}>{row.severity_label}</Badge>
                  {row.reaction && <div className="ui-muted allergy__reaction">{row.reaction}</div>}
                </div>
                <Button size="sm" variant="ghost" onClick={() => setRemoving(row)}>
                  حذف
                </Button>
              </li>
            ))}
          </ul>
        )}

        {adding && (
          <form className="allergy__form" onSubmit={submit}>
            <Input
              label="المادة"
              required
              autoFocus
              placeholder="مثال: بنسلين"
              error={create.fieldErrors.substance}
              value={values.substance}
              onChange={(e) => setValues((v) => ({ ...v, substance: e.target.value }))}
            />
            <Input
              label="رد الفعل"
              placeholder="مثال: طفح جلدي"
              value={values.reaction}
              onChange={(e) => setValues((v) => ({ ...v, reaction: e.target.value }))}
            />
            <Select
              label="الشدة"
              options={SEVERITIES}
              value={values.severity}
              onChange={(e) => setValues((v) => ({ ...v, severity: e.target.value }))}
            />
            {create.formError && <div className="form-error">{create.formError}</div>}
            <div className="ui-row">
              <Button type="submit" variant="primary" size="sm" loading={create.submitting}>
                حفظ
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
                إلغاء
              </Button>
            </div>
          </form>
        )}
      </CardBody>

      <ConfirmDialog
        open={Boolean(removing)}
        onClose={() => setRemoving(null)}
        loading={remove.submitting}
        title="حذف الحساسية"
        message={`حذف «${removing?.substance ?? ''}» من سجل المريض؟ لن تظهر بعدها أي تحذيرات عند كتابة الروشتات.`}
        confirmLabel="حذف"
        onConfirm={async () => {
          try {
            await remove.run(removing.uuid)
            toast.success('تم الحذف')
            reload()
          } catch (error) {
            toast.error(error.message)
          } finally {
            setRemoving(null)
          }
        }}
      />
    </Card>
  )
}

/** A compact banner for forms: the allergies of whoever is being prescribed for. */
export function AllergyBanner({ patientUuid }) {
  const { data } = usePatientAllergies(patientUuid)
  const rows = Array.isArray(data) ? data : []
  if (!patientUuid || rows.length === 0) return null
  return (
    <div className="allergy__banner" role="alert">
      <strong>⚠ حساسية مسجلة:</strong>{' '}
      {rows.map((row) => `${row.substance} (${row.severity_label})`).join('، ')}
    </div>
  )
}
