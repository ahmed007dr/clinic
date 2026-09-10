import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Button, Input } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { PageHeader } from '@/components/layout/PageHeader'
import { formatDateTime, formatMoney } from '@/lib/format'

export function PaymentListPage() {
  const navigate = useNavigate()
  const [search] = useSearchParams()
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

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
  ]

  return (
    <>
      <PageHeader
        title="الدفعات"
        actions={
          <Button variant="primary" onClick={() => navigate('/payments/new')}>
            تسجيل دفعة
          </Button>
        }
      />
      <ResourceTable
        resource={api.payments}
        columns={columns}
        params={{ from, to, patient: search.get('patient') || undefined }}
        searchPlaceholder="ابحث برقم الإيصال أو اسم المريض…"
        onRowClick={(row) => navigate(`/payments/${row.uuid}/edit`)}
        filters={
          <>
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
        }
      />
    </>
  )
}
