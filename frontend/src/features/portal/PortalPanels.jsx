import { useState } from 'react'

import {
  Badge,
  Button,
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

export function AppointmentsPanel() {
  const [paying, setPaying] = useState(null)
  return (
    <>
      <PortalList load={(api) => api.appointments()} empty="لا توجد مواعيد">
        {(a) => (
          <Card key={a.uuid}>
            <div className="portal-card__row">
              <strong>{formatDateTime(a.scheduled_date)}</strong>
              <Badge tone={APPOINTMENT_TONES[a.status] ?? 'neutral'}>{a.status_label}</Badge>
            </div>
            <div className="ui-muted">
              {a.status === 'requested'
                ? 'بانتظار تأكيد العيادة'
                : [a.service_name, a.doctor_name].filter(Boolean).join(' · ') || '—'}
            </div>
            {Number(a.due) > 0 && (
              <div className="portal-card__row">
                <span>المستحق: <strong>{formatMoney(a.due)}</strong></span>
                {a.can_pay_online && (
                  <Button size="sm" variant="primary" onClick={() => setPaying(a)}>ادفع أونلاين</Button>
                )}
              </div>
            )}
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
