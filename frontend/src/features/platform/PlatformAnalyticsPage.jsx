import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '@/api'
import { Badge, BarChart, Card, CardBody, CardHeader, ErrorState, Loading, Select, StatTile, Table } from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync } from '@/hooks/useApi'
import { formatMoney, formatNumber } from '@/lib/format'

import { STATUS_TONES } from './PlatformTenantsPage'

const MONTHS = new Intl.DateTimeFormat('ar-EG', { month: 'short', year: '2-digit' })

function points(series) {
  return (series ?? []).map((row) => ({ label: MONTHS.format(new Date(row.month)), value: Number(row.value) }))
}

/** The platform's own business (recurring revenue, invoices, collections,
 * signups, groups won and lost) and what the groups do this month. */
export function PlatformAnalyticsPage() {
  const [months, setMonths] = useState('12')
  const { data, loading, error, reload } = useAsync(() => api.platform.analytics({ months }), [months])

  if (loading && !data) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />
  const t = data.totals

  return (
    <>
      <PageHeader
        title="التحليلات"
        subtitle="إيرادات المنصة ونمو المجموعات ونشاطها"
        actions={
          <Select id="analytics-months" value={months} onChange={(e) => setMonths(e.target.value)}
            options={[{ value: '6', label: 'آخر 6 أشهر' }, { value: '12', label: 'آخر 12 شهراً' },
              { value: '24', label: 'آخر 24 شهراً' }]} />
        }
      />
      <div className="ui-stack">
        <div className="ui-grid ui-grid--3">
          <StatTile label="الإيراد الشهري المتكرر (MRR)" value={formatMoney(t.mrr)} hint={`سنوياً ${formatMoney(t.arr)}`} />
          <StatTile label="المحصّل" value={formatMoney(t.collected)} hint={`من ${formatMoney(t.invoiced)} مفوتر`} />
          <StatTile label="المستحق" value={formatMoney(t.outstanding)}
            tone={t.overdue_invoices ? 'warn' : 'neutral'} hint={`${t.overdue_invoices} فاتورة متأخرة`} />
          <StatTile label="المجموعات" value={formatNumber(t.groups)}
            hint={`${t.active_groups} نشطة · ${t.trial_groups} تجريبية · ${t.lost_groups} موقوفة/ملغاة`} />
          <StatTile label="طلبات جديدة" value={formatNumber(t.signups_pending)} to="/platform/signups"
            hint={t.conversion_percent === null ? 'لا طلبات معالجة' : `نسبة القبول ${t.conversion_percent}%`} />
          <StatTile label="الحسابات النشطة" value={formatNumber(t.active_7_days)}
            hint={`خلال 7 أيام · ${t.active_30_days} خلال 30 يوماً من ${t.accounts}`} />
          <StatTile label="مواعيد العيادات هذا الشهر" value={formatNumber(t.appointments_this_month)} />
          <StatTile label="إيراد العيادات هذا الشهر" value={formatMoney(t.clinic_revenue_this_month)}
            hint={`خصومات ممنوحة ${formatMoney(t.discounts_given)}`} />
        </div>

        <div className="ui-grid ui-grid--2" style={{ alignItems: 'start' }}>
          <Card>
            <CardHeader title="المحصّل شهرياً" />
            <CardBody><BarChart data={points(data.series.collected)} format="money" /></CardBody>
          </Card>
          <Card>
            <CardHeader title="المفوتر شهرياً" />
            <CardBody><BarChart data={points(data.series.invoiced)} format="money" /></CardBody>
          </Card>
          <Card>
            <CardHeader title="مجموعات جديدة" />
            <CardBody><BarChart data={points(data.series.new_groups)} /></CardBody>
          </Card>
          <Card>
            <CardHeader title="طلبات التسجيل" />
            <CardBody><BarChart data={points(data.series.signups)} /></CardBody>
          </Card>
          <Card>
            <CardHeader title="مجموعات أُوقفت أو أُلغيت" />
            <CardBody><BarChart data={points(data.series.lost_groups)} emptyMessage="لم تُفقد مجموعات في هذه الفترة" /></CardBody>
          </Card>
          <Card>
            <CardHeader title="المجموعات حسب الباقة" />
            <CardBody>
              <BarChart data={data.by_plan.map((row) => ({ label: row.plan, value: row.groups }))} />
            </CardBody>
          </Card>
        </div>

        <Card>
          <CardHeader title="المجموعات هذا الشهر" subtitle="مرتبة بإيراد العيادات" />
          <CardBody flush>
            <Table
              rows={data.groups}
              rowKey={(row) => row.uuid}
              columns={[
                { key: 'name', header: 'المجموعة', render: (row) => <Link to={`/platform/tenants/${row.uuid}`}>{row.name}</Link> },
                { key: 'status', header: 'الحالة',
                  render: (row) => <Badge tone={STATUS_TONES[row.status] ?? 'neutral'}>{row.status_label}</Badge> },
                { key: 'plan', header: 'الباقة' },
                { key: 'monthly_value', header: 'قيمتها للمنصة شهرياً', numeric: true,
                  render: (row) => (row.monthly_value ? formatMoney(row.monthly_value) : '—') },
                { key: 'appointments_this_month', header: 'المواعيد', numeric: true },
                { key: 'revenue_this_month', header: 'إيراد العيادات', numeric: true,
                  render: (row) => formatMoney(row.revenue_this_month) },
              ]}
            />
          </CardBody>
        </Card>
      </div>
    </>
  )
}
