import { useNavigate } from 'react-router-dom'

import { api } from '@/api'
import { Badge, Card, CardBody, ErrorState, Loading, StatTile, Table } from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync } from '@/hooks/useApi'
import { formatNumber, formatRelative } from '@/lib/format'

import { STATUS_TONES } from './PlatformTenantsPage'

/**
 * The developer's first screen: every owner group at a glance — its people,
 * who is online, when it was last used, and anything that needs a look
 * (near or over a plan limit, nobody active for a week).
 * platform_admin/monitoring.py assembles it; only counts and accounts.
 */
export function PlatformOverviewPage() {
  const navigate = useNavigate()
  const { data, loading, error, reload } = useAsync(() => api.platform.overview(), [])

  if (loading && !data) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const { totals, groups } = data

  return (
    <>
      <PageHeader title="نظرة عامة" subtitle="كل المجموعات والعيادات والحسابات على المنصة" />
      <div className="ui-stack">
        <div className="ui-grid">
          <StatTile label="المجموعات" value={formatNumber(totals.groups)}
            hint={`${formatNumber(totals.by_status.active ?? 0)} نشطة · ${formatNumber(totals.by_status.trial ?? 0)} تجريبية`} />
          <StatTile label="العيادات (الفروع)" value={formatNumber(totals.branches)} />
          <StatTile label="الأطباء" value={formatNumber(totals.doctors)}
            hint={`${formatNumber(totals.employees)} موظف إجمالاً`} />
          <StatTile label="المرضى" value={formatNumber(totals.patients)} />
          <StatTile label="أونلاين الآن" value={formatNumber(totals.online)} tone="primary"
            hint={`${formatNumber(totals.active_today)} نشط آخر ٢٤ ساعة`} to="/platform/online" />
          <StatTile label="تحتاج متابعة" value={formatNumber(totals.inactive_groups + totals.near_limit_groups)}
            tone={totals.inactive_groups + totals.near_limit_groups ? 'urgent' : 'ok'}
            hint={`${formatNumber(totals.inactive_groups)} غير نشطة · ${formatNumber(totals.near_limit_groups)} عند حد الباقة`} />
        </div>

        <Card>
          <CardBody flush>
            <Table
              columns={[
                {
                  key: 'name',
                  header: 'المجموعة',
                  render: (row) => (
                    <>
                      <strong>{row.name}</strong>
                      <div className="ui-muted">{row.owners.map((o) => o.email).join('، ') || 'بلا أونر'}</div>
                    </>
                  ),
                },
                {
                  key: 'status',
                  header: 'الحالة',
                  render: (row) => (
                    <>
                      <Badge tone={STATUS_TONES[row.status] ?? 'neutral'}>{row.status_label}</Badge>
                      <div className="ui-muted">{row.plan ?? '—'}</div>
                    </>
                  ),
                },
                { key: 'branches', header: 'عيادات', numeric: true },
                { key: 'doctors', header: 'أطباء', numeric: true },
                { key: 'employees', header: 'موظفون', numeric: true },
                { key: 'patients', header: 'مرضى', numeric: true, render: (row) => formatNumber(row.patients) },
                {
                  key: 'online',
                  header: 'أونلاين',
                  numeric: true,
                  render: (row) =>
                    row.online ? <Badge tone="ok">{row.online} / {row.accounts}</Badge> : `0 / ${row.accounts}`,
                },
                {
                  key: 'last_seen_at',
                  header: 'آخر نشاط',
                  render: (row) => (row.last_seen_at ? formatRelative(row.last_seen_at) : 'لم يدخل أحد'),
                },
                {
                  key: 'flags',
                  header: 'تنبيهات',
                  render: (row) => (
                    <div className="ui-row" style={{ flexWrap: 'wrap', gap: 4 }}>
                      {row.inactive && <Badge tone="warn">غير نشطة</Badge>}
                      {row.over_limits.map((label) => <Badge key={label} tone="urgent">تجاوز: {label}</Badge>)}
                      {row.near_limits.map((label) => <Badge key={label} tone="warn">قرب حد: {label}</Badge>)}
                    </div>
                  ),
                },
              ]}
              rows={groups}
              onRowClick={(row) => navigate(`/platform/tenants/${row.uuid}`)}
              empty={{ title: 'لا توجد مجموعات بعد' }}
            />
          </CardBody>
        </Card>
      </div>
    </>
  )
}
