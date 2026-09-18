import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '@/api'
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  ErrorState,
  Loading,
  Textarea,
} from '@/components/ui'
import { RelationSelect } from '@/components/data/RelationSelect'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { serverUrl } from '@/lib/config'
import { formatDateTime } from '@/lib/format'

import { ShiftLedger } from './ShiftLedger'
import { ShiftSummary } from './ShiftSummary'

//: How often an open shift re-reads itself, so a booking or payment made on
//: another screen (or another desk) shows up without a manual refresh.
const REFRESH_MS = 20000

/**
 * The cashier's own drawer. It starts from zero: open it, record money through
 * the usual screens while it is open — a booking's payment is taken with the
 * booking — and count the drawer against this page at any moment. Close it at
 * the end of the day. Once closed it is gone from here — the summary shown at
 * closing is the last this person sees of it; reviewing is management's
 * (/shifts).
 */
export function MyShiftPage() {
  const toast = useToast()
  const { permissions } = useAuth()
  const current = useAsync(() => api.shifts.current(), [])
  const [notes, setNotes] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [handedOver, setHandedOver] = useState(null)
  const [handedOverUuid, setHandedOverUuid] = useState(null)
  // The Owner sees every clinic, so says which one this shift is at; blank is
  // their own. Everyone else's shift is at their own clinic.
  const [branch, setBranch] = useState('')

  const open = useMutation(() => api.shifts.open({ notes, ...(branch ? { branch } : {}) }))
  const close = useMutation((uuid) => api.shifts.close(uuid))

  const isOpen = Boolean(current.data?.shift)
  const { reload } = current
  useEffect(() => {
    if (!isOpen) return undefined
    const timer = setInterval(reload, REFRESH_MS)
    // A desk left open in another tab catches up the moment it is looked at.
    const onFocus = () => reload()
    window.addEventListener('focus', onFocus)
    return () => {
      clearInterval(timer)
      window.removeEventListener('focus', onFocus)
    }
  }, [isOpen, reload])

  if (current.loading && !current.data) return <Loading />
  if (current.error) return <ErrorState error={current.error} onRetry={current.reload} />

  const shift = current.data?.shift

  const onOpen = async (event) => {
    event.preventDefault()
    try {
      await open.run()
      toast.success('تم فتح الوردية')
      setNotes('')
      setBranch('')
      setHandedOver(null)
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
      setHandedOverUuid(shift.uuid)
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
            ? `مفتوحة منذ ${formatDateTime(shift.opened_at)} · ${shift.branch_name} · تبدأ من صفر وتُحدَّث تلقائياً`
            : 'لا توجد وردية مفتوحة'
        }
        actions={
          shift && (
            <>
              <Button variant="ghost" onClick={current.reload} loading={current.loading}>
                تحديث
              </Button>
              <a
                className="ui-btn ui-btn--secondary"
                href={serverUrl(`/billing/shift/${shift.uuid}/print/`)}
                target="_blank"
                rel="noopener"
              >
                طباعة تقرير الوردية
              </a>
              <Button variant="danger" onClick={() => setConfirming(true)}>
                إغلاق الوردية
              </Button>
            </>
          )
        }
      />

      {handedOver && !shift && (
        <Card>
          <CardHeader
            title="ملخص الوردية المُغلقة"
            subtitle="هذه آخر مرة يظهر فيها هذا الملخص لك — راجعه الآن وسلّم الخزينة."
            actions={
              handedOverUuid && (
                <a
                  className="ui-btn ui-btn--secondary"
                  href={serverUrl(`/billing/shift/${handedOverUuid}/print/`)}
                  target="_blank"
                  rel="noopener"
                >
                  طباعة تقرير التسليم
                </a>
              )
            }
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
            subtitle="تبدأ الوردية من صفر. لا يمكن تسجيل حجز مدفوع أو دفعة أو مصروف إلا داخل وردية مفتوحة."
          />
          <CardBody>
            <form className="form-grid" onSubmit={onOpen}>
              {permissions.all_branches && (
                <RelationSelect
                  label="الفرع"
                  resource={api.branches}
                  placeholder="فرعي الحالي"
                  value={branch}
                  onChange={setBranch}
                  hint="أنت ترى كل الفروع: اختر الفرع الذي ستسجّل عليه المبالغ في هذه الوردية."
                />
              )}
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
              title="الجرد الآن"
              subtitle="ما سجّله النظام في ورديتك حتى هذه اللحظة، لكل طريقة دفع — قارنه بما في يدك."
              actions={
                <>
                  <Link to="/appointments/new">حجز موعد</Link>
                  <Link to="/payments/new">تحصيل متبقي</Link>
                  <Link to="/expenses">تسجيل مصروف</Link>
                </>
              }
            />
            <CardBody>
              <ShiftSummary summary={shift.summary} />
            </CardBody>
          </Card>

          <ShiftLedger shift={shift} live />
        </div>
      )}

      <ConfirmDialog
        open={confirming}
        onClose={() => setConfirming(false)}
        onConfirm={onClose}
        loading={close.submitting}
        title="إغلاق الوردية"
        message="بعد الإغلاق لن تظهر لك هذه الوردية ولا أي مبلغ فيها، ولا يعيد فتحها إلا الإدارة. تأكد من مطابقة الخزينة للصافي لكل طريقة دفع."
        confirmLabel="إغلاق الوردية"
      />
    </>
  )
}
