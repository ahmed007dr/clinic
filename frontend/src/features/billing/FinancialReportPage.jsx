import { useState } from 'react'

import { api } from '@/api'
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  ErrorState,
  Input,
  Loading,
  StatTile,
  Table,
} from '@/components/ui'
import { RelationSelect } from '@/components/data/RelationSelect'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { formatMoney, formatNumber, startOfMonth, today } from '@/lib/format'

/**
 * Revenue against expenses for a period.
 *
 * Defaults to the current month, because that is the question actually being
 * asked when someone opens this. The figures are whatever the caller is
 * entitled to see — the server scopes them — so a receptionist opening this
 * gets their branch's takings rather than a refusal.
 */
export function FinancialReportPage() {
  const { permissions } = useAuth()
  const [from, setFrom] = useState(startOfMonth())
  const [to, setTo] = useState(today())
  const [branch, setBranch] = useState('')

  const { data, loading, error, reload } = useAsync(
    () => api.financialReport.get({ from, to, branch }),
    [from, to, branch],
  )

  return (
    <>
      <PageHeader
        title="التقرير المالي"
        subtitle={permissions.all_branches ? 'كل الفروع' : 'فرعك'}
      />

      <div className="ui-stack">
        <Card>
          <CardBody>
            <div className="ui-row" style={{ flexWrap: 'wrap', gap: 'var(--s4)' }}>
              <Input
                label="من"
                type="date"
                value={from}
                onChange={(event) => setFrom(event.target.value)}
              />
              <Input
                label="إلى"
                type="date"
                value={to}
                onChange={(event) => setTo(event.target.value)}
              />
              {permissions.all_branches && (
                <div style={{ minWidth: '12rem' }}>
                  <RelationSelect
                    label="الفرع"
                    resource={api.branches}
                    value={branch}
                    onChange={(value) => setBranch(value ?? '')}
                    placeholder="كل الفروع"
                  />
                </div>
              )}
              <Button variant="ghost" onClick={reload} loading={loading}>
                تحديث
              </Button>
            </div>
          </CardBody>
        </Card>

        {loading && !data && <Loading />}
        {error && <ErrorState error={error} onRetry={reload} />}

        {data && (
          <>
            <div className="ui-grid ui-grid--3">
              <StatTile
                label="الإيراد"
                value={formatMoney(data.revenue)}
                hint={`${formatNumber(data.revenue_count)} دفعة`}
                tone="ok"
              />
              <StatTile
                label="المصروفات"
                value={formatMoney(data.expenses)}
                hint={`${formatNumber(data.expenses_count)} بند`}
              />
              <StatTile
                label="الصافي"
                value={formatMoney(data.net)}
                tone={data.net >= 0 ? 'ok' : 'urgent'}
              />
            </div>

            <div className="ui-grid ui-grid--2">
              <Card>
                <CardHeader title="الإيراد حسب طريقة الدفع" />
                <CardBody flush>
                  <Table
                    columns={[
                      { key: 'name', header: 'الطريقة' },
                      {
                        key: 'count',
                        header: 'العدد',
                        numeric: true,
                        render: (row) => formatNumber(row.count),
                      },
                      {
                        key: 'total',
                        header: 'الإجمالي',
                        numeric: true,
                        render: (row) => formatMoney(row.total),
                      },
                    ]}
                    rows={data.by_method}
                    empty={{ title: 'لا توجد دفعات في هذه الفترة' }}
                  />
                </CardBody>
              </Card>

              <Card>
                <CardHeader title="المصروفات حسب البند" />
                <CardBody flush>
                  <Table
                    columns={[
                      { key: 'name', header: 'البند' },
                      {
                        key: 'count',
                        header: 'العدد',
                        numeric: true,
                        render: (row) => formatNumber(row.count),
                      },
                      {
                        key: 'total',
                        header: 'الإجمالي',
                        numeric: true,
                        render: (row) => formatMoney(row.total),
                      },
                    ]}
                    rows={data.by_category}
                    empty={{ title: 'لا توجد مصروفات في هذه الفترة' }}
                  />
                </CardBody>
              </Card>
            </div>

            {data.by_branch?.length > 0 && (
              <Card>
                <CardHeader title="حسب الفرع" />
                <CardBody flush>
                  <Table
                    columns={[
                      { key: 'name', header: 'الفرع' },
                      {
                        key: 'revenue',
                        header: 'الإيراد',
                        numeric: true,
                        render: (row) => formatMoney(row.revenue),
                      },
                      {
                        key: 'expenses',
                        header: 'المصروفات',
                        numeric: true,
                        render: (row) => formatMoney(row.expenses),
                      },
                      {
                        key: 'net',
                        header: 'الصافي',
                        numeric: true,
                        render: (row) => (
                          <strong
                            style={{
                              color: row.net >= 0 ? 'var(--ok)' : 'var(--urgent)',
                            }}
                          >
                            {formatMoney(row.net)}
                          </strong>
                        ),
                      },
                    ]}
                    rows={data.by_branch}
                    rowKey={(row) => row.uuid}
                    empty={{ title: 'لا توجد فروع' }}
                  />
                </CardBody>
              </Card>
            )}
          </>
        )}
      </div>
    </>
  )
}
