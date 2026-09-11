import { useState } from 'react'

import { Button, Modal, Textarea } from '@/components/ui'
import { useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'

/**
 * Cancel a recorded payment or expense — management only, with a reason
 * (billing/voiding.py). Nothing is deleted: the row stays on record, with who
 * cancelled it and why, and drops out of every total.
 */
export function VoidButton({ resource, record, onDone }) {
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const cancel = useMutation(() => resource.action(record.uuid, 'void', { reason }))

  const submit = async () => {
    try {
      await cancel.run()
      toast.success('تم الإلغاء')
      setOpen(false)
      setReason('')
      onDone?.()
    } catch (error) {
      toast.error(error.message)
    }
  }

  return (
    <span onClick={(event) => event.stopPropagation()}>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        إلغاء
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="إلغاء القيد"
        size="narrow"
        footer={
          <>
            <Button variant="danger" onClick={submit} loading={cancel.submitting} disabled={!reason.trim()}>
              تأكيد الإلغاء
            </Button>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              رجوع
            </Button>
          </>
        }
      >
        <p className="ui-muted">
          يبقى القيد محفوظاً باسمك وتاريخ الإلغاء وسببه، ويُستبعد من كل الإجماليات والتقارير والورديات.
        </p>
        <Textarea
          label="سبب الإلغاء"
          required
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </Modal>
    </span>
  )
}
