import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Button, Card, CardBody, ErrorState, Loading } from '@/components/ui'
import { FormFields, nullableNames } from '@/components/form/FormFields'
import { useForm, useUnsavedWarning } from '@/components/form/useForm'
import { PageHeader } from '@/components/layout/PageHeader'
import { useMutation, useRecord } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { toDateTimeInput } from '@/lib/format'

const FIELDS = [
  {
    name: 'patient',
    label: 'المريض',
    type: 'relation',
    resource: api.patients,
    // Searchable, not a dropdown: a clinic in its second year has thousands of
    // patients and a select would load every one of them.
    searchable: true,
    required: true,
    span: 2,
  },
  { name: 'scheduled_date', label: 'موعد الحجز', type: 'datetime', required: true },
  {
    name: 'doctor',
    label: 'الطبيب',
    type: 'relation',
    resource: api.doctors,
  },
  { name: 'service', label: 'الخدمة', type: 'relation', resource: api.services },
  {
    name: 'specialization',
    label: 'التخصص',
    type: 'relation',
    resource: api.specializations,
  },
  { name: 'branch', label: 'الفرع', type: 'relation', resource: api.branches },
  { name: 'price', label: 'السعر', type: 'money' },
  {
    name: 'status',
    label: 'الحالة',
    type: 'select',
    default: 'waiting',
    placeholder: undefined,
    options: [
      { value: 'waiting', label: 'الانتظار' },
      { value: 'entered', label: 'تم الدخول' },
      { value: 'called', label: 'تم الاتصال' },
      { value: 'quick', label: 'حجز سريع' },
      { value: 'requested', label: 'طلب من المريض' },
      { value: 'completed', label: 'مكتمل' },
      { value: 'cancelled', label: 'ملغي' },
      { value: 'no_show', label: 'لم يحضر' },
    ],
  },
  { name: 'notes', label: 'ملاحظات', type: 'textarea', span: 2 },
]

export function AppointmentFormPage() {
  const { uuid } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { branch, permissions } = useAuth()
  // The price is the doctor's contract price (billing/pricing.py); only
  // management may change it. Shown to everyone, editable by them alone.
  const fields = FIELDS.map((field) =>
    field.name === 'price' && !permissions.is_admin
      ? { ...field, disabled: true, hint: 'من تعاقد الطبيب — تعديله للإدارة فقط' }
      : field,
  )
  const [search] = useSearchParams()
  const editing = Boolean(uuid)

  const { record, loading, error, reload } = useRecord(api.appointments, uuid)

  const save = useMutation((values) =>
    editing ? api.appointments.update(uuid, values) : api.appointments.create(values),
  )

  const initial = editing
    ? {
        ...Object.fromEntries(
          FIELDS.map((field) => [field.name, record?.[field.name] ?? '']),
        ),
        scheduled_date: toDateTimeInput(record?.scheduled_date),
      }
    : {
        ...Object.fromEntries(FIELDS.map((f) => [f.name, f.default ?? ''])),
        // Arriving from a patient's file pre-fills them, so booking from that
        // screen is one step rather than a search for someone already open.
        patient: search.get('patient') ?? '',
        scheduled_date: toDateTimeInput(new Date()),
        branch: branch?.uuid ?? '',
      }

  const form = useForm(initial, { serverErrors: save.fieldErrors })
  useUnsavedWarning(form.dirty && !save.submitting)

  if (editing && loading) return <Loading />
  if (editing && error) return <ErrorState error={error} onRetry={reload} />

  const submit = async (event) => {
    event.preventDefault()
    try {
      const body = form.payload(nullableNames(fields))
      // The price is the server's to set for anyone but management.
      fields.filter((field) => field.disabled).forEach((field) => delete body[field.name])
      await save.run(body)
      toast.success(editing ? 'تم حفظ الموعد' : 'تم حجز الموعد')
      navigate('/appointments')
    } catch {
      /* shown per field */
    }
  }

  return (
    <>
      <PageHeader
        title={editing ? `تعديل الموعد ${record?.serial_number ?? ''}` : 'حجز موعد'}
        back={{ to: '/appointments', label: 'رجوع للمواعيد' }}
      />
      <Card>
        <CardBody>
          <form onSubmit={submit}>
            {save.formError && <div className="form-error">{save.formError}</div>}
            <FormFields
              fields={fields}
              form={form}
              errors={save.fieldErrors}
              disabled={save.submitting}
            />
            <div className="form-actions">
              <Button type="submit" variant="primary" loading={save.submitting}>
                حفظ
              </Button>
              <Button variant="ghost" onClick={() => navigate(-1)}>
                إلغاء
              </Button>
            </div>
          </form>
        </CardBody>
      </Card>
    </>
  )
}
