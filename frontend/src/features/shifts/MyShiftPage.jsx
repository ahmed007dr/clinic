import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '@/api'
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  ErrorState,
  Input,
  Loading,
  Table,
  Textarea,
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { formatDateTime, formatMoney } from '@/lib/format'

import { ShiftSummary } from './ShiftSummary'

/**
 * The cashier's own drawer: open it with the cash already inside, record
 * money through the usual screens while it is open, close it at the end of
 * the day. Once closed it is gone from here — the summary shown at closing is
 * the last this person sees of it; reviewing is management's (/shifts).
 */
export function MyShiftPage() {
  const toast = useToast()
  const current = useAsync(() => api.shifts.current(), [])
  const [balance, setBalance] = useState('')
  const [notes, setNotes] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [handedOver, setHandedOver] = useState(null)

  const open = useMutation(() => api.shifts.open({ opening_balance: balance || '0', notes }))
  const close = useMutation((uuid) => api.shifts.close(uuid))

  if (current.loading && !current.data) return <Loading />
  if (current.error) return <ErrorState error={current.error} onRetry={current.reload} />

  const shift = current.data?.shift

  const onOpen = async (event) => {
    event.preventDefault()
    try {
      await open.run()
      toast.success('تم فتح الوردية')
      setBalance('')
      setNotes('')
      current.reload()
    } catch {
      // formError below
    }
  }

  const onClose = async () => {
    try {
      const result = await close.run(shift.uuid)
      setConfirming(false)
      setHandedOver(result.closing_summary ?? result.summary)
      toast.success('تم إغلاق الوردية')
      current.reload()
    } catch (error) {
      setConfirming(false)
      toast.error(error.message)
    }
  }

  return (
    <>
      <PageHeader
        title="ورديتي"
        subtitle={
          shift
            ? `مفتوحة منذ ${formatDateTime(shift.opened_at)} · ${shift.branch_name}`
            : 'لا توجد وردية مفتوحة'
        }
        actions={
          shift && (
            <Button variant="danger" onClick={() => setConfirming(true)}>
              إغلاق الوردية
            </Button>
          )
        }
      />

      {handedOver && !shift && (
        <Card>
          <CardHeader
            title="ملخص الوردية المُغلقة"
            subtitle="هذه آخر مرة يظهر فيها هذا الملخص لك — راجعه الآن وسلّم الخزينة."
          />
          <CardBody>
            <ShiftSummary summary={handedOver} />
          </CardBody>
        </Card>
      )}

      {!shift && (
        <Card>
          <CardHeader
            title="فتح وردية جديدة"
            subtitle="لا يمكن تسجيل دفعات أو مصروفات إلا داخل وردية مفتوحة."
          />
          <CardBody>
            <form className="form-grid" onSubmit={onOpen}>
              <Input
                label="الرصيد الافتتاحي في الخزينة"
                type="number"
                min="0"
                step="0.01"
                value={balance}
                onChange={(event) => setBalance(event.target.value)}
                hint="المبلغ الموجود فعلاً في الخزينة الآن."
                dir="ltr"
              />
              <Textarea
                label="ملاحظات"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
              />
              {open.formError && <div className="form-error">{open.formError}</div>}
              <div className="form-actions">
                <Button type="submit" variant="primary" loading={open.submitting}>
                  فتح الوردية
                </Button>
              </div>
            </form>
          </CardBody>
        </Card>
      )}

      {shift && (
        <div className="ui-stack">
          <Card>
            <CardHeader
              title="الملخص حتى الآن"
              actions={
                <>
                  <Link to="/payments/new">تسجيل دفعة</Link>
                  <Link to="/expenses">تسجيل مصروف</Link>
                </>
              }
            />
            <CardBody>
              <ShiftSummary summary={shift.summary} />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="الدفعات" subtitle={`${shift.payments.length} دفعة`} />
            <CardBody flush>
              <Table
                columns={[
                  { key: 'receipt_number', header: 'الإيصال', numeric: true },
                  { key: 'date', header: 'الوقت', render: (row) => formatDateTime(row.date) },
                  { key: 'patient_name', header: 'المريض' },
                  { key: 'method_name', header: 'الطريقة', render: (row) => row.method_name || '—' },
                  {
                    key: 'amount',
                    header: 'المبلغ',
                    numeric: true,
                    render: (row) => <strong>{formatMoney(row.amount)}</strong>,
                  },
                ]}
                rows={shift.payments}
                empty={{ title: 'لا دفعات بعد' }}
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="المصروفات" subtitle={`${shift.expenses.length} مصروف`} />
            <CardBody flush>
              <Table
                columns={[
                  { key: 'category_name', header: 'البند', render: (row) => row.category_name || '—' },
                  { key: 'method_name', header: 'الطريقة', render: (row) => row.method_name || '—' },
                  { key: 'notes', header: 'ملاحظات', render: (row) => row.notes || '—' },
                  {
                    key: 'amount',
                    header: 'المبلغ',
                    numeric: true,
                    render: (row) => <strong>{formatMoney(row.amount)}</strong>,
                  },
                ]}
                rows={shift.expenses}
                empty={{ title: 'لا مصروفات بعد' }}
              />
            </CardBody>
          </Card>
        </div>
      )}

      <ConfirmDialog
        open={confirming}
        onClose={() => setConfirming(false)}
        onConfirm={onClose}
        loading={close.submitting}
        title="إغلاق الوردية"
        message="بعد الإغلاق لن تظهر لك هذه الوردية ولا أي مبلغ فيها، ولا يعيد فتحها إلا الإدارة. تأكد من مطابقة الخزينة للرصيد المتوقع."
        confirmLabel="إغلاق الوردية"
      />
    </>
  )
}
