import { useState } from 'react'

import { api } from '@/api'
import { Button, Input, Modal } from '@/components/ui'
import { useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'

const iso = (date) => {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}

/**
 * "Send me my report" — emailed to the signed-in person's own address, never
 * to one typed here (api/views/my_report.py). What it contains is decided by
 * the server from the person's role, so the button is the same for everyone.
 */
export function EmailReportButton({ label = 'أرسل تقريري بالبريد' }) {
  const toast = useToast()
  const send = useMutation((body) => api.myReport.email(body))
  const [open, setOpen] = useState(false)
  const today = iso(new Date())
  const [from, setFrom] = useState(today)
  const [to, setTo] = useState(today)

  const thisMonth = () => {
    const now = new Date()
    setFrom(iso(new Date(now.getFullYear(), now.getMonth(), 1)))
    setTo(today)
  }

  const submit = async () => {
    try {
      const result = await send.run({ from, to })
      toast.success(`أُرسل التقرير إلى ${result.sent_to}`)
      setOpen(false)
    } catch (error) {
      toast.error(error.message)
    }
  }

  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>{label}</Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="إرسال التقرير بالبريد"
        size="narrow"
        footer={
          <>
            <Button variant="primary" onClick={submit} loading={send.submitting} disabled={!from || !to || to < from}>
              إرسال
            </Button>
            <Button variant="ghost" onClick={() => setOpen(false)}>إلغاء</Button>
          </>
        }
      >
        <div className="ui-stack">
          <p className="ui-muted" style={{ margin: 0 }}>
            يصلك تقرير الفترة المختارة على بريدك المسجّل في النظام.
          </p>
          <Input label="من" type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} />
          <Input label="إلى" type="date" value={to} min={from} max={today} onChange={(e) => setTo(e.target.value)} />
          <div>
            <Button size="sm" variant="ghost" onClick={thisMonth}>هذا الشهر</Button>
            <Button size="sm" variant="ghost" onClick={() => { setFrom(today); setTo(today) }}>اليوم</Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
