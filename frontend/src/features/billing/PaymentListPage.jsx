import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Button, Checkbox, Input } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { ExportButtons } from '@/components/data/ExportButtons'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAuth } from '@/hooks/useAuth'
import { formatDateTime, formatMoney } from '@/lib/format'

import { VoidButton } from './VoidButton'

const RESOURCE = api.payments

export function PaymentListPage() {
  const navigate = useNavigate()
  const { permissions } = useAuth()
  const [search] = useSearchParams()
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [voided, setVoided] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  // Reception is shown today's payments only (billing.access); a date range
  // and an export would be controls that do nothing for them.
  const books = permissions.view_finance

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
    {
      key: 'amount',
      header: 'المبلغ',
      numeric: true,
      render: (row) => <strong>{formatMoney(row.amount)}</strong>,
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
      <ResourceTable
        resource={api.payments}
        columns={columns}
        refreshKey={refreshKey}
        params={{
          from,
          to,
          voided: voided ? '1' : undefined,
          patient: search.get('patient') || undefined,
          branch: search.get('branch') || undefined,
        }}
        searchPlaceholder="ابحث برقم الإيصال أو اسم المريض…"
        // Only an admin may change a recorded payment (the server enforces it);
        // for everyone else the rows are not links to a form they cannot save.
        onRowClick={
          permissions.is_admin && !voided ? (row) => navigate(`/payments/${row.uuid}/edit`) : undefined
        }
        filters={
          books && (
          <>
            <Checkbox
              label="الملغاة فقط"
              checked={voided}
              onChange={(event) => setVoided(event.target.checked)}
            />
            <Input
              type="date"
              value={from}
              onChange={(event) => setFrom(event.target.value)}
              aria-label="من تاريخ"
            />
            <Input
              type="date"
              value={to}
              onChange={(event) => setTo(event.target.value)}
              aria-label="إلى تاريخ"
            />
          </>
          )
        }
      />
    </>
  )
}
