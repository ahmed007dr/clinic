import { Link } from 'react-router-dom'

import { api } from '@/api'
import {
  BarChart,
  Badge,
  Card,
  CardBody,
  CardHeader,
  ErrorState,
  Loading,
  StatTile,
  Table,
  APPOINTMENT_TONES,
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { formatDate, formatMoney, formatNumber, formatTime } from '@/lib/format'

import './dashboard.css'

/**
 * The landing screen.
 *
 * Ordered by what someone opening it needs to act on, not by what is easiest
 * to count: the queue first, then today's money, then anything clinical that
 * is waiting on a person. Every figure comes from one request — the server
 * assembles them, already scoped to whatever the caller may see.
 */
export function DashboardPage() {
  const { user, permissions } = useAuth()
  const { data, loading, error, reload } = useAsync(() => api.dashboard.get(), [])
  const queue = useAsync(() => api.appointments.waiting(), [])

  if (loading && !data) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const revenueSeries = (data?.revenue_series ?? []).map((point) => ({
    // The day of the month only: fourteen full dates do not fit across a
    // card, and the chart's own caption already says which fortnight it is.
    label: String(new Date(point.date).getDate()),
    value: point.total,
  }))

  return (
    <>
      <PageHeader
        title={`أهلاً، ${user?.username ?? ''}`}
        subtitle={`${formatDate(data?.today)}${user?.branch ? ` · ${user.branch.name}` : ''}`}
      />

      <div className="ui-stack">
        <div className="ui-grid dashboard__tiles">
          <StatTile
            label="في الانتظار الآن"
            value={formatNumber(data?.appointments?.waiting)}
            hint="مرضى بالعيادة"
            tone={data?.appointments?.waiting > 0 ? 'primary' : 'neutral'}
            to="/queue"
            icon="⏳"
          />
          <StatTile
            label="مواعيد اليوم"
            value={formatNumber(data?.appointments?.today)}
            hint={`${formatNumber(data?.appointments?.upcoming)} خلال الأسبوع`}
            to="/appointments"
            icon="📅"
          />
          <StatTile
            label="إيراد اليوم"
            value={formatMoney(data?.revenue?.today)}
            hint={`الشهر: ${formatMoney(data?.revenue?.month)}`}
            to="/payments"
            icon="💵"
          />
          <StatTile
            label="إجمالي المرضى"
            value={formatNumber(data?.patients?.total)}
            hint={`${formatNumber(data?.patients?.new_this_month)} هذا الشهر`}
            to="/patients"
            icon="👤"
          />

          {permissions.view_clinical && data?.clinical && (
            <>
              <StatTile
                label="زيارات اليوم"
                value={formatNumber(data.clinical.visits_today)}
                to="/visits"
                icon="🩺"
              />
              {/* The one figure on this screen that asks someone to do
                  something. It gets the urgent treatment only when it is
                  non-zero — a permanent red tile stops being read. */}
              <StatTile
                label="تحاليل غير مُطّلع عليها"
                value={formatNumber(data.clinical.unacknowledged_labs)}
                hint={
                  data.clinical.unacknowledged_labs > 0
                    ? 'نتائج غير طبيعية بانتظار المراجعة'
                    : 'لا شيء بانتظار المراجعة'
                }
                tone={data.clinical.unacknowledged_labs > 0 ? 'urgent' : 'ok'}
                to="/lab-results?unacknowledged=1"
                icon="🧪"
              />
            </>
          )}

          {permissions.is_admin && data?.expenses && (
            <StatTile
              label="صافي الشهر"
              value={formatMoney(data.revenue.net_month)}
              hint={`مصروفات: ${formatMoney(data.expenses.month)}`}
              tone={data.revenue.net_month >= 0 ? 'ok' : 'urgent'}
              to="/reports/financial"
              icon="📊"
            />
          )}
        </div>

        <div className="dashboard__split">
          <Card>
            <CardHeader
              title="قائمة الانتظار"
              subtitle="بترتيب الوصول"
              actions={<Link to="/queue">عرض الكل</Link>}
            />
            <CardBody flush>
              <Table
                columns={[
                  {
                    key: 'time',
                    header: 'الوقت',
                    render: (row) => formatTime(row.scheduled_date),
                  },
                  { key: 'patient_name', header: 'المريض' },
                  {
                    key: 'doctor_name',
                    header: 'الطبيب',
                    render: (row) => row.doctor_name || '—',
                  },
                  {
                    key: 'status',
                    header: 'الحالة',
                    render: (row) => (
                      <Badge tone={APPOINTMENT_TONES[row.status] ?? 'neutral'}>
                        {row.status_label}
                      </Badge>
                    ),
                  },
                ]}
                rows={(queue.data ?? []).slice(0, 8)}
                loading={queue.loading}
                error={queue.error}
                onRetry={queue.reload}
                empty={{
                  title: 'لا أحد في الانتظار',
                  message: 'ستظهر هنا حجوزات اليوم فور تسجيل وصول المريض.',
                }}
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="الإيراد" subtitle="آخر ١٤ يوماً" />
            <CardBody>
              <BarChart data={revenueSeries} format="money" height={180} />
            </CardBody>
          </Card>
        </div>
      </div>
    </>
  )
}
