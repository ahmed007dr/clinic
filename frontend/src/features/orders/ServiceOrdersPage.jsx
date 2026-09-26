import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '@/api'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge, Button, Card, CardBody, EmptyState, ErrorState, Input, Loading, Modal, Select, Tabs, Textarea } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { formatDateTime, formatMoney } from '@/lib/format'

import './orders.css'

const STATUS_TONES = {
  submitted: 'warn', approved: 'info', contacted: 'info', scheduled: 'ok', rejected: 'urgent', cancelled: 'neutral',
}
const PAYMENT_TONES = { unscheduled: 'neutral', unpaid: 'warn', partial: 'info', paid: 'ok' }
const PAYMENT_LABELS = { unscheduled: 'لم يُحجز بعد', unpaid: 'لم يُدفع', partial: 'دفع جزئي', paid: 'مدفوع' }

/** `2026-09-21T10:00:00` → the value a datetime-local input wants. */
const asInput = (iso) => (iso ? iso.slice(0, 16) : '')

/**
 * «طلبات الاستور» — what customers ordered from the website (docs/16).
 *
 * The clinic's side of the journey the customer started: the Admin approves or
 * refuses, customer service (reception) phones the customer, then the doctor and
 * time are settled — which makes real bookings — and the money is taken in a shift
 * like any payment. Each order says whether the customer chose to pay online or by
 * hand, and what has actually been paid. The Owner sees every clinic's orders and
 * the whole story of each one.
 */
export function ServiceOrdersPage() {
  const { permissions } = useAuth()
  const [status, setStatus] = useState('submitted')
  const [open, setOpen] = useState(null)
  const list = useAsync(() => api.serviceOrders.list({ status: status === 'all' ? undefined : status }), [status])
  const overview = useAsync(() => api.serviceOrders.overview(), [], { skip: !permissions.is_admin })

  const counts = list.data?.counts ?? {}
  const tabs = [
    { id: 'submitted', label: `بانتظار الموافقة${counts.to_approve ? ` (${counts.to_approve})` : ''}` },
    { id: 'approved', label: 'بانتظار الاتصال' },
    { id: 'contacted', label: 'تم الاتصال' },
    { id: 'scheduled', label: 'محددة المواعيد' },
    { id: 'rejected', label: 'مرفوضة' },
    { id: 'all', label: 'الكل' },
  ]

  const changed = () => {
    setOpen(null)
    list.reload()
    overview.reload?.()
  }

  return (
    <>
      <PageHeader
        title="طلبات الاستور"
        subtitle="ما طلبه العملاء من الموقع: الموافقة، الاتصال، تحديد المواعيد واستلام المبلغ."
      />

      {permissions.is_admin && overview.data && <Overview data={overview.data} />}

      <Tabs items={tabs} active={status} onChange={setStatus} />

      {list.loading && !list.data ? (
        <Loading />
      ) : list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : list.data.results.length === 0 ? (
        <EmptyState title="لا توجد طلبات في هذا القسم" />
      ) : (
        <ul className="orders-list">
          {list.data.results.map((order) => (
            <li key={order.uuid}>
              <OrderCard order={order} onOpen={() => setOpen(order.uuid)} />
            </li>
          ))}
        </ul>
      )}

      {open && <OrderDialog uuid={open} onClose={() => setOpen(null)} onChanged={changed} />}
    </>
  )
}

function Overview({ data }) {
  const T = data.totals
  return (
    <Card>
      <CardBody>
        <h2 className="orders-title">متابعة الاستور</h2>
        <div className="orders-totals">
          <span>بانتظار الموافقة <strong>{T.counts.submitted}</strong></span>
          <span>بانتظار الاتصال <strong>{T.counts.approved + T.counts.contacted}</strong></span>
          <span>محددة <strong>{T.counts.scheduled}</strong></span>
          <span>مطلوب <strong>{formatMoney(T.ordered)}</strong></span>
          <span>مستلم <strong>{formatMoney(T.paid)}</strong>{Number(T.paid_online) > 0 && <> (منه أونلاين {formatMoney(T.paid_online)})</>}</span>
          <span>متبقٍّ <strong>{formatMoney(T.due)}</strong></span>
        </div>
        {data.clinics.length > 1 && (
          <div className="ui-table-scroll">
            <table className="ui-table">
              <thead>
                <tr>
                  <th>العيادة</th><th>موافقة</th><th>اتصال</th><th>محددة</th><th>مرفوضة</th><th>مطلوب</th><th>مستلم</th><th>متبقٍّ</th>
                </tr>
              </thead>
              <tbody>
                {data.clinics.map((clinic) => (
                  <tr key={clinic.branch}>
                    <td>{clinic.branch_name}</td>
                    <td>{clinic.counts.submitted}</td>
                    <td>{clinic.counts.approved + clinic.counts.contacted}</td>
                    <td>{clinic.counts.scheduled}</td>
                    <td>{clinic.counts.rejected}</td>
                    <td>{formatMoney(clinic.ordered)}</td>
                    <td>{formatMoney(clinic.paid)}</td>
                    <td>{formatMoney(clinic.due)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  )
}

function PaymentBadges({ payment }) {
  return (
    <>
      <Badge tone={payment.preference === 'online' ? 'primary' : 'neutral'}>
        اختار: {payment.preference === 'online' ? 'أونلاين' : 'يدوي'}
      </Badge>
      <Badge tone={PAYMENT_TONES[payment.status]}>{PAYMENT_LABELS[payment.status]}</Badge>
      {payment.paid_online && <Badge tone="ok">دُفع أونلاين</Badge>}
    </>
  )
}

function OrderCard({ order, onOpen }) {
  return (
    <Card>
      <CardBody>
        <div className="orders-row">
          <strong>{order.serial_number}</strong>
          <Badge tone={STATUS_TONES[order.status]}>{order.status_label}</Badge>
          <PaymentBadges payment={order.payment} />
          <span className="ui-muted">{formatDateTime(order.created_at)}</span>
        </div>
        <div className="orders-row">
          <strong>{order.patient_name}</strong>
          {order.patient_phone && <a dir="ltr" href={`tel:${order.patient_phone}`}>{order.patient_phone}</a>}
          <span className="ui-muted">{order.branch_name}</span>
        </div>
        <div className="ui-muted">
          {order.lines.map((line) => (
            <span key={line.uuid} className="orders-chip">
              {line.service_name}{line.quantity && ` × ${Number(line.quantity)}`}
            </span>
          ))}
        </div>
        <div className="orders-row">
          <span>{order.total_is_estimate ? 'تقديري' : 'الإجمالي'}: <strong>{formatMoney(order.total)}</strong></span>
          <Button size="sm" variant="primary" onClick={onOpen}>فتح وتنفيذ الإجراءات</Button>
        </div>
      </CardBody>
    </Card>
  )
}

function OrderDialog({ uuid, onClose, onChanged }) {
  const { permissions } = useAuth()
  const toast = useToast()
  const { data: order, loading, error, reload } = useAsync(() => api.serviceOrders.get(uuid), [uuid])
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const run = async (action, body, done) => {
    setBusy(true)
    try {
      await action(uuid, body)
      toast.success(done)
      setNote('')
      onChanged()
    } catch (caught) {
      toast.error(caught.fields?.lines ? Object.values(caught.fields.lines).join(' ') : caught.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open onClose={onClose} title={order ? `طلب ${order.serial_number}` : 'الطلب'} size="wide">
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : (
        <div className="orders-detail">
          <div className="orders-row">
            <Badge tone={STATUS_TONES[order.status]}>{order.status_label}</Badge>
            <strong>{order.patient_name}</strong>
            {order.patient_phone && <a dir="ltr" href={`tel:${order.patient_phone}`}>{order.patient_phone}</a>}
            <span className="ui-muted">{order.branch_name}</span>
          </div>
          {order.preferred_contact && <p>أفضل وقت للاتصال: <strong>{order.preferred_contact}</strong></p>}
          {order.notes && <p>ملاحظات العميل: {order.notes}</p>}

          <h3 className="orders-title">الخدمات</h3>
          <ul className="orders-lines">
            {order.lines.map((line) => (
              <li key={line.uuid}>
                <strong>{line.service_name}</strong>
                {line.quantity && ` × ${Number(line.quantity)} ${line.quantity_unit}`}
                <span className="ui-muted">
                  {' — '}{line.unit_price === null ? 'السعر بعد التقييم' : `${line.price_is_final ? '' : '≈ '}${formatMoney(line.price)}`}
                </span>
                {(line.preferred_doctor || line.preferred_at) && (
                  <div className="ui-muted">
                    تفضيل العميل: {line.preferred_doctor && `د. ${line.preferred_doctor}`}
                    {line.preferred_at && ` — ${formatDateTime(line.preferred_at)}`}
                  </div>
                )}
              </li>
            ))}
          </ul>

          <PaymentPanel order={order} />

          {order.status === 'submitted' && (
            <div className="orders-actions">
              <Textarea label="ملاحظة أو سبب الرفض" rows={2} value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
              {permissions.is_admin ? (
                <div className="orders-row">
                  <Button variant="primary" disabled={busy} onClick={() => run(api.serviceOrders.approve, { note }, 'تمت الموافقة وأُرسل بريد للعميل.')}>
                    موافقة على الطلب
                  </Button>
                  <Button variant="danger" disabled={busy || !note.trim()} onClick={() => run(api.serviceOrders.reject, { note }, 'رُفض الطلب وأُبلغ العميل.')}>
                    رفض (السبب مطلوب)
                  </Button>
                </div>
              ) : (
                <p className="ui-muted">الموافقة على الطلب لأدمن العيادة.</p>
              )}
            </div>
          )}

          {order.status === 'approved' && (
            <div className="orders-actions">
              <p className="ui-muted">اتصل بالعميل على الرقم أعلاه، ثم سجّل الاتصال أو حدّد الموعد مباشرة.</p>
              <Input label="ملاحظة الاتصال" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
              <Button disabled={busy} onClick={() => run(api.serviceOrders.contacted, { note }, 'سُجّل الاتصال بالعميل.')}>تم الاتصال بالعميل</Button>
            </div>
          )}

          {(order.status === 'approved' || order.status === 'contacted') && (
            <ScheduleForm order={order} onDone={onChanged} />
          )}

          {order.status === 'contacted' && order.contact_note && <p className="ui-muted">ملاحظة الاتصال: {order.contact_note}</p>}
          {order.status === 'rejected' && order.review_note && <p>سبب الرفض: {order.review_note}</p>}

          <Timeline events={order.timeline} />
        </div>
      )}
    </Modal>
  )
}

function PaymentPanel({ order }) {
  const payment = order.payment
  return (
    <>
      <h3 className="orders-title">الدفع</h3>
      <div className="orders-row"><PaymentBadges payment={payment} /></div>
      {payment.status !== 'unscheduled' && (
        <p>
          المطلوب {formatMoney(payment.total)} — المستلم <strong>{formatMoney(payment.paid)}</strong> — المتبقي <strong>{formatMoney(payment.due)}</strong>
        </p>
      )}
      {payment.preference === 'online' && payment.status === 'unpaid' && (
        <p className="ui-muted">اختار العميل الدفع أونلاين: يدفع من «مواعيدي» في حسابه بعد تحديد الموعد، ويُسجَّل المبلغ تلقائياً في وردية الدفع الإلكتروني.</p>
      )}
      {payment.appointments.length > 0 && (
        <ul className="orders-lines">
          {payment.appointments.map((a) => (
            <li key={a.uuid}>
              {a.service_name}: {formatMoney(a.price)} — مدفوع {formatMoney(a.paid)} — متبقٍّ {formatMoney(a.due)}{' '}
              {Number(a.due) > 0 && (
                <Link className="ui-btn ui-btn--secondary ui-btn--sm" to={`/payments/new?appointment=${a.uuid}`}>
                  تسجيل دفعة (تحويل / نقدي)
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}
      {payment.payments.length > 0 && (
        <ul className="orders-lines">
          {payment.payments.map((p) => (
            <li key={p.uuid}>
              {p.receipt_number}: <strong>{formatMoney(p.amount)}</strong> — {p.method}
              {p.online && ' (أونلاين)'} — {formatDateTime(p.date)}
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function ScheduleForm({ order, onDone }) {
  const toast = useToast()
  const initial = useMemo(() => Object.fromEntries(order.lines.map((line) => [line.uuid, {
    doctor: line.preferred_doctor_uuid || (line.candidates.length === 1 ? line.candidates[0].uuid : ''),
    scheduled_date: asInput(line.preferred_at),
  }])), [order])
  const [values, setValues] = useState(initial)
  const [busy, setBusy] = useState(false)
  const set = (line, name, value) => setValues({ ...values, [line]: { ...values[line], [name]: value } })

  const submit = async () => {
    setBusy(true)
    try {
      await api.serviceOrders.schedule(order.uuid, {
        lines: order.lines.map((line) => ({ line: line.uuid, doctor: values[line.uuid].doctor, scheduled_date: values[line.uuid].scheduled_date.replace('T', ' ') })),
      })
      toast.success('حُددت المواعيد وأُرسل بريد للعميل.')
      onDone()
    } catch (caught) {
      toast.error(caught.fields?.lines ? Object.values(caught.fields.lines).join(' ') : caught.message)
    } finally {
      setBusy(false)
    }
  }

  const ready = order.lines.every((line) => values[line.uuid].doctor && values[line.uuid].scheduled_date)
  return (
    <div className="orders-actions">
      <h3 className="orders-title">تحديد الطبيب والموعد</h3>
      {order.lines.map((line) => (
        <div key={line.uuid} className="orders-schedule">
          <strong>{line.service_name}</strong>
          <Select label="الطبيب" value={values[line.uuid].doctor} onChange={(e) => set(line.uuid, 'doctor', e.target.value)}>
            <option value="">اختر الطبيب</option>
            {line.candidates.map((c) => (
              <option key={c.uuid} value={c.uuid}>د. {c.name}{c.price ? ` — ${formatMoney(c.price)}` : ''}</option>
            ))}
          </Select>
          <Input label="الموعد" type="datetime-local" value={values[line.uuid].scheduled_date}
            onChange={(e) => set(line.uuid, 'scheduled_date', e.target.value)} />
          {line.candidates.length === 0 && <span className="ui-muted">لا طبيب متاح لهذه الخدمة في العيادة.</span>}
        </div>
      ))}
      <Button variant="primary" disabled={busy || !ready} onClick={submit}>تحديد المواعيد وإرسال التأكيد للعميل</Button>
    </div>
  )
}

function Timeline({ events }) {
  return (
    <>
      <h3 className="orders-title">سجل الطلب</h3>
      <ol className="orders-timeline">
        {events.map((event, index) => (
          <li key={`${event.kind}-${index}`}>
            <strong>{event.label}</strong>
            {event.by && <span className="ui-muted"> — {event.by}</span>}
            <div className="ui-muted">{formatDateTime(event.at)}{event.note && ` — ${event.note}`}</div>
          </li>
        ))}
      </ol>
    </>
  )
}
