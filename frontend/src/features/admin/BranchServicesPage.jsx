import { useState } from 'react'

import { api } from '@/api'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge, Card, CardBody, Select, Table } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { formatMoney } from '@/lib/format'

const PRICE_LABEL = {
  fixed: 'سعر ثابت',
  starting_from: 'يبدأ من',
  after_evaluation: 'بعد التقييم',
}

/**
 * Which services this clinic offers (docs/15, D9) — management's switch.
 *
 * A service is defined once for the group (Services). Here each clinic says
 * whether it offers it, and whether it can be booked from the website. That is
 * separate from the doctors' contracts: turning a service on does not put a
 * doctor under contract for it, and a contract alone does not make the clinic
 * offer it. To appear on the public page the service also needs at least one
 * doctor under contract at this clinic who is shown publicly and has a valid
 * price — the «أطباء جاهزون» column says how many there are.
 *
 * The Owner picks any clinic; an Admin sees their own.
 */
export function BranchServicesPage() {
  const toast = useToast()
  const [branch, setBranch] = useState('')
  const [busy, setBusy] = useState('')
  const { data, loading, error, reload } = useAsync(() => api.branchServices.get(branch || undefined), [branch])

  const change = async (row, patch, done) => {
    setBusy(row.uuid)
    try {
      await api.branchServices.set({ branch: data.branch.uuid, service: row.uuid, ...patch })
      toast.success(done)
      reload()
    } catch (caught) {
      toast.error(caught.message)
    } finally {
      setBusy('')
    }
  }

  const columns = [
    { key: 'name', header: 'الخدمة', render: (row) => <strong>{row.name}</strong> },
    { key: 'specialization', header: 'التخصص', render: (row) => row.specialization || '—' },
    {
      key: 'base_price',
      header: 'السعر',
      numeric: true,
      render: (row) => (
        <>
          {formatMoney(row.base_price)}
          <div className="ui-muted">{PRICE_LABEL[row.price_display]}</div>
        </>
      ),
    },
    { key: 'duration_minutes', header: 'المدة', numeric: true, render: (row) => `${row.duration_minutes} د` },
    {
      key: 'doctors_ready',
      header: 'أطباء جاهزون',
      numeric: true,
      render: (row) =>
        row.doctors_ready > 0 ? (
          <Badge tone="ok">{row.doctors_ready}</Badge>
        ) : (
          <Badge tone="warn" title="لا يوجد طبيب متعاقد ظاهر للعامة بسعر صالح">لا أحد</Badge>
        ),
    },
    {
      key: 'enabled',
      header: 'تقدّمها العيادة',
      render: (row) => (
        <input
          type="checkbox"
          aria-label={`تفعيل ${row.name}`}
          checked={row.enabled}
          disabled={busy === row.uuid || !row.service_active}
          onChange={(event) =>
            change(row, { enabled: event.target.checked }, event.target.checked ? 'تم تفعيل الخدمة.' : 'تم إيقاف الخدمة في هذه العيادة.')
          }
        />
      ),
    },
    {
      key: 'online_bookable',
      header: 'حجز إلكتروني',
      render: (row) => (
        <input
          type="checkbox"
          aria-label={`حجز إلكتروني ${row.name}`}
          checked={row.online_bookable}
          disabled={busy === row.uuid || !row.enabled}
          onChange={(event) => change(row, { online_bookable: event.target.checked }, 'تم الحفظ.')}
        />
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="الخدمات في العيادات"
        subtitle="حدّد ما تقدّمه كل عيادة وما يمكن حجزه من الموقع. التعاقد مع الأطباء منفصل عن هذه الشاشة."
        back={{ to: '/services', label: 'الخدمات' }}
      />
      {data?.branches?.length > 1 && (
        <Card>
          <CardBody>
            <Select
              label="العيادة"
              value={data.branch?.uuid ?? ''}
              options={data.branches.map((b) => ({ value: b.uuid, label: b.name }))}
              onChange={(event) => setBranch(event.target.value)}
            />
          </CardBody>
        </Card>
      )}
      <Table
        columns={columns}
        rows={data?.services ?? []}
        loading={loading}
        error={error}
        onRetry={reload}
        empty={{ title: 'لا خدمات', message: 'أضف الخدمات أولاً من شاشة الخدمات.' }}
      />
    </>
  )
}
