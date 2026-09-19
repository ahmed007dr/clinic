import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Button, Card, CardBody, ErrorState, Loading } from '@/components/ui'
import { Link } from 'react-router-dom'
import { FormFields, nullableNames } from '@/components/form/FormFields'
import { useForm, useUnsavedWarning } from '@/components/form/useForm'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation, useRecord } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { serverUrl } from '@/lib/config'
import { formatMoney, toDateTimeInput } from '@/lib/format'

import './booking.css'

//: A booking in one of these is still waiting to go in — the only point a
//: queue ticket makes sense (appointments/views.py TICKET_STATUSES).
const TICKETABLE = new Set(['waiting', 'called'])

const FIELDS = [
  {
    name: 'patient',
    label: 'المريض',
    type: 'relation',
    resource: api.patients,
    // Searchable, not a dropdown: a clinic in its second year has thousands of
    // patients and a select would load every one of them.
    searchable: true,
    // The desk finds a patient the way they are asked for: by the phone
    // number they give at the door, or by name. The server matches both
    // (api/views/patients.py search_fields); the phone is shown beside each
    // result so two people with the same name can be told apart.
    placeholder: 'ابحث برقم الهاتف أو اسم المريض',
    renderLabel: (row) => [row.name, row.phone1, row.serial_number].filter(Boolean).join(' · '),
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
  // Chosen from what the doctor offers (below): their contracted services and
  // their own specialties, each service with its price beside its name.
  { name: 'specialization', label: 'التخصص', type: 'select' },
  { name: 'service', label: 'الخدمة', type: 'select' },
  { name: 'branch', label: 'الفرع', type: 'relation', resource: api.branches },
  { name: 'price', label: 'السعر', type: 'money' },
  // How many, for a service sold by quantity (Services › «تُباع بالكمية»): the
  // total is the unit price × this, worked out by the server.
  { name: 'quantity', label: 'الكمية', type: 'number' },
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
  // How the booking reached the desk (docs/15). Chosen when booking; a website
  // booking keeps its own source and is not edited here.
  {
    name: 'source',
    label: 'مصدر الحجز',
    type: 'select',
    default: 'reception',
    placeholder: undefined,
    options: [
      { value: 'reception', label: 'الاستقبال' },
      { value: 'phone', label: 'الهاتف' },
      { value: 'whatsapp', label: 'واتساب' },
      { value: 'admin', label: 'الإدارة' },
    ],
  },
  { name: 'notes', label: 'ملاحظات', type: 'textarea', span: 2 },
  // Payment, taken with the booking in the same step (the group owner's rule,
  // 2026-09-18): how much now, and how. A coupon is a discount management gave
  // this patient. All three are for a new booking at the desk only.
  { name: 'coupon', label: 'كوبون خصم', type: 'select' },
  {
    name: 'paid_amount',
    label: 'المبلغ المدفوع الآن',
    type: 'money',
    required: true,
    hint: 'يجب سداد المبلغ كاملاً (بعد الخصم) قبل دخول المريض للطبيب.',
  },
  { name: 'payment_method', label: 'طريقة الدفع', type: 'relation', resource: api.paymentMethods },
]

export function AppointmentFormPage() {
  const { uuid } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { branch, permissions } = useAuth()
  const [search] = useSearchParams()
  const editing = Boolean(uuid)
  // Set once a new booking is saved for a patient who is waiting now, so
  // reception can print their queue ticket before moving on (the group
  // owner's rule, 2026-09-12) — replaces the form rather than sitting beside
  // it, so there is no risk of submitting the same booking twice.
  const [justBooked, setJustBooked] = useState(null)

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

  // What the chosen doctor offers: only the services they are under contract
  // for, and only their own specialties, with each price — so the receptionist
  // can tell the patient what they will pay. With no doctor yet, the whole
  // catalogue at catalogue prices. (api/views/core.py DoctorViewSet.offerings)
  const doctorId = form.values.doctor
  const offers = useAsync(
    () => api.doctors.collectionAction('offerings', doctorId ? { doctor: doctorId } : undefined),
    [doctorId],
  )
  const offer = offers.data
  const specialization = form.values.specialization

  const serviceOptions = (offer?.services ?? [])
    .filter((service) => !specialization || service.specialization === specialization)
    .map((service) => ({
      value: service.uuid,
      label: `${service.name} — ${formatMoney(service.price)}${
        service.requires_quantity ? ` / ${service.quantity_unit || 'وحدة'}` : ''
      }`,
    }))
  const specializationOptions = (offer?.specializations ?? []).map((item) => ({
    value: item.uuid,
    label: item.name,
  }))
  // A booking made before a contract changed keeps showing what it was booked
  // with, even if that is no longer on offer.
  if (record?.service && form.values.service === record.service && !serviceOptions.some((o) => o.value === record.service)) {
    serviceOptions.push({ value: record.service, label: record.service_name ?? '—' })
  }

  // The doctor changed: drop a service or specialty this doctor does not offer.
  useEffect(() => {
    if (!offer || !form.touched.doctor) return
    const { service, specialization: chosen } = form.values
    if (service && !offer.services.some((s) => s.uuid === service)) form.setValue('service', '')
    if (chosen && !offer.specializations.some((s) => s.uuid === chosen)) form.setValue('specialization', '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offer])

  // A service picked (or the doctor changed under it): its price appears at
  // once, and its specialty is filled in when the doctor has that specialty.
  useEffect(() => {
    if (!offer || !(form.touched.service || form.touched.doctor || form.touched.quantity)) return
    const chosen = offer.services.find((s) => s.uuid === form.values.service)
    if (!chosen) {
      if (!form.values.service) form.setValue('price', '')
      return
    }
    // Sold by quantity: the service's price is per unit, the booking's is unit × how many.
    const quantity = Number(form.values.quantity)
    form.setValue(
      'price',
      chosen.requires_quantity
        ? (() => {
            // No quantity typed and the doctor will set it: the smallest one is the estimate.
            const shown = quantity > 0 ? quantity : chosen.doctor_sets_quantity ? Number(chosen.min_quantity) : 0
            return shown > 0 ? (Number(chosen.price) * shown).toFixed(2) : ''
          })()
        : chosen.price,
    )
    if (
      chosen.specialization &&
      chosen.specialization !== form.values.specialization &&
      offer.specializations.some((s) => s.uuid === chosen.specialization)
    ) {
      form.setValue('specialization', chosen.specialization)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.values.service, form.values.quantity, offer])

  const price = form.values.price
  // The chosen service, and whether it is sold by quantity (with its unit price).
  const chosenService = offer?.services.find((s) => s.uuid === form.values.service)
  const soldByQuantity = Boolean(chosenService?.requires_quantity)

  // The desk takes the payment here, into their open shift; and may apply a
  // discount coupon the patient holds (issued by management).
  const canCollect = !editing && permissions.front_desk
  const patientId = form.values.patient
  const coupons = useAsync(
    () => api.coupons.list({ patient: patientId, available: 1, page_size: 50 }),
    [patientId],
    { skip: !canCollect || !patientId },
  )
  const specializationId = specialization || offer?.services.find((s) => s.uuid === form.values.service)?.specialization
  const usable = (coupons.data?.results ?? []).filter((c) =>
    c.service ? c.service === form.values.service : Boolean(c.specialization) && c.specialization === specializationId,
  )
  const couponOptions = usable.map((c) => ({
    value: c.uuid,
    label: `خصم ${formatMoney(c.amount)} — ${c.service_name || c.specialization_name}`,
  }))
  const coupon = usable.find((c) => c.uuid === form.values.coupon)
  const discount = coupon ? Math.min(Number(coupon.amount), Number(price) || 0) : 0
  const net = Math.max((Number(price) || 0) - discount, 0)
  const paidNow = Number(form.values.paid_amount) || 0

  // A coupon that no longer fits the service chosen is dropped.
  useEffect(() => {
    if (form.values.coupon && !coupon) form.setValue('coupon', '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coupon, form.values.coupon])

  // Until the cashier types an amount, "paid now" follows the net price: the
  // usual case is paying it all. (Raw setValues, so it is not counted as typed.)
  useEffect(() => {
    if (!canCollect || form.touched.paid_amount) return
    form.setValues((current) => ({ ...current, paid_amount: net ? String(net) : '' }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [net, canCollect])

  const shiftInfo = useAsync(() => api.shifts.current(), [], {
    skip: !canCollect || !permissions.works_in_shifts,
  })
  const noShift = canCollect && permissions.works_in_shifts && shiftInfo.data && !shiftInfo.data.shift

  // The field list is built last: it needs the offer, the coupons and the desk
  // state derived above, and a `const` read before its line is a runtime error.
  const noContract = Boolean(doctorId) && offer?.contracted && offer.services.length === 0
  const fields = FIELDS.map((field) => {
    if (field.name === 'service') {
      return {
        ...field,
        options: serviceOptions,
        hint: noContract
          ? 'لا توجد خدمات متعاقد عليها مع هذا الطبيب — تُضاف من الحسابات ← التعاقدات.'
          : doctorId
            ? 'الخدمات المتعاقد عليها مع هذا الطبيب فقط.'
            : 'اختر الطبيب لتظهر خدماته المتعاقد عليها.',
      }
    }
    if (field.name === 'specialization') {
      return { ...field, options: specializationOptions, hint: doctorId ? 'تخصصات هذا الطبيب فقط.' : undefined }
    }
    // The price is the doctor's contract price (billing/pricing.py); only
    // management may change it. Shown to everyone, editable by them alone.
    if (field.name === 'price' && !permissions.is_admin) {
      return { ...field, disabled: true, hint: 'من تعاقد الطبيب — تعديله للإدارة فقط' }
    }
    if (field.name === 'coupon') {
      return {
        ...field,
        options: couponOptions,
        hide: !canCollect || couponOptions.length === 0,
        hint: 'خصم أعطته الإدارة لهذا المريض على الخدمة المختارة.',
      }
    }
    if (field.name === 'paid_amount' || field.name === 'payment_method') return { ...field, hide: !canCollect }
    if (field.name === 'source') return { ...field, hide: editing }
    if (field.name === 'quantity') {
      const unit = chosenService?.quantity_unit
      const limits = [
        chosenService?.min_quantity && `الأدنى ${Number(chosenService.min_quantity)}`,
        chosenService?.max_quantity && `الأقصى ${Number(chosenService.max_quantity)}`,
      ].filter(Boolean)
      return {
        ...field,
        hide: !soldByQuantity,
        // The doctor sets the real quantity in the room: the booking may go with
        // an estimate, or none (it is then booked at the smallest quantity).
        required: !chosenService?.doctor_sets_quantity,
        label: unit ? `الكمية (${unit})` : 'الكمية',
        hint: [
          `السعر ${formatMoney(chosenService?.price)} للوحدة`,
          ...limits,
          chosenService?.doctor_sets_quantity && 'يحدد الطبيب الكمية الفعلية أثناء الجلسة — اترك الحقل فارغاً لتقدير بأقل كمية',
        ].filter(Boolean).join(' — '),
      }
    }
    return field
  })

  if (editing && loading) return <Loading />
  if (editing && error) return <ErrorState error={error} onRetry={reload} />

  // Whether this booking was outside the waiting queue before this save —
  // so editing an already-waiting booking (its price, say) does not pop the
  // ticket screen on every change, only the moment it *enters* the queue: a
  // fresh booking, or a portal request just confirmed into one.
  const enteringQueueNow = !TICKETABLE.has(record?.status)

  const submit = async (event) => {
    event.preventDefault()
    try {
      const body = form.payload(nullableNames(fields))
      // The price is the server's to set for anyone but management; a hidden
      // field (payment on an edit, say) is not the user's to send.
      fields.filter((field) => field.disabled || field.hide).forEach((field) => delete body[field.name])
      const result = await save.run(body)
      toast.success(editing ? 'تم حفظ الموعد' : 'تم حجز الموعد')
      // The confirmation screen carries the receipt and the queue ticket, so it
      // shows for a booking that just entered the queue and for any booking
      // that took a payment.
      if ((enteringQueueNow && TICKETABLE.has(result?.status)) || result?.receipt_uuid) {
        setJustBooked(result)
        return
      }
      navigate('/appointments')
    } catch {
      /* shown per field */
    }
  }

  if (justBooked) {
    return (
      <>
        <PageHeader title="تم حجز الموعد" back={{ to: '/appointments', label: 'رجوع للمواعيد' }} />
        <Card>
          <CardBody>
            <p>
              تم حجز الموعد رقم <strong className="ui-num">{justBooked.serial_number}</strong> للمريض
              بنجاح{TICKETABLE.has(justBooked.status) ? '، وهو الآن في قائمة الانتظار' : ''}.
            </p>
            {justBooked.receipt_uuid && (
              <p>
                المدفوع: <strong>{formatMoney(justBooked.paid_total)}</strong>
                {Number(justBooked.amount_due) > 0 && (
                  <>
                    {' '}
                    · المتبقي: <strong>{formatMoney(justBooked.amount_due)}</strong>
                  </>
                )}
              </p>
            )}
            {Number(justBooked.amount_due) > 0 && (
              <div className="form-error">
                لا يدخل المريض للطبيب قبل سداد المتبقي.{' '}
                <Link to={`/payments/new?appointment=${justBooked.uuid}`}>تحصيل المتبقي</Link>
              </div>
            )}
            <div className="form-actions">
              {justBooked.receipt_uuid && (
                <a
                  className="ui-btn ui-btn--primary"
                  href={serverUrl(`/billing/${justBooked.receipt_uuid}/print/`)}
                  target="_blank"
                  rel="noopener"
                >
                  طباعة إيصال الدفع
                </a>
              )}
              {TICKETABLE.has(justBooked.status) && (
                <a
                  className="ui-btn ui-btn--primary"
                  href={serverUrl(`/appointments/${justBooked.uuid}/ticket/`)}
                  target="_blank"
                  rel="noopener"
                >
                  طباعة تذكرة الانتظار
                </a>
              )}
              <Button variant="ghost" onClick={() => navigate('/appointments')}>
                الذهاب لقائمة المواعيد
              </Button>
              <Button variant="ghost" onClick={() => navigate('/queue')}>
                قائمة الانتظار
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
        title={editing ? `تعديل الموعد ${record?.serial_number ?? ''}` : 'حجز موعد'}
        back={{ to: '/appointments', label: 'رجوع للمواعيد' }}
      />
      {noShift && (
        <Card>
          <CardBody>
            <div className="form-error">
              لا توجد وردية مفتوحة. <Link to="/shift">افتح ورديتك</Link> أولاً لتسجيل الدفع مع الحجز.
            </div>
          </CardBody>
        </Card>
      )}
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
            {form.values.service && price !== '' && price != null && (
              <div className="booking-price" role="status">
                <div className="booking-price__row">
                  <span>السعر</span>
                  <span>{formatMoney(price)}</span>
                </div>
                {discount > 0 && (
                  <div className="booking-price__row">
                    <span>خصم الكوبون</span>
                    <span>− {formatMoney(discount)}</span>
                  </div>
                )}
                <div className="booking-price__row booking-price__net">
                  <span>المبلغ الذي سيدفعه المريض</span>
                  <strong>{formatMoney(editing ? record?.net_price ?? net : net)}</strong>
                </div>
                {canCollect && (
                  <div className="booking-price__row">
                    <span>المتبقي بعد الدفع الآن</span>
                    <span>{formatMoney(Math.max(net - paidNow, 0))}</span>
                  </div>
                )}
              </div>
            )}
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
