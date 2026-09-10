import { useEffect } from 'react'
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
  APPOINTMENT_TONES,
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { formatTime } from '@/lib/format'

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
}

export function QueuePage() {
  const navigate = useNavigate()
  const toast = useToast()
  const { data, loading, error, reload } = useAsync(() => api.appointments.waiting(), [])
  const move = useMutation((uuid, status) => api.appointments.setStatus(uuid, status))

  useEffect(() => {
    const timer = setInterval(reload, 30000)
    return () => clearInterval(timer)
  }, [reload])

  const advance = async (row) => {
    const step = NEXT_STEP[row.status]
    if (!step) return
    try {
      await move.run(row.uuid, step.status)
      reload()
    } catch (caught) {
      toast.error(caught.message)
    }
  }

  const rows = data ?? []

  return (
    <>
      <PageHeader
        title="قائمة الانتظار"
        subtitle="حجوزات اليوم بترتيب الوصول · تُحدَّث تلقائياً"
        actions={
          <>
            <Button variant="ghost" onClick={reload} loading={loading}>
              تحديث
            </Button>
            <Button variant="primary" onClick={() => navigate('/appointments/new')}>
              حجز سريع
            </Button>
          </>
        }
      />

      {loading && rows.length === 0 && <Loading />}
      {error && <ErrorState error={error} onRetry={reload} />}

      {!loading && !error && rows.length === 0 && (
        <Card>
          <CardBody>
            <EmptyState
              icon="🪑"
              title="لا أحد في الانتظار"
              message="ستظهر هنا حجوزات اليوم التي لم تُنهَ بعد."
            />
          </CardBody>
        </Card>
      )}

      {rows.length > 0 && (
        <div className="queue">
          {rows.map((row, index) => {
            const step = NEXT_STEP[row.status]
            return (
              <Card key={row.uuid} className="queue__card">
                <CardBody>
                  <div className="queue__row">
                    <div className="queue__position" aria-hidden="true">
                      {index + 1}
                    </div>

                    <div className="queue__who">
                      <strong className="queue__name">{row.patient_name}</strong>
                      <div className="queue__meta">
                        <span className="ui-num">{row.serial_number}</span>
                        <span>· {formatTime(row.scheduled_date)}</span>
                        {row.doctor_name && <span>· {row.doctor_name}</span>}
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

                    <div className="queue__actions">
                      {step && (
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => advance(row)}
                          disabled={move.submitting}
                        >
                          {step.label}
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => navigate(`/patients/${row.patient}`)}
                      >
                        الملف
                      </Button>
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
