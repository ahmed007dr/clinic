import { useEffect } from 'react'
import { Link } from 'react-router-dom'

import { api } from '@/api'
import { Badge, Card, CardBody, Table } from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync } from '@/hooks/useApi'
import { formatRelative } from '@/lib/format'

/** Everyone active in the last five minutes, across every group. Refreshes
 * itself every half minute. */
export function PlatformOnlinePage() {
  const { data, loading, error, reload } = useAsync(() => api.platform.online(), [])

  useEffect(() => {
    const timer = setInterval(reload, 30000)
    return () => clearInterval(timer)
  }, [reload])

  return (
    <>
      <PageHeader title="أونلاين الآن" subtitle="الحسابات النشطة خلال آخر ٥ دقائق · تتحدث تلقائياً" />
      <Card>
        <CardBody flush>
          <Table
            columns={[
              { key: 'username', header: 'الحساب', render: (row) => (
                <>
                  <strong>{row.username}</strong>
                  <div className="ui-muted" dir="ltr">{row.email}</div>
                </>
              ) },
              {
                key: 'group',
                header: 'المجموعة',
                render: (row) =>
                  row.platform ? <Badge tone="primary">المنصة</Badge>
                    : <Link to={`/platform/tenants/${row.group_uuid}`}>{row.group}</Link>,
              },
              { key: 'branch', header: 'العيادة', render: (row) => row.branch ?? '—' },
              { key: 'role', header: 'الدور', render: (row) => row.role ?? '—' },
              { key: 'last_seen_at', header: 'آخر نشاط', render: (row) => formatRelative(row.last_seen_at) },
            ]}
            rows={data ?? []}
            loading={loading}
            error={error}
            onRetry={reload}
            empty={{ title: 'لا أحد أونلاين الآن' }}
          />
        </CardBody>
      </Card>
    </>
  )
}
