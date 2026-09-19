import { useState } from 'react'
import { Link } from 'react-router-dom'

import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Input,
  Loading,
  Modal,
  Select,
  APPOINTMENT_TONES,
  LAB_TONES,
} from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { fileSize, formatDate, formatDateTime, formatMoney } from '@/lib/format'

import { usePortal } from './PortalContext'

/**
 * One list per tab, as cards: this audience is on a phone, where a table is a
 * sideways scroll. Every panel is the same shape, so one small list component
 * carries the loading, error and empty states for all of them.
 */
function PortalList({ load, empty, children }) {
  const { api } = usePortal()
  const { data, loading, error, reload } = useAsync(() => load(api), [api])
  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />
  if (!data?.length) return <EmptyState title={empty} />
  return <ul className="portal__list">{data.map(children)}</ul>
}

function Card({ className = '', children }) {
  return <li className={`portal-card ${className}`}>{children}</li>
}

/** Where the patient stands today, in words: the doctor and how many are
 * before them. A number only — the server never says who. */
function TurnNote({ appointment: a }) {
  let text = null
  let tone = 'portal-turn'
  if (a.status === 'entered') {
    text = 'أنت عند الطبيب الآن'
    tone += ' portal-turn--now'
  } else if (a.ahead_count === 0) {
    text = 'حان دورك — توجّه إلى الاستقبال'
    tone += ' portal-turn--now'
  } else if (a.ahead_count > 0) {
    text = `أمامك ${a.ahead_count} ${a.ahead_count === 1 ? 'مريض' : 'مرضى'}`
  }
  if (!text && !a.ticket_number) return null
  return (
    <div className={tone}>
      {a.ticket_number && (
        <span className="portal-turn__ticket">
          رقم التذكرة <strong className="ui-num" dir="ltr">{a.ticket_number}</strong>
          {a.queue_position && <> · ترتيبك <strong className="ui-num">{a.queue_position}</strong></>}
        </span>
      )}
      {text && <strong>{text}</strong>}
      {a.doctor_name && <span>د. {a.doctor_name}</span>}
      {a.ahead_count === 0 && a.doctor_busy && <span>الطبيب مع مريض الآن</span>}
    </div>
  )
}

const PAYMENT_STATUS = {
  paid: { label: 'مدفوع', tone: 'ok' },
  partial: { label: 'مدفوع جزئياً', tone: 'warn' },
  unpaid: { label: 'غير مدفوع', tone: 'neutral' },
}

/** Money is separate from the booking: what it costs, what was paid, and how the
 * rest is paid — at the clinic on arrival, or online once it is confirmed. */
function PaymentLine({ appointment: a }) {
  if (a.payment_status === 'free' || !['requested', 'waiting', 'quick', 'called', 'entered', 'completed'].includes(a.status)) {
    return null
  }
  const status = PAYMENT_STATUS[a.payment_status]
  return (
    <div className="portal-card__row">
      <span>
        السعر: <strong>{formatMoney(a.price)}</strong>
        {Number(a.paid) > 0 && <> · المدفوع: <strong>{formatMoney(a.paid)}</strong></>}
      </span>
      {status && <Badge tone={status.tone}>{status.label}</Badge>}
      {a.pay_at_clinic && (
        <span className="ui-muted">
          الدفع عند الوصول للعيادة{a.can_pay_online ? '، أو أونلاين الآن' : ''}
        </span>
      )}
    </div>
  )
}

/** Cancel, or ask for another time — under the clinic's rules, which the server
 * enforces and explains when it says no (`cancel_blocked_reason`). */
function BookingActions({ appointment: a, onChanged }) {
  const { api, slug } = usePortal()
  const toast = useToast()
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const canAsk = a.can_reschedule && a.service && a.branch && a.doctor

  const cancel = async () => {
    setBusy(true)
    try {
      await api.cancelAppointment(a.uuid)
      toast.success('تم إلغاء الحجز.')
      setConfirming(false)
      onChanged()
    } catch (caught) {
      toast.error(caught.message)
      setConfirming(false)
    } finally {
      setBusy(false)
    }
  }

  const open = ['requested', 'waiting', 'quick'].includes(a.status)
  if (!open) return null

  return (
    <>
      {a.reschedule_requested_for && (
        <div className="ui-muted" role="status">
          طلبت نقل الموعد إلى {formatDateTime(a.reschedule_requested_for)} — بانتظار رد العيادة.
        </div>
      )}
      <div className="portal-card__row">
        {canAsk && (
          <Link className="ui-btn ui-btn--secondary ui-btn--sm"
            to={`/portal/${slug}/services/${a.service}/${a.branch}/${a.doctor}?reschedule=${a.uuid}`}>
            طلب تغيير الموعد
          </Link>
        )}
        {a.can_cancel ? (
          <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>
            {a.status === 'requested' ? 'سحب الطلب' : 'إلغاء الحجز'}
          </Button>
        ) : (
          a.cancel_blocked_reason && <span className="ui-muted">{a.cancel_blocked_reason}</span>
        )}
      </div>
      <ConfirmDialog
        open={confirming}
        onClose={() => setConfirming(false)}
        onConfirm={cancel}
        loading={busy}
        title="إلغاء الحجز"
        message="هل تريد إلغاء هذا الحجز؟"
        confirmLabel="نعم، إلغاء"
        cancelLabel="رجوع"
      />
    </>
  )
}

export function AppointmentsPanel() {
  const [paying, setPaying] = useState(null)
  const [version, setVersion] = useState(0)
  return (
    <>
      <PortalList key={version} load={(api) => api.appointments()} empty="لا توجد مواعيد">
        {(a) => (
          <Card key={a.uuid}>
            <div className="portal-card__row">
              <strong>{formatDateTime(a.scheduled_date)}</strong>
              <Badge tone={APPOINTMENT_TONES[a.status] ?? 'neutral'}>{a.status_label}</Badge>
            </div>
            {a.branch_name && <span className="ui-muted">{a.branch_name}</span>}
            <TurnNote appointment={a} />
            <div className="ui-muted">
              {[
                a.service_name && (a.quantity ? `${a.service_name} × ${Number(a.quantity)}${a.quantity_unit ? ` ${a.quantity_unit}` : ''}${a.quantity_is_estimate ? ' (تقديرية — يحددها الطبيب)' : ''}` : a.service_name),
                a.doctor_name && `د. ${a.doctor_name}`,
              ].filter(Boolean).join(' · ')
                || (a.status === 'requested' ? '' : '—')}
              {a.status === 'requested' && `${a.service_name || a.doctor_name ? ' — ' : ''}بانتظار تأكيد العيادة`}
            </div>
            <PaymentLine appointment={a} />
            {Number(a.due) > 0 && (
              <div className="portal-card__row">
                <span>المستحق: <strong>{formatMoney(a.due)}</strong></span>
                {a.can_pay_online && (
                  <Button size="sm" variant="primary" onClick={() => setPaying(a)}>ادفع أونلاين</Button>
                )}
              </div>
            )}
            <BookingActions appointment={a} onChanged={() => setVersion((n) => n + 1)} />
          </Card>
        )}
      </PortalList>
      {paying && <PayOnline appointment={paying} onClose={() => setPaying(null)} />}
    </>
  )
}

/** Pay a booking with the clinic's own gateway; the gateway's page takes over
 * and sends the patient back here when done. */
function PayOnline({ appointment, onClose }) {
  const { api } = usePortal()
  const toast = useToast()
  const options = useAsync(() => api.payOptions(), [api])
  const [method, setMethod] = useState('')
  const [phone, setPhone] = useState('')
  const [busy, setBusy] = useState(false)
  const methods = options.data?.methods ?? []
  const chosen = method || methods[0]?.kind || ''

  return (
    <Modal
      open
      onClose={onClose}
      title={`دفع ${formatMoney(appointment.due)}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>إلغاء</Button>
          <Button
            variant="primary"
            loading={busy}
            disabled={!chosen || (chosen === 'vodafone_cash' && !phone)}
            onClick={async () => {
              setBusy(true)
              try {
                const { redirect_url: url } = await api.payAppointment(appointment.uuid, { method: chosen, phone })
                window.location.assign(url)
              } catch (caught) {
                toast.error(caught.message)
                setBusy(false)
              }
            }}
          >
            متابعة للدفع
          </Button>
        </>
      }
    >
      {options.loading ? <Loading /> : (
        <div className="ui-stack">
          <Select id="portal-pay-method" label="طريقة الدفع"
            options={methods.map((m) => ({ value: m.kind, label: m.label }))}
            value={chosen} onChange={(e) => setMethod(e.target.value)} />
          {chosen === 'vodafone_cash' && (
            <Input id="portal-pay-phone" label="رقم محفظة فودافون كاش" dir="ltr" inputMode="tel" required
              value={phone} onChange={(e) => setPhone(e.target.value)} />
          )}
          <p className="ui-muted" style={{ margin: 0 }}>ستنتقل إلى صفحة الدفع الآمنة ثم تعود إلى هنا.</p>
        </div>
      )}
    </Modal>
  )
}

const ORDER_TONES = {
  submitted: 'warn', approved: 'info', contacted: 'info', scheduled: 'ok', rejected: 'urgent', cancelled: 'neutral',
}

/** «طلباتي»: what the customer sent, and where each order stands with the clinic (docs/16). */
export function OrdersPanel() {
  return (
    <PortalList load={(api) => api.orders()} empty="لم ترسل أي طلب بعد. اختر خدمة من الصفحة الرئيسية.">
      {(order) => (
        <Card key={order.uuid}>
          <div className="portal-card__row">
            <strong>{order.serial_number}</strong>
            <Badge tone={ORDER_TONES[order.status] ?? 'neutral'}>{order.status_label}</Badge>
          </div>
          <span>{order.branch.name}{order.branch.phone && <span className="ui-muted"> — {order.branch.phone}</span>}</span>
          <ul className="portal-order-lines">
            {order.lines.map((line) => (
              <li key={`${order.uuid}-${line.service_name}`}>
                {line.service_name}
                {line.quantity && ` × ${Number(line.quantity)} ${line.quantity_unit}`}
                <span className="ui-muted">
                  {' — '}
                  {line.unit_price === null ? 'السعر بعد التقييم' : `${line.price_is_final ? '' : '≈ '}${formatMoney(line.price)}`}
                </span>
              </li>
            ))}
          </ul>
          <span className="ui-muted">
            {order.total_is_estimate ? 'الإجمالي التقديري' : 'الإجمالي'}: {formatMoney(order.total)}
          </span>
          <OrderNote order={order} />
          <OrderActions order={order} />
        </Card>
      )}
    </PortalList>
  )
}

function OrderNote({ order }) {
  if (order.status === 'submitted') return <span className="ui-muted">بانتظار موافقة العيادة على طلبك.</span>
  if (order.status === 'approved') return <span className="ui-muted">وافقت العيادة. ستتصل بك خدمة العملاء قريباً لتحديد الطبيب والموعد.</span>
  if (order.status === 'contacted') return <span className="ui-muted">اتصلت بك خدمة العملاء. يُحدَّد الموعد النهائي.</span>
  if (order.status === 'rejected' && order.review_note) return <span className="ui-muted">السبب: {order.review_note}</span>
  if (order.status === 'scheduled') {
    return (
      <ul className="portal-order-lines" aria-label="المواعيد">
        {order.appointments.map((a) => (
          <li key={a.uuid}>
            {a.service_name}{a.doctor_name && ` — د. ${a.doctor_name}`}
            <strong> — {formatDateTime(a.scheduled_date)}</strong>
          </li>
        ))}
      </ul>
    )
  }
  return null
}

function OrderActions({ order }) {
  const { api } = usePortal()
  const toast = useToast()
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  if (!order.is_open) return null

  const cancel = async () => {
    setBusy(true)
    try {
      await api.cancelOrder(order.uuid)
      toast.success('تم إلغاء الطلب.')
      window.location.reload()
    } catch (caught) {
      toast.error(caught.message)
      setConfirming(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="portal-card__row">
        <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>إلغاء الطلب</Button>
      </div>
      <ConfirmDialog
        open={confirming} onClose={() => setConfirming(false)} onConfirm={cancel} loading={busy}
        title="إلغاء الطلب" message="هل تريد إلغاء هذا الطلب؟" confirmLabel="نعم، إلغاء" cancelLabel="رجوع"
      />
    </>
  )
}

export function PrescriptionsPanel() {
  const [printing, setPrinting] = useState(null)

  const print = (uuid) => {
    setPrinting(uuid)
    document.body.classList.add('portal-printing')
    setTimeout(() => {
      window.print()
      document.body.classList.remove('portal-printing')
      setPrinting(null)
    }, 50)
  }

  return (
    <PortalList load={(api) => api.prescriptions()} empty="لا توجد روشتات">
      {(p) => (
        <Card key={p.uuid} className={printing === p.uuid ? 'portal-print' : ''}>
          <div className="portal-card__row">
            <strong>{formatDate(p.issued_at)}</strong>
            <span className="ui-muted">{p.serial_number}</span>
          </div>
          {p.doctor_name && <div className="ui-muted">د. {p.doctor_name}</div>}
          <ol className="portal-rx">
            {p.items.map((item, index) => (
              <li key={index}>
                <strong>{item.medication}</strong>
                <div className="ui-muted">
                  {[item.dosage, item.frequency, item.duration].filter(Boolean).join(' · ')}
                </div>
                {item.instructions && <div>{item.instructions}</div>}
              </li>
            ))}
          </ol>
          {p.notes && <p className="ui-muted">{p.notes}</p>}
          <Button size="sm" onClick={() => print(p.uuid)} className="portal-no-print">طباعة</Button>
        </Card>
      )}
    </PortalList>
  )
}

export function LabsPanel() {
  return (
    <PortalList load={(api) => api.labResults()} empty="لا توجد نتائج متاحة بعد">
      {(r) => (
        <Card key={r.uuid}>
          <div className="portal-card__row">
            <strong>{r.test_name}</strong>
            <Badge tone={LAB_TONES[r.flag] ?? 'neutral'}>{r.flag_label}</Badge>
          </div>
          <div>
            <strong className="ui-num">{r.value || '—'}</strong> {r.unit}
            {r.reference_range && <span className="ui-muted"> (المعدل {r.reference_range})</span>}
          </div>
          <div className="ui-muted">{formatDate(r.resulted_at)}{r.lab_name ? ` · ${r.lab_name}` : ''}</div>
        </Card>
      )}
    </PortalList>
  )
}

export function FilesPanel() {
  const { api } = usePortal()
  const toast = useToast()
  return (
    <PortalList load={(a) => a.attachments()} empty="لا توجد مستندات متاحة بعد">
      {(f) => (
        <Card key={f.uuid}>
          <div className="portal-card__row">
            <strong>{f.title}</strong>
            <Badge tone="neutral">{f.category_label}</Badge>
          </div>
          <div className="portal-card__row">
            <span className="ui-muted">{formatDate(f.created_at)} · {fileSize(f.size_bytes)}</span>
            <Button size="sm" onClick={() =>
              api.downloadAttachment(f.uuid, f.original_filename || f.title).catch((e) => toast.error(e.message))
            }>
              تنزيل
            </Button>
          </div>
        </Card>
      )}
    </PortalList>
  )
}

export function PlansPanel() {
  return (
    <PortalList load={(api) => api.plans()} empty="لا توجد خطط علاج">
      {(plan) => {
        const percent = plan.planned_sessions
          ? Math.min(100, Math.round((plan.completed_sessions / plan.planned_sessions) * 100))
          : 0
        return (
          <Card key={plan.uuid}>
            <div className="portal-card__row">
              <strong>{plan.title}</strong>
              <Badge tone="primary">{plan.status_label}</Badge>
            </div>
            <div className="portal-progress" aria-label={`${percent}%`}>
              <div className="portal-progress__bar" style={{ width: `${percent}%` }} />
            </div>
            <div className="ui-muted ui-num">
              {plan.completed_sessions} من {plan.planned_sessions} جلسات
            </div>
          </Card>
        )
      }}
    </PortalList>
  )
}

export function VisitsPanel() {
  return (
    <PortalList load={(api) => api.visits()} empty="لا توجد زيارات">
      {(v) => (
        <Card key={v.uuid}>
          <div className="portal-card__row">
            <strong>{formatDate(v.visit_date)}</strong>
            {v.doctor_name && <span className="ui-muted">د. {v.doctor_name}</span>}
          </div>
          {v.diagnosis && <div>{v.diagnosis}</div>}
          {v.follow_up_date && (
            <div className="ui-muted">موعد المتابعة: {formatDate(v.follow_up_date)}</div>
          )}
        </Card>
      )}
    </PortalList>
  )
}

export function PaymentsPanel() {
  return (
    <PortalList load={(api) => api.payments()} empty="لا توجد مدفوعات">
      {(p) => (
        <Card key={p.uuid}>
          <div className="portal-card__row">
            <strong className="ui-num">{formatMoney(p.amount)}</strong>
            <span className="ui-muted">{formatDate(p.date)}</span>
          </div>
          <div className="ui-muted">إيصال {p.receipt_number}{p.method_name ? ` · ${p.method_name}` : ''}</div>
        </Card>
      )}
    </PortalList>
  )
}
