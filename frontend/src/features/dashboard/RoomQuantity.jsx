import { useState } from 'react'

import { api } from '@/api'
import { Badge, Button, Input, Modal } from '@/components/ui'
import { useToast } from '@/hooks/useToast'

/**
 * The doctor sets the real quantity of a service sold by quantity while the
 * patient is in the room (docs/15, D14) — pulses used, millilitres given. That
 * fixes what the service comes to (unit price × quantity, worked out by the
 * server) and the front desk is told what is left to collect.
 *
 * The doctor sees the quantity and its limits, never a price: what a doctor
 * sees of the clinic's money is their own share (billing.access).
 */
export function RoomQuantity({ row, onChanged }) {
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  if (!row.doctor_sets_quantity) return null
  const unit = row.quantity_unit || 'وحدة'

  const openIt = () => {
    setValue(row.quantity_is_estimate ? '' : String(Number(row.quantity ?? '')))
    setError(null)
    setOpen(true)
  }

  const save = async (event) => {
    event?.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.appointments.setQuantity(row.appointment, value)
      toast.success('تم تحديد الكمية، وأُبلغ الاستقبال بالمبلغ المتبقي.')
      setOpen(false)
      onChanged()
    } catch (caught) {
      setError(caught.fields?.quantity ? [].concat(caught.fields.quantity).join(' ') : caught.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <span className="ui-row">
        <span>
          {row.service_name} × {Number(row.quantity)} {unit}
        </span>
        {row.quantity_is_estimate ? <Badge tone="warn">تقديرية</Badge> : <Badge tone="ok">حدّدتها</Badge>}
        <Button size="sm" variant="secondary" onClick={openIt}>
          {row.quantity_is_estimate ? 'حدّد الكمية' : 'تعديل الكمية'}
        </Button>
      </span>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={`الكمية — ${row.service_name}`}
        size="narrow"
        footer={
          <>
            <Button variant="primary" onClick={save} loading={busy}>حفظ</Button>
            <Button variant="ghost" onClick={() => setOpen(false)}>إلغاء</Button>
          </>
        }
      >
        <form className="ui-stack" onSubmit={save}>
          {error && <div className="form-error" role="alert">{error}</div>}
          <Input
            label={`الكمية الفعلية (${unit})`} type="number" inputMode="decimal" step="any" required autoFocus
            min={row.quantity_min} max={row.quantity_max || undefined}
            value={value} onChange={(event) => setValue(event.target.value)}
            hint={[
              `الأدنى ${Number(row.quantity_min)}`,
              row.quantity_max && `الأقصى ${Number(row.quantity_max)}`,
            ].filter(Boolean).join(' — ')}
          />
          <button type="submit" className="u-visually-hidden" tabIndex={-1}>حفظ</button>
        </form>
      </Modal>
    </>
  )
}
