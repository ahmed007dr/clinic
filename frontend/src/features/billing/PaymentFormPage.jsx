import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { api } from '@/api'
import { Button, Card, CardBody, ErrorState, Loading } from '@/components/ui'
import { FormFields, nullableNames } from '@/components/form/FormFields'
import { useForm, useUnsavedWarning } from '@/components/form/useForm'
import { PageHeader } from '@/components/layout/PageHeader'
import { useMutation, useRecord } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'

const FIELDS = [
  {
    name: 'patient',
    label: 'المريض',
    type: 'relation',
    resource: api.patients,
    searchable: true,
    required: true,
  },
  {
    name: 'appointment',
    label: 'الموعد',
    type: 'relation',
    resource: api.appointments,
    searchable: true,
    labelKey: 'serial_number',
    required: true,
  },
  { name: 'receipt_number', label: 'رقم الإيصال', required: true },
  { name: 'amount', label: 'المبلغ', type: 'money', required: true },
  {
    name: 'method',
    label: 'طريقة الدفع',
    type: 'relation',
    resource: api.paymentMethods,
  },
  { name: 'branch', label: 'الفرع', type: 'relation', resource: api.branches },
  { name: 'notes', label: 'ملاحظات', type: 'textarea', span: 2 },
]

export function PaymentFormPage() {
  const { uuid } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { branch } = useAuth()
  const editing = Boolean(uuid)

  const { record, loading, error, reload } = useRecord(api.payments, uuid)
  const save = useMutation((values) =>
    editing ? api.payments.update(uuid, values) : api.payments.create(values),
  )

  const initial = editing
    ? Object.fromEntries(FIELDS.map((f) => [f.name, record?.[f.name] ?? '']))
    : {
        ...Object.fromEntries(FIELDS.map((f) => [f.name, ''])),
        branch: branch?.uuid ?? '',
      }

  const form = useForm(initial, { serverErrors: save.fieldErrors })
  useUnsavedWarning(form.dirty && !save.submitting)

  // Choosing the appointment fills in the patient and the price. The server
  // rejects a payment whose patient does not match its appointment, so this
  // is not a convenience alone — it keeps the form from producing a payload
  // that will be refused.
  const appointmentUuid = form.values.appointment
  useEffect(() => {
    if (!appointmentUuid || editing) return
    let active = true
    api.appointments
      .get(appointmentUuid)
      .then((appointment) => {
        if (!active) return
        form.setValue('patient', appointment.patient)
        if (!form.values.amount && appointment.price) {
          form.setValue('amount', appointment.price)
        }
        if (!form.values.branch && appointment.branch) {
          form.setValue('branch', appointment.branch)
        }
      })
      .catch(() => {})
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appointmentUuid, editing])

  if (editing && loading) return <Loading />
  if (editing && error) return <ErrorState error={error} onRetry={reload} />

  const submit = async (event) => {
    event.preventDefault()
    try {
      await save.run(form.payload(nullableNames(FIELDS)))
      toast.success('تم تسجيل الدفعة')
      navigate('/payments')
    } catch {
      /* per field */
    }
  }

  return (
    <>
      <PageHeader
        title={editing ? `تعديل الإيصال ${record?.receipt_number ?? ''}` : 'تسجيل دفعة'}
        back={{ to: '/payments', label: 'رجوع للدفعات' }}
      />
      <Card>
        <CardBody>
          <form onSubmit={submit}>
            {save.formError && <div className="form-error">{save.formError}</div>}
            <FormFields
              fields={FIELDS}
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
