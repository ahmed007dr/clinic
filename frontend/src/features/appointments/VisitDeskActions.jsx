import { useState } from 'react'

import { api } from '@/api'
import { Button, Input, Loading, Modal } from '@/components/ui'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { serverUrl } from '@/lib/config'
import { formatDate, formatDateTime } from '@/lib/format'

/**
 * What the front desk does with a booking once the patient has been in:
 * set the follow-up date, and print the doctor's prescriptions for signing.
 * Neither opens the medical record — the follow-up is a date, and the
 * prescriptions are a list of print links (api/views/appointments.py).
 *
 * Shown only for a booking that has opened a visit (`has_visit`).
 */
export function VisitDeskActions({ appointment, onChanged }) {
  const [open, setOpen] = useState(null) // 'follow-up' | 'print' | null
  if (!appointment.has_visit) return null

  return (
    <span className="ui-row" onClick={(event) => event.stopPropagation()}>
      <Button size="sm" variant="ghost" onClick={() => setOpen('follow-up')}>
        {appointment.follow_up_date ? `متابعة ${formatDate(appointment.follow_up_date)}` : 'موعد المتابعة'}
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setOpen('print')}>
        الروشتات
      </Button>
      {open === 'follow-up' && (
        <FollowUpDialog
          appointment={appointment}
          onClose={() => setOpen(null)}
          onSaved={() => {
            setOpen(null)
            onChanged?.()
          }}
        />
      )}
      {open === 'print' && <PrintDialog appointment={appointment} onClose={() => setOpen(null)} />}
    </span>
  )
}

function FollowUpDialog({ appointment, onClose, onSaved }) {
  const toast = useToast()
  const [date, setDate] = useState(appointment.follow_up_date ?? '')
  const save = useMutation(() => api.appointments.followUp(appointment.uuid, date || null))

  const submit = async () => {
    try {
      await save.run()
      toast.success('تم حفظ موعد المتابعة')
      onSaved()
    } catch (error) {
      toast.error(error.message)
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`موعد متابعة ${appointment.patient_name}`}
      size="narrow"
      footer={
        <>
          <Button variant="primary" onClick={submit} loading={save.submitting}>
            حفظ
          </Button>
          <Button variant="ghost" onClick={onClose}>
            إلغاء
          </Button>
        </>
      }
    >
      <Input
        label="تاريخ المتابعة"
        type="date"
        value={date}
        onChange={(event) => setDate(event.target.value)}
        hint="اتركه فارغاً لإلغاء موعد المتابعة."
      />
    </Modal>
  )
}

function PrintDialog({ appointment, onClose }) {
  const { data, loading } = useAsync(() => api.appointments.prescriptions(appointment.uuid), [
    appointment.uuid,
  ])
  const rows = data ?? []

  return (
    <Modal open onClose={onClose} title={`روشتات ${appointment.patient_name}`} size="narrow">
      {loading && <Loading />}
      {!loading && rows.length === 0 && <p className="ui-muted">لم يكتب الطبيب روشتة في هذه الزيارة بعد.</p>}
      <div className="ui-stack">
        {rows.map((row) => (
          <div className="ui-row" key={row.uuid} style={{ justifyContent: 'space-between' }}>
            <span>
              <strong className="ui-num">{row.serial_number}</strong> · {formatDateTime(row.issued_at)}
              {row.doctor_name && <> · {row.doctor_name}</>}
            </span>
            {/* Printed for the doctor to sign — the sheet has the signature line. */}
            <a
              className="ui-btn ui-btn--secondary ui-btn--sm"
              href={serverUrl(row.print_url)}
              target="_blank"
              rel="noopener"
            >
              طباعة
            </a>
          </div>
        ))}
      </div>
    </Modal>
  )
}
