import { api } from '@/api'
import { Badge, Card, CardBody, CardHeader, Table } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { formatDateTime, formatRelative } from '@/lib/format'

/** One group's clinics (doctors, employees, accounts, online) and every
 * account with its role and last activity. */
export function TenantPeople({ tenant }) {
  const { data, loading, error, reload } = useAsync(() => api.platform.people(tenant), [tenant])

  return (
    <>
      <Card>
        <CardHeader title="العيادات" subtitle="الأطباء والموظفون والحسابات لكل عيادة" />
        <CardBody flush>
          <Table
            columns={[
              { key: 'name', header: 'العيادة', render: (row) => (
                <>
                  {row.name} {!row.is_active && <Badge tone="neutral">موقوفة</Badge>}
                </>
              ) },
              { key: 'doctors', header: 'أطباء', numeric: true },
              { key: 'employees', header: 'موظفون', numeric: true },
              { key: 'accounts', header: 'حسابات', numeric: true },
              { key: 'online', header: 'أونلاين', numeric: true,
                render: (row) => (row.online ? <Badge tone="ok">{row.online}</Badge> : 0) },
            ]}
            rows={data?.branches ?? []}
            loading={loading}
            error={error}
            onRetry={reload}
            empty={{ title: 'لا توجد عيادات' }}
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="الحسابات" subtitle="آخر نشاط وآخر دخول لكل حساب" />
        <CardBody flush>
          <Table
            columns={[
              { key: 'username', header: 'الحساب', render: (row) => (
                <>
                  <strong>{row.username}</strong>
                  <div className="ui-muted" dir="ltr">{row.email}</div>
                </>
              ) },
              { key: 'role', header: 'الدور', render: (row) => row.role ?? '—' },
              { key: 'branch', header: 'العيادة', render: (row) => row.branch ?? '—' },
              {
                key: 'status',
                header: 'الحالة',
                render: (row) =>
                  !row.is_active ? <Badge tone="neutral">موقوف</Badge>
                    : row.online ? <Badge tone="ok">أونلاين</Badge> : <Badge tone="neutral">غير متصل</Badge>,
              },
              { key: 'last_seen_at', header: 'آخر نشاط',
                render: (row) => (row.last_seen_at ? formatRelative(row.last_seen_at) : 'لم يظهر بعد') },
              { key: 'last_login', header: 'آخر دخول',
                render: (row) => (row.last_login ? formatDateTime(row.last_login) : '—') },
            ]}
            rows={data?.accounts ?? []}
            loading={loading}
            empty={{ title: 'لا توجد حسابات' }}
          />
        </CardBody>
      </Card>
    </>
  )
}
