import { useState } from 'react'

import { api } from '@/api'
import { Badge, Button, Checkbox, Input, Select, StatTile } from '@/components/ui'
import { MultiRelationSelect } from '@/components/data/MultiRelationSelect'
import { RelationSelect } from '@/components/data/RelationSelect'
import { ResourceTable } from '@/components/data/ResourceTable'
import { EmailReportButton } from '@/components/data/EmailReportButton'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { serverUrl } from '@/lib/config'
import { formatDateTime, formatMoney } from '@/lib/format'

/**
 * The doctor's share of every payment received (billing/commissions.py).
 *
 * A doctor sees their own — each service, its original price, what was
 * paid, their percentage, their share, and whether it has been handed over —
 * in the clinic they are looking at. Management sees their clinic's doctors
 * and records a share as received.
 */
export function CommissionsPage() {
  const toast = useToast()
  const { permissions } = useAuth()
  const manage = permissions.is_admin
  const [status, setStatus] = useState('')
  const [doctors, setDoctors] = useState([]) // one or several
  const [service, setService] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [chosen, setChosen] = useState(new Set())
  const [refreshKey, setRefreshKey] = useState(0)

  const params = {
    status,
    doctor: doctors.length ? doctors.join(',') : undefined,
    service: service || undefined,
    from,
    to,
  }
  // The signed sheet is the list on screen: same filters, on paper
  // (billing/commissions.py `narrow`). Whatever the status filter says —
  // pending or already handed over — is what gets printed.
  const printUrl = serverUrl(
    `/billing/commissions/print/?${new URLSearchParams(
      Object.entries(params).filter(([, value]) => value),
    )}`,
  )
  const summary = useAsync(() => api.commissions.summary(params), [JSON.stringify(params), refreshKey])
  const settle = useMutation(() => api.commissions.settle([...chosen]))

  const toggle = (uuid) =>
    setChosen((current) => {
      const next = new Set(current)
      if (next.has(uuid)) next.delete(uuid)
      else next.add(uuid)
      return next
    })

  const onSettle = async () => {
    try {
      const result = await settle.run()
      toast.success(`تم تسجيل استلام ${result.settled} نسبة`)
      setChosen(new Set())
      setRefreshKey((value) => value + 1)
    } catch (error) {
      toast.error(error.message)
    }
  }

  const columns = [
    manage && {
      key: '__pick',
      header: '',
      render: (row) =>
        row.status === 'pending' ? (
          <Checkbox
            aria-label="اختيار"
            checked={chosen.has(row.uuid)}
            onChange={() => toggle(row.uuid)}
          />
        ) : null,
    },
    { key: 'created_at', header: 'التاريخ', render: (row) => formatDateTime(row.created_at) },
    manage && { key: 'doctor_name', header: 'الطبيب' },
    { key: 'patient_name', header: 'المريض', render: (row) => row.patient_name || '—' },
    { key: 'description', header: 'الخدمة' },
    { key: 'original_price', header: 'السعر الأصلي', numeric: true, render: (row) => formatMoney(row.original_price) },
    { key: 'paid_amount', header: 'المدفوع', numeric: true, render: (row) => formatMoney(row.paid_amount) },
    { key: 'percent', header: 'النسبة', numeric: true, render: (row) => `${Number(row.percent)}%` },
    {
      key: 'amount',
      header: 'النصيب',
      numeric: true,
      render: (row) => <strong>{formatMoney(row.amount)}</strong>,
    },
    {
      key: 'status',
      header: 'الحالة',
      render: (row) => (
        <Badge tone={row.status === 'settled' ? 'ok' : 'warn'}>
          {row.status_label}
          {row.settled_at ? ` · ${formatDateTime(row.settled_at)}` : ''}
        </Badge>
      ),
    },
  ].filter(Boolean)

  return (
    <>
      <PageHeader
        title={manage ? 'نسب الأطباء' : 'نسبي وحساباتي'}
        subtitle="نسبة الطبيب من المبلغ المدفوع فعلاً لكل خدمة"
        actions={
          <>
            <EmailReportButton />
            <a className="ui-btn ui-btn--secondary" href={printUrl} target="_blank" rel="noopener">
              طباعة التقرير{status ? ` (${status === 'settled' ? 'المستلمة' : 'المعلّقة'})` : ''}
            </a>
            {manage && (
              <Button variant="primary" onClick={onSettle} disabled={chosen.size === 0} loading={settle.submitting}>
                تسجيل استلام المحدد ({chosen.size})
              </Button>
            )}
          </>
        }
      />

      <div className="ui-stack">
        <div className="ui-grid ui-grid--3">
          <StatTile label="معلّقة" value={formatMoney(summary.data?.pending)} tone="primary" icon="⏳" />
          <StatTile label="مستلمة" value={formatMoney(summary.data?.settled)} tone="ok" icon="✓" />
          <StatTile label="الإجمالي" value={formatMoney(summary.data?.total)} icon="Σ" />
        </div>

        <ResourceTable
          resource={api.commissions}
          columns={columns}
          params={params}
          refreshKey={refreshKey}
          searchable={false}
          filters={
            <>
              <Select
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                aria-label="الحالة"
                placeholder="كل الحالات"
                options={[
                  { value: 'pending', label: 'معلّقة' },
                  { value: 'settled', label: 'مستلمة' },
                ]}
              />
              {manage && (
                <div style={{ minWidth: '16rem' }}>
                  <MultiRelationSelect
                    resource={api.doctors}
                    value={doctors}
                    onChange={setDoctors}
                    placeholder="كل الأطباء — ابحث بالاسم أو الهاتف"
                    renderLabel={(row) => (row.phone1 ? `${row.name} · ${row.phone1}` : row.name)}
                  />
                </div>
              )}
              <RelationSelect
                resource={api.services}
                value={service}
                onChange={(value) => setService(value ?? '')}
                placeholder="كل الخدمات"
              />
              <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="من تاريخ" />
              <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label="إلى تاريخ" />
            </>
          }
          empty={{
            title: 'لا توجد نسب',
            message: 'تُحتسب النسبة تلقائياً عند استلام أي دفعة لحجز مع طبيب له نسبة في تعاقده.',
          }}
        />
      </div>
    </>
  )
}
