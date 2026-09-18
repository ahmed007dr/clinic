import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Button } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { ExportButtons } from '@/components/data/ExportButtons'
import { SearchPanel } from '@/components/data/SearchPanel'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAuth } from '@/hooks/useAuth'
import { serverUrl } from '@/lib/config'
import { formatDateTime, formatMoney } from '@/lib/format'

import { ShiftStamp } from '../shifts/ShiftStamp'
import { VoidButton } from './VoidButton'

const RESOURCE = api.payments

export function PaymentListPage() {
  const navigate = useNavigate()
  const { permissions } = useAuth()
  const [search] = useSearchParams()
  const [refreshKey, setRefreshKey] = useState(0)
  // Reception is shown their own open shift's payments only (billing.access) —
  // a short list, loaded at once. Management sees the clinic's whole books, so
  // for them nothing loads until a period or a name is given and "بحث" is
  // pressed. A patient's card links here with the patient already chosen.
  const books = permissions.view_finance
  const linkedPatient = search.get('patient') || undefined
  const linkedBranch = search.get('branch') || undefined
  const [applied, setApplied] = useState(
    linkedPatient || linkedBranch ? { patient: linkedPatient, branch: linkedBranch } : null,
  )
  const voided = Boolean(applied?.voided)

  const columns = [
    { key: 'receipt_number', header: 'رقم الإيصال', numeric: true },
    { key: 'date', header: 'التاريخ', render: (row) => formatDateTime(row.date) },
    { key: 'patient_name', header: 'المريض' },
    {
      key: 'appointment_serial',
      header: 'الموعد',
      render: (row) => row.appointment_serial || '—',
    },
    { key: 'method_name', header: 'الطريقة', render: (row) => row.method_name || '—' },
    { key: 'shift', header: 'الوردية', render: (row) => <ShiftStamp row={row} /> },
    {
      key: 'amount',
      header: 'المبلغ',
      numeric: true,
      render: (row) => <strong>{formatMoney(row.amount)}</strong>,
    },
    {
      key: '__print',
      actions: true,
      render: (row) =>
        !row.voided_at && (
          <a
            className="ui-btn ui-btn--ghost ui-btn--sm"
            href={serverUrl(`/billing/${row.uuid}/print/`)}
            target="_blank"
            rel="noopener"
          >
            طباعة
          </a>
        ),
    },
    // Management: cancel with a reason, or review what was cancelled.
    permissions.is_admin && {
      key: '__void',
      actions: true,
      render: (row) =>
        row.voided_at ? (
          <span className="ui-muted" title={row.void_reason}>
            ملغى · {row.voided_by_name ?? ''} · {row.void_reason}
          </span>
        ) : (
          <VoidButton resource={RESOURCE} record={row} onDone={() => setRefreshKey((n) => n + 1)} />
        ),
    },
  ].filter(Boolean)

  return (
    <>
      <PageHeader
        title="الدفعات"
        subtitle={books ? undefined : 'دفعات ورديتك المفتوحة فقط'}
        actions={
          <>
          {books && <ExportButtons path="/billing/export/" />}
          <Button variant="primary" onClick={() => navigate('/payments/new')}>
            تسجيل دفعة
          </Button>
          </>
        }
      />
      {books && (
        <SearchPanel
          queryLabel="اسم المريض أو رقم الإيصال"
          queryPlaceholder="اكتب اسم المريض أو رقم الإيصال"
          initial={{ branch: linkedBranch ?? '' }}
          fields={[
            { name: 'from', label: 'من تاريخ', type: 'date' },
            { name: 'to', label: 'إلى تاريخ', type: 'date' },
            ...(permissions.all_branches
              ? [{ name: 'branch', label: 'الفرع', type: 'relation', resource: api.branches }]
              : []),
            { name: 'voided', label: 'الملغاة فقط', type: 'checkbox' },
          ]}
          validate={(values) => {
            if (values.q.trim()) return null
            if (values.from && values.to) return null
            if (values.from || values.to) return 'حدد التاريخين معاً: من وإلى، ليتم البحث في الفترة.'
            return 'يجب تحديد فترة (من – إلى) ليتم البحث فيها، أو كتابة اسم المريض أو رقم الإيصال.'
          }}
          onSearch={setApplied}
          onReset={() => setApplied(null)}
        />
      )}
      <ResourceTable
        resource={api.payments}
        columns={columns}
        refreshKey={refreshKey}
        searchable={!books}
        enabled={!books || applied !== null}
        params={
          books
            ? {
                search: applied?.q,
                from: applied?.from,
                to: applied?.to,
                branch: applied?.branch,
                voided: applied?.voided ? '1' : undefined,
                patient: applied?.patient,
              }
            : {}
        }
        searchPlaceholder="ابحث برقم الإيصال أو اسم المريض…"
        idle={{
          title: 'ابحث في الدفعات',
          message: 'حدد فترة من – إلى، أو اكتب اسم المريض أو رقم الإيصال، ثم اضغط «بحث».',
        }}
        // Only an admin may change a recorded payment (the server enforces it);
        // for everyone else the rows are not links to a form they cannot save.
        onRowClick={
          permissions.is_admin && !voided ? (row) => navigate(`/payments/${row.uuid}/edit`) : undefined
        }
      />
    </>
  )
}
