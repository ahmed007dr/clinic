import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '@/api'
import { useAuth } from '@/hooks/useAuth'
import { Badge, Button, Card, CardBody, StatTile, Table } from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync } from '@/hooks/useApi'
import { formatDate, formatNumber } from '@/lib/format'

import { CreateTenantModal } from './CreateTenantModal'

export const STATUS_TONES = {
  trial: 'info',
  active: 'ok',
  suspended: 'urgent',
  cancelled: 'neutral',
}

/** Every clinic on the platform. */
export function PlatformTenantsPage() {
  const { platformUser } = useAuth()
  const canChange = platformUser?.role === 'super'
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)
  const { data, loading, error, reload } = useAsync(() => api.platform.tenants(), [])

  const totals = data?.totals
  const count = (status) => formatNumber(totals?.by_status?.[status] ?? 0)

  return (
    <>
      <PageHeader
        title="العيادات"
        subtitle="كل العيادات المشتركة في النظام"
        actions={
          // Support accounts are read-only (the server refuses them anyway).
          canChange && (
            <Button variant="primary" onClick={() => setCreating(true)}>
              عيادة جديدة
            </Button>
          )
        }
      />

      <div className="ui-stack">
        <div className="ui-grid ui-grid--3">
          <StatTile label="إجمالي العيادات" value={formatNumber(totals?.tenants ?? 0)} />
          <StatTile label="نشطة" value={count('active')} tone="ok" />
          <StatTile label="تجريبية" value={count('trial')} />
          <StatTile
            label="موقوفة"
            value={count('suspended')}
            tone={totals?.by_status?.suspended ? 'urgent' : 'neutral'}
          />
          <StatTile label="إجمالي المرضى" value={formatNumber(totals?.patients ?? 0)} />
        </div>

        <Card>
          <CardBody flush>
            <Table
              rows={data?.results ?? []}
              loading={loading}
              error={error}
              onRetry={reload}
              onRowClick={(row) => navigate(`/platform/tenants/${row.uuid}`)}
              empty={{ title: 'لا توجد عيادات', message: 'أضف أول عيادة من الزر أعلى الصفحة.' }}
              columns={[
                { key: 'name', header: 'العيادة' },
                { key: 'slug', header: 'المعرّف', render: (row) => <span dir="ltr">{row.slug}</span> },
                {
                  key: 'status',
                  header: 'الحالة',
                  render: (row) => (
                    <Badge tone={STATUS_TONES[row.status] ?? 'neutral'}>{row.status_label}</Badge>
                  ),
                },
                { key: 'plan', header: 'الباقة', render: (row) => row.plan?.name ?? '—' },
                { key: 'patients', header: 'المرضى', numeric: true },
                { key: 'staff', header: 'الموظفون', numeric: true },
                { key: 'branches', header: 'الفروع', numeric: true },
                {
                  key: 'trial_ends_on',
                  header: 'نهاية التجربة',
                  render: (row) => (row.trial_ends_on ? formatDate(row.trial_ends_on) : '—'),
                },
              ]}
            />
          </CardBody>
        </Card>
      </div>

      <CreateTenantModal
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={reload}
        statuses={data?.statuses ?? []}
      />
    </>
  )
}
