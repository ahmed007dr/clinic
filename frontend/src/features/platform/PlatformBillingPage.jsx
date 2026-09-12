import { Link } from 'react-router-dom'

import { api } from '@/api'
import { Badge, Card, CardBody, ErrorState, Loading, StatTile, Table } from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync } from '@/hooks/useApi'
import { formatDate, formatMoney } from '@/lib/format'

import { STATUS_TONES } from './PlatformTenantsPage'

/** Customers and balances: what each owner group was invoiced, paid and
 * still owes, with anything overdue or marked late up front. */
export function PlatformBillingPage() {
  const { data, loading, error, reload } = useAsync(() => api.platform.balances(), [])

  if (loading && !data) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const owing = data.items.filter((row) => Number(row.balance) > 0).length

  return (
    <>
      <PageHeader title="الاشتراكات والأرصدة" subtitle="فواتير المنصة لكل مجموعة، والمدفوع، والمتبقي" />
      <div className="ui-stack">
        <div className="ui-grid ui-grid--3">
          <StatTile label="إجمالي المفوتر" value={formatMoney(data.totals.invoiced)} />
          <StatTile label="إجمالي المحصّل" value={formatMoney(data.totals.paid)} />
          <StatTile label="المستحق" value={formatMoney(data.totals.balance)} hint={`${owing} مجموعة عليها رصيد`} />
        </div>
        <Card>
          <CardBody flush>
            <Table
              rows={data.items}
              rowKey={(row) => row.uuid}
              columns={[
                {
                  key: 'name', header: 'المجموعة',
                  render: (row) => <Link to={`/platform/tenants/${row.uuid}#billing`}>{row.name}</Link>,
                },
                {
                  key: 'status', header: 'الحالة',
                  render: (row) => <Badge tone={STATUS_TONES[row.status] ?? 'neutral'}>{row.status_label}</Badge>,
                },
                {
                  key: 'cycle', header: 'الدورة',
                  render: (row) => (row.cycle === 'yearly' ? 'سنوي' : 'شهري')
                    + (row.custom_price ? ` · ${formatMoney(row.custom_price)}` : ''),
                },
                { key: 'invoiced', header: 'المفوتر', numeric: true, render: (row) => formatMoney(row.invoiced) },
                { key: 'paid', header: 'المدفوع', numeric: true, render: (row) => formatMoney(row.paid) },
                {
                  key: 'balance', header: 'المتبقي', numeric: true,
                  render: (row) => <strong>{formatMoney(row.balance)}</strong>,
                },
                {
                  key: 'flags', header: '',
                  render: (row) => (
                    <div className="ui-row">
                      {row.overdue_invoices > 0 && <Badge tone="urgent">{row.overdue_invoices} متأخرة</Badge>}
                      {row.late && <Badge tone="warn" title={row.late.note}>متأخر السداد</Badge>}
                    </div>
                  ),
                },
                {
                  key: 'next_invoice_on', header: 'الفاتورة القادمة',
                  render: (row) => (row.next_invoice_on ? formatDate(row.next_invoice_on) : '—'),
                },
              ]}
            />
          </CardBody>
        </Card>
      </div>
    </>
  )
}
