import { useMemo, useState } from 'react'

import { Button, Input, Loading, Modal, Select, Textarea } from '@/components/ui'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { formatMoney, toDateTimeInput } from '@/lib/format'

import { usePortal } from './PortalContext'

/**
 * A request, not a booking: reception confirms it (decision D3).
 *
 * The choices follow the front desk's own booking form: pick a specialty, then
 * one of the clinic's doctors who has it, then a service that doctor is under
 * contract for — each with the price it will cost. The server re-checks all of
 * it; this only stops the patient offering what would be refused.
 */
export function RequestAppointment({ open, onClose, onDone }) {
  const { api } = usePortal()
  const toast = useToast()
  const [when, setWhen] = useState('')
  const [notes, setNotes] = useState('')
  const [specialization, setSpecialization] = useState('')
  const [doctor, setDoctor] = useState('')
  const [service, setService] = useState('')
  const send = useMutation((body) => api.requestAppointment(body))
  const options = useAsync(() => (open ? api.bookingOptions() : Promise.resolve(null)), [api, open])

  const doctors = useMemo(
    () => (options.data?.doctors ?? []).filter((d) => !specialization || d.specializations.includes(specialization)),
    [options.data, specialization],
  )
  const chosenDoctor = doctors.find((d) => d.uuid === doctor)
  const services = (chosenDoctor?.services ?? []).filter((s) => !specialization || !s.specialization || s.specialization === specialization)
  const noContract = Boolean(chosenDoctor) && chosenDoctor.services.length === 0

  const pickSpecialization = (value) => {
    setSpecialization(value)
    setDoctor('')
    setService('')
  }
  const pickDoctor = (value) => {
    setDoctor(value)
    setService('')
  }

  const submit = async (event) => {
    event.preventDefault()
    try {
      await send.run({ scheduled_date: when, notes, specialization, doctor, service })
      toast.success('تم إرسال طلبك. ستتواصل معك العيادة لتأكيد الموعد.')
      setWhen('')
      setNotes('')
      pickSpecialization('')
      onDone()
    } catch {
      /* shown in the form */
    }
  }

  const errors = send.fieldErrors

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
        {options.loading ? <Loading /> : (
          <>
            {(options.data?.specializations?.length ?? 0) > 0 && (
              <Select label="التخصص (اختياري)" value={specialization} error={errors.specialization}
                placeholder="— أي تخصص —"
                options={options.data.specializations.map((s) => ({ value: s.uuid, label: s.name }))}
                onChange={(e) => pickSpecialization(e.target.value)} />
            )}
            {doctors.length > 0 && (
              <Select label="الطبيب (اختياري)" value={doctor} error={errors.doctor}
                placeholder="— أي طبيب متاح —"
                options={doctors.map((d) => ({ value: d.uuid, label: `د. ${d.name}` }))}
                onChange={(e) => pickDoctor(e.target.value)} />
            )}
            {chosenDoctor && (
              <Select label="الخدمة" value={service} error={errors.service}
                placeholder={noContract ? 'لا توجد خدمات متاحة مع هذا الطبيب' : '— اختر الخدمة —'}
                disabled={noContract}
                options={services.map((s) => ({ value: s.uuid, label: `${s.name} — ${formatMoney(s.price)}` }))}
                onChange={(e) => setService(e.target.value)} />
            )}
          </>
        )}
        <Input label="الموعد المفضّل" type="datetime-local" required min={toDateTimeInput(new Date())}
          value={when} onChange={(e) => setWhen(e.target.value)} error={errors.scheduled_date} />
        <Textarea label="سبب الزيارة (اختياري)" value={notes} onChange={(e) => setNotes(e.target.value)} />
        <p className="ui-muted" style={{ fontSize: 'var(--text-sm)', margin: 0 }}>
          هذا طلب وليس حجزاً نهائياً — تؤكّد العيادة الموعد معك. السعر المعروض هو سعر تعاقد الطبيب.
        </p>
        <button type="submit" className="u-visually-hidden" tabIndex={-1}>إرسال</button>
      </form>
    </Modal>
  )
}
