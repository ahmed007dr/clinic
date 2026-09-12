import { useState } from 'react'

import { api } from '@/api'
import {
  Badge,
  Button,
  Card,
  CardBody,
  Checkbox,
  ErrorState,
  Input,
  Loading,
  Modal,
  Select,
  Table,
  Textarea,
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { formatMoney } from '@/lib/format'

const LIMIT_LABELS = {
  max_branches: 'العيادات',
  max_doctors: 'الأطباء',
  max_staff: 'الموظفون',
  max_patients: 'المرضى',
  max_storage_mb: 'التخزين (MB)',
}

/** The plan catalogue: prices, cycles, limits and the services each plan
 * turns on. A plan's price is what groups without a negotiated price pay. */
export function PlatformPlansPage() {
  const { platformUser } = useAuth()
  const canChange = platformUser?.role === 'super'
  const { data, loading, error, reload } = useAsync(() => api.platform.managePlans(), [])
  const [editing, setEditing] = useState(null)

  if (loading && !data) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  return (
    <>
      <PageHeader
        title="الباقات"
        subtitle="الأسعار والحدود والخدمات المتاحة في كل باقة"
        actions={canChange && <Button variant="primary" onClick={() => setEditing({})}>باقة جديدة</Button>}
      />
      <Card>
        <CardBody flush>
          <Table
            rows={data.items}
            rowKey={(row) => row.id}
            columns={[
              {
                key: 'name', header: 'الباقة',
                render: (row) => (
                  <>
                    <strong>{row.name}</strong> <span className="ui-muted" dir="ltr">{row.code}</span>
                  </>
                ),
              },
              {
                key: 'price', header: 'السعر', numeric: true,
                render: (row) => `${formatMoney(row.price)} / ${row.billing_period_label}`,
              },
              {
                key: 'limits', header: 'الحدود',
                render: (row) => Object.entries(row.limits)
                  .map(([key, value]) => `${LIMIT_LABELS[key] ?? key}: ${value ?? '∞'}`).join(' · '),
              },
              {
                key: 'features', header: 'الخدمات',
                render: (row) => (
                  <div className="ui-row" style={{ flexWrap: 'wrap' }}>
                    {data.features.filter((f) => row.features?.[f.key]).map((f) => (
                      <Badge key={f.key} tone="info">{f.label}</Badge>
                    ))}
                  </div>
                ),
              },
              {
                key: 'state', header: '',
                render: (row) => (
                  <div className="ui-row">
                    {!row.is_active && <Badge>غير معروضة</Badge>}
                    {!row.is_public && <Badge tone="warn">خاصة</Badge>}
                  </div>
                ),
              },
              {
                key: 'edit', header: '',
                render: (row) => canChange && <Button size="sm" onClick={() => setEditing(row)}>تعديل</Button>,
              },
            ]}
          />
        </CardBody>
      </Card>
      {editing && (
        <PlanModal plan={editing} meta={data} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload() }} />
      )}
    </>
  )
}

function PlanModal({ plan, meta, onClose, onSaved }) {
  const toast = useToast()
  const creating = !plan.id
  const [form, setForm] = useState({
    code: plan.code ?? '',
    name: plan.name ?? '',
    description: plan.description ?? '',
    price: plan.price ?? '0',
    currency: plan.currency ?? 'EGP',
    billing_period: plan.billing_period ?? 'monthly',
    limits: Object.fromEntries(meta.limits.map((l) => [l.key, plan.limits?.[l.key] ?? ''])),
    features: Object.fromEntries(meta.features.map((f) => [f.key, Boolean(plan.features?.[f.key])])),
    is_active: plan.is_active ?? true,
    is_public: plan.is_public ?? true,
  })
  const save = useMutation(() => (creating ? api.platform.createPlan(form) : api.platform.updatePlan(plan.id, form)))

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={creating ? 'باقة جديدة' : `تعديل ${plan.name}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>إلغاء</Button>
          <Button
            variant="primary"
            loading={save.submitting}
            onClick={async () => {
              try {
                await save.run()
                toast.success('تم حفظ الباقة')
                onSaved()
              } catch (caught) {
                toast.error(caught.message)
              }
            }}
          >
            حفظ
          </Button>
        </>
      }
    >
      <div className="ui-stack">
        <div className="integrations__controls">
          <Input id="plan-name" label="الاسم" required value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Input id="plan-code" label="الرمز" dir="ltr" required disabled={!creating} value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })} />
          <Input id="plan-price" label="السعر" type="number" min="0" step="0.01" value={form.price}
            onChange={(e) => setForm({ ...form, price: e.target.value })} />
          <Select id="plan-period" label="دورة الفوترة" options={meta.billing_periods} value={form.billing_period}
            onChange={(e) => setForm({ ...form, billing_period: e.target.value })} />
        </div>
        <Textarea id="plan-description" label="الوصف" value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <fieldset className="plan-form__group">
          <legend>الحدود (فارغ = غير محدود)</legend>
          <div className="integrations__controls">
            {meta.limits.map((limit) => (
              <Input key={limit.key} id={`plan-limit-${limit.key}`} label={LIMIT_LABELS[limit.key] ?? limit.label}
                type="number" min="0" value={form.limits[limit.key] ?? ''}
                onChange={(e) => setForm({ ...form, limits: { ...form.limits, [limit.key]: e.target.value } })} />
            ))}
          </div>
        </fieldset>
        <fieldset className="plan-form__group">
          <legend>الخدمات المتاحة</legend>
          <div className="integrations__controls">
            {meta.features.map((feature) => (
              <Checkbox key={feature.key} id={`plan-feature-${feature.key}`} label={feature.label}
                checked={form.features[feature.key]}
                onChange={(e) => setForm({ ...form, features: { ...form.features, [feature.key]: e.target.checked } })} />
            ))}
          </div>
        </fieldset>
        <div className="ui-row">
          <Checkbox id="plan-active" label="معروضة للاختيار" checked={form.is_active}
            onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
          <Checkbox id="plan-public" label="عامة (تظهر في قائمة الباقات)" checked={form.is_public}
            onChange={(e) => setForm({ ...form, is_public: e.target.checked })} />
        </div>
      </div>
    </Modal>
  )
}
