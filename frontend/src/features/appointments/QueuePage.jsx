import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '@/api'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  Loading,
  Select,
  Tabs,
  APPOINTMENT_TONES,
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { serverUrl } from '@/lib/config'
import { formatMoney, formatTime } from '@/lib/format'

import { VisitDeskActions } from './VisitDeskActions'
import './queue.css'

/**
 * Today's queue, as the front desk works it.
 *
 * The gap this closes: the system could record that someone was *booked*, but
 * moving them through the visit — arrived, called, in with the doctor — meant
 * editing the appointment on a form. Here each step is one button on the row.
 *
 * It refreshes on a timer because two people run this screen at once: the
 * receptionist who checks patients in and the nurse who calls them through.
 */
const NEXT_STEP = {
  waiting: { status: 'called', label: 'نداء' },
  called: { status: 'entered', label: 'دخول' },
  quick: { status: 'entered', label: 'دخول' },
  entered: { status: 'completed', label: 'إنهاء الزيارة' },
}

//: Still waiting to go in — the only point a queue ticket makes sense
//: (appointments/views.py TICKET_STATUSES).
const TICKETABLE = new Set(['waiting', 'called'])

//: Who is still waiting to see the doctor. Someone already `entered` is with
//: the doctor: shown on their own tab and never counted as "ahead"
//: (appointments/queue.py).
const WAITING = new Set(['waiting', 'called', 'quick'])

//: One tab per state, plus the one that answers "who still owes money?".
//: `match` decides which of today's rows a tab shows.
const owes = (row) => Number(row.amount_due) > 0
const TABS = [
  { id: 'all', label: 'الكل', match: (row) => WAITING.has(row.status), empty: 'لا أحد في الانتظار' },
  { id: 'waiting', label: 'انتظار', match: (row) => row.status === 'waiting', empty: 'لا أحد في حالة انتظار' },
  { id: 'called', label: 'تم الاتصال بالهاتف', match: (row) => row.status === 'called', empty: 'لم يُتصل بأحد بعد' },
  { id: 'quick', label: 'حجز سريع', match: (row) => row.status === 'quick', empty: 'لا حجوزات سريعة' },
  {
    id: 'owing',
    label: 'متبقي عليه مبلغ',
    match: (row) => WAITING.has(row.status) && owes(row),
    empty: 'لا أحد عليه مبلغ متبقٍ',
  },
  { id: 'entered', label: 'بالداخل الآن', match: (row) => row.status === 'entered', empty: 'لا أحد عند الطبيب الآن' },
]

//: A row's turn, for its own doctor: "دوره الآن" for the first, else how many
//: are before it. Null when there is no doctor to queue for.
function Turn({ row }) {
  if (row.ahead_count === null || row.ahead_count === undefined) {
    return (
      <div className="queue__turn queue__turn--none" title="حدد الطبيب ليُحسب الدور">
        <span className="queue__turn-label">بلا طبيب</span>
      </div>
    )
  }
  const now = row.ahead_count === 0
  return (
    <div className={`queue__turn${now ? ' queue__turn--now' : ''}`}>
      {now ? (
        <span className="queue__turn-label">دوره الآن</span>
      ) : (
        <>
          <span className="queue__turn-num ui-num">{row.ahead_count}</span>
          <span className="queue__turn-label">أمامه</span>
        </>
      )}
    </div>
  )
}

export function QueuePage() {
  const navigate = useNavigate()
  const toast = useToast()
  const { permissions } = useAuth()
  // The desk runs the queue — call, send in, collect, print. A doctor only
  // looks at who is waiting for them (the owner's rule, 2026-09-19); the
  // server refuses the moves too (api/views/appointments.py FrontDeskWrites).
  const desk = permissions.front_desk
  const { data, loading, error, reload } = useAsync(() => api.appointments.waiting(), [])
  const move = useMutation((uuid, status) => api.appointments.setStatus(uuid, status))

  useEffect(() => {
    const timer = setInterval(reload, 30000)
    return () => clearInterval(timer)
  }, [reload])

  const [tab, setTab] = useState('all')
  const [doctor, setDoctor] = useState('')

  // A patient goes in to the doctor only once the booking is paid in full
  // (net of any coupon). With something still owing, the button collects it
  // first — the payment lands in this cashier's shift — instead of failing.
  const advance = async (row) => {
    const step = NEXT_STEP[row.status]
    if (!step) return
    if (step.status === 'entered' && owes(row)) {
      navigate(`/payments/new?appointment=${row.uuid}`)
      return
    }
    try {
      await move.run(row.uuid, step.status)
      reload()
    } catch (caught) {
      toast.error(caught.message)
    }
  }

  const all = data ?? []

  // The doctors who have someone in today's queue: a filter only offers what
  // it can show. Each doctor's turn numbers come from the server, so choosing
  // one changes what is listed and the tab counts, never the numbers.
  const doctors = useMemo(() => {
    const seen = new Map()
    all.forEach((row) => {
      if (row.doctor && !seen.has(row.doctor)) seen.set(row.doctor, row.doctor_name)
    })
    return [...seen].map(([value, label]) => ({ value, label }))
  }, [data])
  // A doctor whose last patient has gone in drops out of the list; the filter
  // must not stay stuck on someone it can no longer offer.
  const activeDoctor = doctors.some((item) => item.value === doctor) ? doctor : ''
  const inScope = activeDoctor ? all.filter((row) => row.doctor === activeDoctor) : all

  // Nobody but the desk sees what a booking still owes, so no tab for it.
  const visibleTabs = TABS.filter((item) => desk || item.id !== 'owing')
  const tabs = visibleTabs.map((item) => ({
    id: item.id,
    label: item.label,
    badge: inScope.filter(item.match).length,
  }))
  const current = visibleTabs.find((item) => item.id === tab) ?? visibleTabs[0]
  const rows = inScope.filter(current.match)

  return (
    <>
      <PageHeader
        title="قائمة الانتظار"
        subtitle={
          desk
            ? 'حجوزات اليوم بترتيب الوصول · تُحدَّث تلقائياً'
            : 'المرضى المنتظرون لديك اليوم بترتيب الوصول · للاطلاع فقط · تُحدَّث تلقائياً'
        }
        actions={
          <>
            <Button variant="ghost" onClick={reload} loading={loading}>
              تحديث
            </Button>
            {desk && (
              <Button variant="primary" onClick={() => navigate('/appointments/new')}>
                حجز سريع
              </Button>
            )}
          </>
        }
      />

      {loading && all.length === 0 && <Loading />}
      {error && <ErrorState error={error} onRetry={reload} />}

      {all.length > 0 && (
        <div className="queue__bar">
          <Tabs items={tabs} active={tab} onChange={setTab} />
          {doctors.length > 1 && (
            <Select
              id="queue-doctor"
              label="الطبيب"
              placeholder="كل الأطباء"
              options={doctors}
              value={activeDoctor}
              onChange={(event) => setDoctor(event.target.value)}
            />
          )}
        </div>
      )}

      {!loading && !error && rows.length === 0 && (
        <Card>
          <CardBody>
            <EmptyState
              icon="🪑"
              title={all.length === 0 ? 'لا أحد في الانتظار' : current.empty}
              message="ستظهر هنا حجوزات اليوم التي لم تُنهَ بعد."
            />
          </CardBody>
        </Card>
      )}

      {rows.length > 0 && (
        <div className="queue">
          {rows.map((row) => {
            const step = NEXT_STEP[row.status]
            return (
              <Card key={row.uuid} className="queue__card">
                <CardBody>
                  <div className="queue__row">
                    {row.status === 'entered' ? (
                      <div className="queue__turn queue__turn--inside">
                        <span className="queue__turn-label">بالداخل</span>
                      </div>
                    ) : (
                      <Turn row={row} />
                    )}

                    <div className="queue__who">
                      <strong className="queue__name">{row.patient_name}</strong>
                      <div className="queue__doctor">{row.doctor_name || 'بدون طبيب'}</div>
                      <div className="queue__meta">
                        <span className="ui-num">{row.serial_number}</span>
                        <span>· {formatTime(row.scheduled_date)}</span>
                        {row.service_name && <span>· {row.service_name}</span>}
                      </div>
                      {row.patient_phone && (
                        <a
                          className="queue__phone"
                          href={`tel:${row.patient_phone}`}
                          dir="ltr"
                        >
                          {row.patient_phone}
                        </a>
                      )}
                    </div>

                    <Badge tone={APPOINTMENT_TONES[row.status] ?? 'neutral'}>
                      {row.status_label}
                    </Badge>
                    {row.status !== 'entered' && owes(row) && (
                      <Badge tone="warn">متبقي {formatMoney(row.amount_due)}</Badge>
                    )}

                    <div className="queue__actions">
                      {desk && step && (
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => advance(row)}
                          disabled={move.submitting}
                        >
                          {step.status === 'entered' && owes(row) ? 'تحصيل ثم دخول' : step.label}
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => navigate(`/patients/${row.patient}`)}
                      >
                        الملف
                      </Button>
                      {desk && TICKETABLE.has(row.status) && (
                        <a
                          className="ui-btn ui-btn--ghost ui-btn--sm"
                          href={serverUrl(`/appointments/${row.uuid}/ticket/`)}
                          target="_blank"
                          rel="noopener"
                        >
                          تذكرة الانتظار
                        </a>
                      )}
                      {desk && <VisitDeskActions appointment={row} onChanged={reload} />}
                    </div>
                  </div>
                </CardBody>
              </Card>
            )
          })}
        </div>
      )}
    </>
  )
}
