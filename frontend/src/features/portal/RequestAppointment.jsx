import { useState } from 'react'

import { Button, Input, Modal, Textarea } from '@/components/ui'
import { useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { toDateTimeInput } from '@/lib/format'

import { usePortal } from './PortalContext'

/** A request, not a booking: reception confirms it (decision D3). */
export function RequestAppointment({ open, onClose, onDone }) {
  const { api } = usePortal()
  const toast = useToast()
  const [when, setWhen] = useState('')
  const [notes, setNotes] = useState('')
  const send = useMutation((body) => api.requestAppointment(body))

  const submit = async (event) => {
    event.preventDefault()
    try {
      await send.run({ scheduled_date: when, notes })
      toast.success('تم إرسال طلبك. ستتواصل معك العيادة لتأكيد الموعد.')
      setWhen('')
      setNotes('')
      onDone()
    } catch {
      /* shown in the form */
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="طلب موعد"
      size="narrow"
      footer={
        <>
          <Button variant="primary" onClick={submit} loading={send.submitting}>إرسال الطلب</Button>
          <Button variant="ghost" onClick={onClose}>إلغاء</Button>
        </>
      }
    >
      <form className="ui-stack" onSubmit={submit}>
        {send.formError && <div className="form-error">{send.formError}</div>}
        <Input label="الموعد المفضّل" type="datetime-local" required min={toDateTimeInput(new Date())}
          value={when} onChange={(e) => setWhen(e.target.value)} error={send.fieldErrors.scheduled_date} />
        <Textarea label="سبب الزيارة (اختياري)" value={notes} onChange={(e) => setNotes(e.target.value)} />
        <p className="ui-muted" style={{ fontSize: 'var(--text-sm)', margin: 0 }}>
          هذا طلب وليس حجزاً نهائياً — تؤكّد العيادة الموعد معك.
        </p>
        <button type="submit" className="u-visually-hidden" tabIndex={-1}>إرسال</button>
      </form>
    </Modal>
  )
}
