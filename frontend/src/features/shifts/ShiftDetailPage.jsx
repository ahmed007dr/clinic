import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { api } from '@/api'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  DescriptionList,
  ErrorState,
  Loading,
  Table,
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { formatDateTime, formatMoney } from '@/lib/format'

import { ShiftSummary } from './ShiftSummary'

/**
 * One shift, for management: the figures now, the figures frozen when it was
 * closed, and every payment and expense in it. Where the two summaries
 * disagree, something was corrected after the drawer was handed over — which
 * is exactly what a review is for.
 */
export function ShiftDetailPage() {
  const { uuid } = useParams()
  const toast = useToast()
  const { data: shift, loading, error, reload } = useAsync(() => api.shifts.get(uuid), [uuid])
  const [confirm, setConfirm] = useState(null)
  const act = useMutation((kind) => (kind === 'close' ? api.shifts.close(uuid) : api.shifts.reopen(uuid)))

  if (loading && !shift) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const run = async () => {
    try {
      await act.run(confirm)
      toast.success(confirm === 'close' ? 'تم إغلاق الوردية' : 'تمت إعادة فتح الوردية')
      setConfirm(null)
      reload()
    } catch (caught) {
      setConfirm(null)
      toast.error(caught.message)
    }
  }

  const changedSinceClosing =
    shift.closing_summary && shift.closing_summary.net !== shift.summary.net

  return (
    <>
      <PageHeader
        title={`وردية ${shift.user_name}`}
        subtitle={`${shift.branch_name} · ${formatDateTime(shift.opened_at)}`}
        actions={
          shift.status === 'open' ? (
            <Button variant="danger" onClick={() => setConfirm('close')}>
              إغلاق الوردية
            </Button>
          ) : (
            <Button onClick={() => setConfirm('reopen')}>إعادة فتح الوردية</Button>
          )
        }
      />

      <div className="ui-stack">
        <Card>
          <CardBody>
            <DescriptionList
              items={[
                {
                  label: 'الحالة',
                  value: (
                    <Badge tone={shift.status === 'open' ? 'primary' : 'neutral'}>
                      {shift.status_label}
                    </Badge>
                  ),
                },
                { label: 'فُتحت', value: formatDateTime(shift.opened_at) },
                {
                  label: 'أُغلقت',
                  value: shift.closed_at
                    ? `${formatDateTime(shift.closed_at)} · ${shift.closed_by_name ?? ''}`
                    : null,
                },
                {
                  label: 'أُعيد فتحها',
                  value: shift.reopened_at
                    ? `${formatDateTime(shift.reopened_at)} · ${shift.reopened_by_name ?? ''}`
                    : null,
                },
                { label: 'ملاحظات', value: shift.notes, span: 2 },
              ]}
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="الملخص الحالي" subtitle="بحسب طريقة الدفع" />
          <CardBody>
            <ShiftSummary summary={shift.summary} />
          </CardBody>
        </Card>

        {shift.closing_summary && (
          <Card>
            <CardHeader
              title="الملخص عند الإغلاق"
              subtitle={
                changedSinceClosing
                  ? '⚠ تغيّرت المبالغ بعد الإغلاق — قارن بالملخص الحالي.'
                  : 'مطابق للملخص الحالي.'
              }
            />
            <CardBody>
              <ShiftSummary summary={shift.closing_summary} />
            </CardBody>
          </Card>
        )}

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
              empty={{ title: 'لا دفعات' }}
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
              empty={{ title: 'لا مصروفات' }}
            />
          </CardBody>
        </Card>
      </div>

      <ConfirmDialog
        open={Boolean(confirm)}
        onClose={() => setConfirm(null)}
        onConfirm={run}
        loading={act.submitting}
        title={confirm === 'close' ? 'إغلاق الوردية' : 'إعادة فتح الوردية'}
        message={
          confirm === 'close'
            ? 'ستُغلق الوردية ويُحفظ ملخصها، ولن يراها الموظف بعد ذلك.'
            : 'ستعود الوردية مفتوحة ويراها الموظف مرة أخرى ويسجل عليها.'
        }
        confirmLabel={confirm === 'close' ? 'إغلاق' : 'إعادة فتح'}
        tone={confirm === 'close' ? 'danger' : 'primary'}
      />
    </>
  )
}
