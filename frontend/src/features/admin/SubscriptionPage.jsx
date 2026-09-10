import { api } from '@/api'
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  DescriptionList,
  ErrorState,
  Loading,
  Table,
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync } from '@/hooks/useApi'
import { formatDate, formatMoney } from '@/lib/format'

import './subscription.css'

/**
 * The clinic's own plan: what it allows, how much is used, when it ends.
 *
 * Before this page a clinic learned its limits only by being refused, and the
 * refusal told it to upgrade a plan it had no way to look at. Read-only by
 * design — there is no payment gateway, so a button promising an upgrade would
 * be a button that cannot work.
 */
export function SubscriptionPage() {
  const { data, loading, error, reload } = useAsync(() => api.subscription.get(), [])

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const { plan, subscription, limits, features } = data

  return (
    <>
      <PageHeader title="الباقة والاشتراك" subtitle={data.clinic} />

      <div className="ui-stack">
        <div className="ui-grid ui-grid--2" style={{ alignItems: 'start' }}>
          <Card>
            <CardHeader
              title={plan ? plan.name : 'لا توجد باقة نشطة'}
              actions={
                subscription && (
                  <Badge tone={subscription.status === 'active' ? 'ok' : 'warn'}>
                    {subscription.status_label}
                  </Badge>
                )
              }
            />
            <CardBody>
              {plan ? (
                <DescriptionList
                  columns={1}
                  items={[
                    { label: 'السعر', value: `${formatMoney(plan.price)} / ${plan.billing_period}` },
                    { label: 'تاريخ البدء', value: formatDate(subscription?.started_on) },
                    {
                      label: 'نهاية الفترة التجريبية',
                      value: subscription?.trial_ends_on ? formatDate(subscription.trial_ends_on) : null,
                    },
                    {
                      label: 'تاريخ الانتهاء',
                      value: subscription?.ends_on ? formatDate(subscription.ends_on) : 'مستمر',
                    },
                    { label: 'حالة العيادة', value: data.clinic_status_label },
                  ]}
                />
              ) : (
                <p className="ui-muted" style={{ margin: 0 }}>
                  لا يمكن إضافة سجلات جديدة بدون باقة نشطة. تواصل مع الدعم.
                </p>
              )}
              <p className="ui-muted" style={{ marginTop: 'var(--s4)', fontSize: 'var(--text-sm)' }}>
                لترقية الباقة أو تجديدها تواصل معنا — الدفع يتم خارج النظام حالياً.
              </p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="المزايا" />
            <CardBody>
              <ul className="subscription__features">
                {features.map((feature) => (
                  <li key={feature.key}>
                    {!feature.available ? (
                      <Badge tone="info">قريباً</Badge>
                    ) : (
                      <Badge tone={feature.enabled ? 'ok' : 'neutral'}>
                        {feature.enabled ? 'مفعّلة' : 'غير متاحة في باقتك'}
                      </Badge>
                    )}{' '}
                    {feature.label}
                  </li>
                ))}
              </ul>
            </CardBody>
          </Card>
        </div>

        <Card>
          <CardHeader title="الاستهلاك" subtitle="المستخدم مقابل المسموح في باقتك" />
          <CardBody flush>
            <Table
              rowKey={(row) => row.key}
              rows={limits}
              columns={[
                { key: 'label_ar', header: 'البند' },
                { key: 'used', header: 'المستخدم', numeric: true, render: (row) => row.used ?? '—' },
                {
                  key: 'allowed',
                  header: 'المسموح',
                  numeric: true,
                  render: (row) => (row.unlimited ? 'غير محدود' : row.allowed),
                },
                {
                  key: 'state',
                  header: 'الحالة',
                  render: (row) =>
                    row.over ? (
                      <Badge tone="urgent">تجاوز الحد</Badge>
                    ) : !row.unlimited && row.used >= row.allowed ? (
                      <Badge tone="warn">وصل للحد</Badge>
                    ) : (
                      <Badge tone="ok">متاح</Badge>
                    ),
                },
              ]}
            />
          </CardBody>
        </Card>
      </div>
    </>
  )
}
