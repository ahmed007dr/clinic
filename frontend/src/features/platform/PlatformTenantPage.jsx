import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { api } from '@/api'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  ErrorState,
  Loading,
  Select,
  StatTile,
  Table,
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { formatDate, formatMoney, formatNumber } from '@/lib/format'

import { STATUS_TONES } from './PlatformTenantsPage'

const STATUSES = [
  { value: 'trial', label: 'تجريبي' },
  { value: 'active', label: 'نشط' },
  { value: 'suspended', label: 'موقوف' },
  { value: 'cancelled', label: 'ملغي' },
]

/**
 * One clinic, as the platform sees it: read-only figures, plus the two things
 * the platform may change — the clinic's status and its plan.
 *
 * Opening this page is recorded in the clinic's own audit trail. That is
 * deliberate and stated on the page: an operator looking at a customer's data
 * is the act worth recording.
 */
export function PlatformTenantPage() {
  const { platformUser } = useAuth()
  // Support accounts are read-only (the server refuses them anyway).
  const canChange = platformUser?.role === 'super'
  const { uuid } = useParams()
  const toast = useToast()
  const { data, loading, error, reload } = useAsync(() => api.platform.tenant(uuid), [uuid])
  const plans = useAsync(() => api.platform.plans(), [])
  const [status, setStatus] = useState('')
  const [plan, setPlan] = useState('')
  const [confirm, setConfirm] = useState(null) // 'status' | 'plan'

  useEffect(() => {
    if (data) {
      setStatus(data.status)
      setPlan(data.plan?.code ?? '')
    }
  }, [data])

  const change = useMutation((kind) =>
    kind === 'status' ? api.platform.setStatus(uuid, status) : api.platform.setPlan(uuid, plan),
  )

  if (loading && !data) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const apply = async () => {
    try {
      await change.run(confirm)
      toast.success(confirm === 'status' ? 'تم تغيير حالة العيادة' : 'تم تغيير الباقة')
      reload()
    } catch (caught) {
      toast.error(caught.message)
    } finally {
      setConfirm(null)
    }
  }

  const suspending = confirm === 'status' && status === 'suspended'

  return (
    <>
      <PageHeader
        title={data.name}
        subtitle={`${data.slug} · منذ ${formatDate(data.created_at)}`}
        back={{ to: '/platform', label: 'رجوع للعيادات' }}
        actions={<Badge tone={STATUS_TONES[data.status] ?? 'neutral'}>{data.status_label}</Badge>}
      />

      <p className="ui-muted" style={{ fontSize: 'var(--text-sm)', marginTop: 'calc(-1 * var(--s3))' }}>
        فتح هذه الصفحة يُسجَّل في سجل تدقيق العيادة. البيانات الطبية للعرض فقط.
      </p>

      <div className="ui-stack">
        <div className="ui-grid ui-grid--3">
          <StatTile label="المرضى" value={formatNumber(data.patients)} />
          <StatTile label="المواعيد" value={formatNumber(data.snapshot.appointments)} />
          <StatTile label="الزيارات" value={formatNumber(data.snapshot.visits)} />
          <StatTile label="الإيراد المسجل" value={formatMoney(data.snapshot.revenue)} />
        </div>

        <div className="ui-grid ui-grid--2" style={{ alignItems: 'start' }}>
          <Card>
            <CardHeader title="حالة العيادة" subtitle="الإيقاف يمنع موظفي العيادة فوراً، حتى من هم داخل النظام الآن" />
            <CardBody>
              <div className="ui-row" style={{ alignItems: 'flex-end' }}>
                <div style={{ flex: 1 }}>
                  <Select label="الحالة" options={STATUSES} value={status}
                    onChange={(event) => setStatus(event.target.value)} />
                </div>
                <Button onClick={() => setConfirm('status')} disabled={!canChange || status === data.status}>
                  تطبيق
                </Button>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="الباقة" subtitle={data.plan ? `الحالية: ${data.plan.name}` : 'لا توجد باقة'} />
            <CardBody>
              <div className="ui-row" style={{ alignItems: 'flex-end' }}>
                <div style={{ flex: 1 }}>
                  <Select
                    label="الباقة"
                    placeholder={plans.loading ? 'جارٍ التحميل…' : undefined}
                    options={(plans.data ?? []).map((p) => ({
                      value: p.code,
                      label: `${p.name} — ${formatMoney(p.price)} / ${p.billing_period}`,
                    }))}
                    value={plan}
                    onChange={(event) => setPlan(event.target.value)}
                  />
                </div>
                <Button onClick={() => setConfirm('plan')} disabled={!canChange || !plan || plan === data.plan?.code}>
                  تطبيق
                </Button>
              </div>
            </CardBody>
          </Card>
        </div>

        <Card>
          <CardHeader title="الاستهلاك مقابل الباقة" />
          <CardBody flush>
            <Table
              rows={data.limits}
              rowKey={(row) => row.key}
              columns={[
                { key: 'label_ar', header: 'البند' },
                { key: 'used', header: 'المستخدم', numeric: true },
                {
                  key: 'allowed', header: 'المسموح', numeric: true,
                  render: (row) => (row.unlimited ? 'غير محدود' : row.allowed),
                },
                {
                  key: 'over', header: '',
                  render: (row) => (row.over ? <Badge tone="urgent">تجاوز</Badge> : null),
                },
              ]}
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="سجل الاشتراكات" />
          <CardBody flush>
            <Table
              rows={data.history}
              rowKey={(row) => `${row.plan}-${row.started_on}`}
              empty={{ title: 'لا يوجد سجل' }}
              columns={[
                { key: 'plan', header: 'الباقة' },
                { key: 'status', header: 'الحالة' },
                { key: 'started_on', header: 'البدء', render: (row) => formatDate(row.started_on) },
                { key: 'ends_on', header: 'الانتهاء', render: (row) => (row.ends_on ? formatDate(row.ends_on) : '—') },
              ]}
            />
          </CardBody>
        </Card>
      </div>

      <ConfirmDialog
        open={Boolean(confirm)}
        onClose={() => setConfirm(null)}
        onConfirm={apply}
        loading={change.submitting}
        tone={suspending ? 'danger' : 'primary'}
        title={confirm === 'status' ? 'تغيير حالة العيادة' : 'تغيير الباقة'}
        message={
          suspending
            ? `إيقاف «${data.name}» يمنع كل موظفيها من استخدام النظام فوراً. متابعة؟`
            : confirm === 'status'
              ? `تغيير حالة «${data.name}»؟`
              : `نقل «${data.name}» إلى الباقة المختارة؟ تُطبَّق حدودها فوراً.`
        }
        confirmLabel={suspending ? 'إيقاف العيادة' : 'تطبيق'}
      />
    </>
  )
}
