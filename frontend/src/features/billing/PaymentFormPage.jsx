import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Button, Card, CardBody, DescriptionList, ErrorState, Loading } from '@/components/ui'
import { FormFields, nullableNames } from '@/components/form/FormFields'
import { useForm, useUnsavedWarning } from '@/components/form/useForm'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation, useRecord } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { serverUrl } from '@/lib/config'
import { formatMoney } from '@/lib/format'

/**
 * Collecting money against a booking.
 *
 * A payment belongs to a booking (the group owner's rule, 2026-09-18): the
 * usual payment is taken *with* the booking, on the booking screen. This
 * screen is for the rest — a patient who paid part, or a booking made without
 * paying — so it starts from the booking, shows what is still owed, and cannot
 * take more than that. The receipt number is issued by the system, and the
 * payment goes into the recorder's open shift.
 */
const CREATE_FIELDS = [
  {
    name: 'appointment',
    label: 'الحجز',
    type: 'relation',
    resource: api.appointments,
    searchable: true,
    // Found by typing the patient's name (or the booking number) — no list to
    // scroll — and shown as both. Only bookings that still owe something.
    params: { owing: 1 },
    minSearch: 2,
    renderLabel: (row) => `${row.patient_name} · ${row.serial_number}`,
    placeholder: 'اكتب اسم المريض أو رقم الحجز…',
    hint: 'تظهر الحجوزات التي بقي عليها مبلغ فقط.',
    required: true,
    span: 2,
  },
  { name: 'amount', label: 'المبلغ', type: 'money', required: true },
  {
    name: 'method',
    label: 'طريقة الدفع',
    type: 'relation',
    resource: api.paymentMethods,
    required: true,
  },
  { name: 'notes', label: 'ملاحظات', type: 'textarea', span: 2 },
]

// An admin correcting a recorded payment: what was taken and how, nothing else.
const EDIT_FIELDS = CREATE_FIELDS.filter((field) => field.name !== 'appointment')

export function PaymentFormPage() {
  const { uuid } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { permissions } = useAuth()
  const [search] = useSearchParams()
  const editing = Boolean(uuid)
  const FIELDS = editing ? EDIT_FIELDS : CREATE_FIELDS
  // Set once a new payment is saved, so whoever recorded it can print its
  // receipt before moving on (the group owner's rule, 2026-09-12).
  const [justPaid, setJustPaid] = useState(null)
  // A new payment goes into the recorder's open cash shift; say so before
  // the form is filled in rather than after it is refused.
  const shift = useAsync(() => api.shifts.current(), [], {
    skip: editing || !permissions.works_in_shifts,
  })
  const noShift = !editing && permissions.works_in_shifts && shift.data && !shift.data.shift

  const { record, loading, error, reload } = useRecord(api.payments, uuid)
  const save = useMutation((values) =>
    editing ? api.payments.update(uuid, values) : api.payments.create(values),
  )

  const initial = editing
    ? Object.fromEntries(FIELDS.map((f) => [f.name, record?.[f.name] ?? '']))
    : {
        ...Object.fromEntries(FIELDS.map((f) => [f.name, ''])),
        appointment: search.get('appointment') ?? '',
      }

  const form = useForm(initial, { serverErrors: save.fieldErrors })
  useUnsavedWarning(form.dirty && !save.submitting)

  // Choosing the booking shows what it costs, what is paid and what is left,
  // and offers the rest as the amount.
  const appointmentUuid = form.values.appointment
  const booking = useAsync(() => api.appointments.get(appointmentUuid), [appointmentUuid], {
    skip: editing || !appointmentUuid,
  })
  const appointment = booking.data
  const remaining = appointment ? Number(appointment.amount_due) : null
  useEffect(() => {
    if (editing || !appointment || form.touched.amount) return
    form.setValues((current) => ({ ...current, amount: remaining > 0 ? String(remaining) : '' }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appointment?.uuid, remaining])

  if (editing && loading) return <Loading />
  if (editing && error) return <ErrorState error={error} onRetry={reload} />

  const submit = async (event) => {
    event.preventDefault()
    try {
      const result = await save.run(form.payload(nullableNames(FIELDS)))
      toast.success(editing ? 'تم حفظ الدفعة' : 'تم تسجيل الدفعة')
      if (!editing) {
        setJustPaid({ ...result, patient: appointment?.patient_name })
        return
      }
      navigate('/payments')
    } catch {
      /* per field */
    }
  }

  if (justPaid) {
    return (
      <>
        <PageHeader title="تم تسجيل الدفعة" back={{ to: '/payments', label: 'رجوع للدفعات' }} />
        <Card>
          <CardBody>
            <p>
              تم تسجيل الإيصال رقم <strong className="ui-num">{justPaid.receipt_number}</strong> بمبلغ{' '}
              <strong>{formatMoney(justPaid.amount)}</strong> بنجاح.
            </p>
            <div className="form-actions">
              <a
                className="ui-btn ui-btn--primary"
                href={serverUrl(`/billing/${justPaid.uuid}/print/`)}
                target="_blank"
                rel="noopener"
              >
                طباعة الإيصال
              </a>
              <Button variant="ghost" onClick={() => navigate('/queue')}>
                قائمة الانتظار
              </Button>
              <Button variant="ghost" onClick={() => navigate('/payments')}>
                الذهاب لقائمة الدفعات
              </Button>
            </div>
          </CardBody>
        </Card>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title={editing ? `تعديل الإيصال ${record?.receipt_number ?? ''}` : 'تحصيل مبلغ على حجز'}
        subtitle={editing ? undefined : 'الدفع مع الحجز يتم من شاشة الحجز؛ هذه الشاشة لتحصيل المتبقي.'}
        back={{ to: '/payments', label: 'رجوع للدفعات' }}
      />
      {noShift && (
        <Card>
          <CardBody>
            <div className="form-error">
              لا توجد وردية مفتوحة. <Link to="/shift">افتح ورديتك</Link> أولاً لتسجيل الدفعات.
            </div>
          </CardBody>
        </Card>
      )}
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
            {appointment && (
              <DescriptionList
                items={[
                  { label: 'المريض', value: appointment.patient_name },
                  { label: 'الخدمة', value: appointment.service_name },
                  { label: 'السعر', value: formatMoney(appointment.price) },
                  {
                    label: 'الخصم',
                    value: Number(appointment.discount) > 0 ? formatMoney(appointment.discount) : null,
                  },
                  { label: 'المطلوب', value: formatMoney(appointment.net_price) },
                  { label: 'المدفوع', value: formatMoney(appointment.paid_total) },
                  {
                    label: 'المتبقي',
                    value: <strong>{formatMoney(appointment.amount_due)}</strong>,
                  },
                ]}
              />
            )}
            {remaining === 0 && (
              <div className="ui-muted">هذا الحجز مسدد بالكامل — لا يوجد ما يُحصَّل.</div>
            )}
            <div className="form-actions">
              <Button type="submit" variant="primary" loading={save.submitting} disabled={remaining === 0}>
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
