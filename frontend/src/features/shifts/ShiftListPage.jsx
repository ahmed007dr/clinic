import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '@/api'
import { Badge, Input, Select } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { PageHeader } from '@/components/layout/PageHeader'
import { formatDateTime, formatMoney } from '@/lib/format'

/**
 * Every cashier's shifts, for management: who ran it, when, what it took,
 * and whether it is still open. The server shows an Admin their own clinic
 * and the Owner every clinic; nobody else reaches this list at all.
 */
export function ShiftListPage() {
  const navigate = useNavigate()
  const [status, setStatus] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

  return (
    <>
      <PageHeader title="الورديات" subtitle="مراجعة ورديات الاستقبال والإدارة وإغلاقها وإعادة فتحها" />
      <ResourceTable
        resource={api.shifts}
        params={{ status, from, to }}
        searchable={false}
        onRowClick={(row) => navigate(`/shifts/${row.uuid}`)}
        columns={[
          { key: 'user_name', header: 'الموظف' },
          { key: 'branch_name', header: 'الفرع' },
          { key: 'opened_at', header: 'الفتح', render: (row) => formatDateTime(row.opened_at) },
          {
            key: 'closed_at',
            header: 'الإغلاق',
            render: (row) => (row.closed_at ? formatDateTime(row.closed_at) : '—'),
          },
          {
            key: 'net',
            header: 'الصافي عند الإغلاق',
            numeric: true,
            render: (row) => (row.closing_summary ? formatMoney(row.closing_summary.net) : '—'),
          },
          {
            key: 'status',
            header: 'الحالة',
            render: (row) => (
              <Badge tone={row.status === 'open' ? 'primary' : 'neutral'}>{row.status_label}</Badge>
            ),
          },
        ]}
        filters={
          <>
            <Select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              aria-label="الحالة"
              placeholder="كل الحالات"
              options={[
                { value: 'open', label: 'مفتوحة' },
                { value: 'closed', label: 'مغلقة' },
              ]}
            />
            <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="من تاريخ" />
            <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label="إلى تاريخ" />
          </>
        }
        empty={{ title: 'لا ورديات', message: 'تظهر هنا الورديات بعد أن يفتحها الموظفون.' }}
      />
    </>
  )
}
