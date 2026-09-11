import { useEffect, useState } from 'react'

import { api } from '@/api'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Input,
  Select,
  Table,
} from '@/components/ui'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { formatDate, formatDateTime } from '@/lib/format'

/**
 * The group's settings the developer controls: its name and patient-portal
 * link, the services it may use and its limits beyond the plan, the
 * subscription's status and dates, and the history of support sign-ins.
 */
export function TenantControl({ tenant, summary, onChanged }) {
  const { platformUser } = useAuth()
  const canChange = platformUser?.role === 'super'
  const toast = useToast()
  const ent = useAsync(() => api.platform.entitlements(tenant), [tenant])
  const support = useAsync(() => api.platform.supportSessions(tenant), [tenant])
  const [details, setDetails] = useState({ name: summary.name, slug: summary.slug })
  const [dates, setDates] = useState(null)
  const [limits, setLimits] = useState({})
  const act = useMutation((fn) => fn())

  useEffect(() => setDetails({ name: summary.name, slug: summary.slug }), [summary])
  useEffect(() => {
    if (!ent.data) return
    const sub = ent.data.subscription
    setDates(sub ? { status: sub.status, ends_on: sub.ends_on ?? '', trial_ends_on: sub.trial_ends_on ?? '' } : null)
    setLimits(Object.fromEntries(ent.data.limits.map((row) => [
      row.key, row.overridden ? (row.allowed === null ? 'unlimited' : String(row.allowed)) : '',
    ])))
  }, [ent.data])

  const run = async (fn, message, after) => {
    try {
      await act.run(fn)
      toast.success(message)
      after?.()
    } catch (caught) {
      toast.error(caught.message)
    }
  }
  const setEnt = (body, message) => run(() => api.platform.setEntitlements(tenant, body), message, ent.reload)

  return (
    <>
      <div className="ui-grid ui-grid--2" style={{ alignItems: 'start' }}>
        <Card>
          <CardHeader title="بيانات المجموعة" />
          <CardBody>
            <div className="ui-stack">
              <Input id="group-name" label="الاسم" value={details.name} disabled={!canChange}
                onChange={(e) => setDetails({ ...details, name: e.target.value })} />
              <Input id="group-slug" label="المعرّف (رابط بوابة المرضى)" dir="ltr" value={details.slug}
                disabled={!canChange} hint="تغييره يغيّر رابط بوابة المرضى القديم"
                onChange={(e) => setDetails({ ...details, slug: e.target.value })} />
              {canChange && (
                <div className="ui-row" style={{ flexWrap: 'wrap' }}>
                  <Button variant="primary" loading={act.submitting}
                    onClick={() => run(() => api.platform.editTenant(tenant, details), 'تم الحفظ', onChanged)}>
                    حفظ
                  </Button>
                  <Button onClick={() => api.platform.exportGroup(tenant, `${summary.slug}.zip`)
                    .catch((caught) => toast.error(caught.message))}>
                    تصدير بيانات المجموعة
                  </Button>
                </div>
              )}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="الاشتراك" subtitle={ent.data?.subscription ? `الباقة: ${ent.data.subscription.plan}` : undefined} />
          <CardBody>
            {dates ? (
              <div className="ui-stack">
                <div className="integrations__controls">
                  <Select id="sub-status" label="حالة الاشتراك" value={dates.status} disabled={!canChange}
                    options={ent.data.statuses} onChange={(e) => setDates({ ...dates, status: e.target.value })} />
                  <Input id="sub-ends" label="ينتهي في" type="date" value={dates.ends_on} disabled={!canChange}
                    onChange={(e) => setDates({ ...dates, ends_on: e.target.value })} />
                  <Input id="sub-trial" label="نهاية التجربة" type="date" value={dates.trial_ends_on}
                    disabled={!canChange} onChange={(e) => setDates({ ...dates, trial_ends_on: e.target.value })} />
                </div>
                {canChange && (
                  <div className="ui-row">
                    <Button loading={act.submitting} onClick={() => setEnt(dates, 'تم تحديث الاشتراك')}>حفظ</Button>
                  </div>
                )}
              </div>
            ) : <p className="ui-muted">لا يوجد اشتراك.</p>}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="الخدمات" subtitle="تشغيل أو إيقاف أي خدمة لهذه المجموعة بغضّ النظر عن الباقة" />
        <CardBody flush>
          <Table
            rows={ent.data?.features ?? []}
            rowKey={(row) => row.key}
            loading={ent.loading}
            columns={[
              {
                key: 'label', header: 'الخدمة',
                render: (row) => (
                  <>
                    {row.label} {!row.built && <Badge tone="info">قريباً</Badge>}
                  </>
                ),
              },
              { key: 'in_plan', header: 'في الباقة', render: (row) => (row.in_plan ? 'نعم' : 'لا') },
              {
                key: 'enabled', header: 'الآن',
                render: (row) => (
                  <>
                    <Badge tone={row.enabled ? 'ok' : 'neutral'}>{row.enabled ? 'تعمل' : 'متوقفة'}</Badge>
                    {row.override !== null && row.override !== undefined && <span className="ui-muted"> · استثناء</span>}
                  </>
                ),
              },
              {
                key: 'actions', header: '',
                render: (row) => canChange && (
                  <div className="ui-row">
                    <Button size="sm" variant={row.enabled ? 'ghost' : 'primary'}
                      onClick={() => setEnt({ features: { [row.key]: !row.enabled } }, row.enabled ? 'أُوقفت الخدمة' : 'شُغّلت الخدمة')}>
                      {row.enabled ? 'إيقاف' : 'تشغيل'}
                    </Button>
                    {row.override !== null && row.override !== undefined && (
                      <Button size="sm" variant="ghost"
                        onClick={() => setEnt({ features: { [row.key]: null } }, 'عادت الخدمة لإعداد الباقة')}>
                        كما في الباقة
                      </Button>
                    )}
                  </div>
                ),
              },
            ]}
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="الحدود" subtitle="فارغ = حد الباقة · unlimited = غير محدود · أو رقم" />
        <CardBody>
          <div className="integrations__controls">
            {(ent.data?.limits ?? []).map((row) => (
              <Input
                key={row.key}
                id={`limit-${row.key}`}
                label={`${row.label_ar} (مستخدم ${row.used ?? '—'})`}
                hint={`الباقة: ${row.plan_value ?? 'غير محدود'}`}
                dir="ltr"
                value={limits[row.key] ?? ''}
                disabled={!canChange}
                onChange={(e) => setLimits({ ...limits, [row.key]: e.target.value.trim() })}
              />
            ))}
          </div>
          {canChange && (
            <div className="ui-row integrations__actions">
              <Button loading={act.submitting} onClick={() => setEnt({
                limits: Object.fromEntries(Object.entries(limits).map(([k, v]) => [k, v === '' ? null : v])),
              }, 'تم تحديث الحدود')}>
                حفظ الحدود
              </Button>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="سجل دخول الدعم" subtitle="كل «دخول كـ» على حسابات هذه المجموعة" />
        <CardBody flush>
          <Table
            rows={support.data ?? []}
            rowKey={(row) => row.id}
            loading={support.loading}
            empty={{ title: 'لم يدخل الدعم إلى هذه المجموعة' }}
            columns={[
              { key: 'started_at', header: 'البدء', render: (row) => formatDateTime(row.started_at) },
              { key: 'operator', header: 'المطوّر', render: (row) => <span dir="ltr">{row.operator}</span> },
              { key: 'target', header: 'الحساب' },
              { key: 'reason', header: 'السبب' },
              {
                key: 'state', header: 'الحالة',
                render: (row) => (row.active ? <Badge tone="warn">جارية</Badge>
                  : `انتهت ${formatDate(row.ended_at ?? row.expires_at)}`),
              },
            ]}
          />
        </CardBody>
      </Card>
    </>
  )
}
