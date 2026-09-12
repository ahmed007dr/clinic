import { useEffect, useMemo, useState } from 'react'

import { api } from '@/api'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Checkbox,
  ConfirmDialog,
  ErrorState,
  Input,
  Loading,
  Select,
  Tabs,
  Textarea,
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { formatDateTime } from '@/lib/format'

import { ScopePicker, scopeReady } from './ScopePicker'

const ENVIRONMENTS = [
  { id: 'test', label: 'تجريبي (Test)' },
  { id: 'production', label: 'إنتاج (Production)' },
]
const GATEWAYS = ['paymob', 'fawry', 'vodafone_cash']

/**
 * Keys and passwords for every integration — email (SMTP), cPanel, Paymob,
 * Fawry, Vodafone Cash, Google Drive — for the whole platform, one owner
 * group, or one clinic, each with a test and a production set.
 *
 * This screen is the only way they enter the system (the group owner's
 * rule). They are encrypted on the server and never come back whole: a saved
 * secret shows as "saved …last four", and leaving it blank keeps it.
 */
export function PlatformIntegrationsPage() {
  const [place, setPlace] = useState({ scope: 'platform', customer: '', branch: '' })
  const ready = scopeReady(place)
  const params = ready
    ? { scope: place.scope, customer: place.customer || undefined, branch: place.branch || undefined }
    : { scope: '__none__' }
  const { data, loading, error, reload } = useAsync(
    () => api.platform.integrations(params),
    [place.scope, place.customer, place.branch],
  )

  const kinds = useMemo(
    () => (data?.kinds ?? []).filter((kind) => kind.scopes.includes(place.scope)),
    [data, place.scope],
  )

  return (
    <>
      <PageHeader
        title="المفاتيح والتكاملات"
        subtitle="البريد وبوابات الدفع و cPanel و Google Drive — لكل المنصة أو لكل مجموعة أو لكل عيادة، ببيئتين: تجريبي وإنتاج"
      />
      <div className="ui-stack">
        <Card>
          <CardBody>
            <ScopePicker value={place} onChange={setPlace} />
            <p className="ui-muted integrations__order">
              عند الاستخدام يُؤخذ إعداد العيادة أولاً، ثم إعداد مجموعتها، ثم إعداد المنصة. بوابات الدفع لتحصيل
              العيادة من مرضاها لا ترجع أبداً إلى مفاتيح المنصة؛ مفاتيح المنصة لتحصيل الاشتراكات فقط.
            </p>
          </CardBody>
        </Card>

        {!ready && <p className="ui-muted">اختر المجموعة{place.scope === 'clinic' ? ' والعيادة' : ''} لعرض إعداداتها.</p>}
        {ready && loading && !data && <Loading />}
        {ready && error && <ErrorState error={error} onRetry={reload} />}
        {ready && data && (
          <>
            {kinds.map((kind) => (
              <IntegrationCard
                key={`${kind.kind}-${place.scope}-${place.customer}-${place.branch}`}
                spec={kind}
                place={place}
                item={data.items.find((row) => row.kind === kind.kind)}
                callbackUrl={data.callback_urls?.[kind.kind]}
                onSaved={reload}
              />
            ))}
          </>
        )}
      </div>
    </>
  )
}

function blankValues(spec, masked) {
  const values = {}
  spec.fields.forEach((field) => {
    const shown = masked?.[field.name]
    if (field.secret) values[field.name] = ''
    else if (field.type === 'bool') values[field.name] = Boolean(shown)
    else values[field.name] = shown ?? ''
  })
  return values
}

function IntegrationCard({ spec, place, item, callbackUrl, onSaved }) {
  const { platformUser } = useAuth()
  const canChange = platformUser?.role === 'super'
  const toast = useToast()
  const [tab, setTab] = useState(item?.mode ?? 'test')
  const [values, setValues] = useState({
    test: blankValues(spec, item?.test),
    production: blankValues(spec, item?.production),
  })
  const [mode, setMode] = useState(item?.mode ?? 'test')
  const [enabled, setEnabled] = useState(item?.enabled ?? true)
  const [notes, setNotes] = useState(item?.notes ?? '')
  const [check, setCheck] = useState(null)
  const [removing, setRemoving] = useState(false)

  useEffect(() => {
    setValues({ test: blankValues(spec, item?.test), production: blankValues(spec, item?.production) })
    setMode(item?.mode ?? 'test')
    setEnabled(item?.enabled ?? true)
    setNotes(item?.notes ?? '')
  }, [item, spec])

  const save = useMutation(() =>
    api.platform.saveIntegration({
      kind: spec.kind,
      scope: place.scope,
      customer: place.customer || undefined,
      branch: place.branch || undefined,
      mode,
      enabled,
      notes,
      test: values.test,
      production: values.production,
    }),
  )
  const test = useMutation((env) => api.platform.testIntegration(item.id, env))
  const remove = useMutation(() => api.platform.removeIntegration(item.id))

  const set = (env, name, value) => setValues((all) => ({ ...all, [env]: { ...all[env], [name]: value } }))
  const missing = item ? item[`${mode}_missing`] : null

  return (
    <Card>
      <CardHeader
        title={spec.label}
        subtitle={
          item
            ? `آخر تعديل ${formatDateTime(item.updated_at)}${item.updated_by ? ` · ${item.updated_by}` : ''}`
            : 'غير مضبوط على هذا المستوى'
        }
        actions={
          <div className="ui-row">
            {item && (
              <Badge tone={item.enabled ? 'ok' : 'neutral'}>{item.enabled ? 'مفعّل' : 'موقوف'}</Badge>
            )}
            {item && (
              <Badge tone={item.mode === 'production' ? 'primary' : 'warn'}>
                البيئة الحالية: {item.mode === 'production' ? 'إنتاج' : 'تجريبي'}
              </Badge>
            )}
            {item?.error && <Badge tone="urgent">{item.error}</Badge>}
          </div>
        }
      />
      <CardBody>
        <Tabs
          items={ENVIRONMENTS.map((env) => ({
            ...env,
            badge: item && item[`${env.id}_missing`]?.length ? 'ناقص' : null,
          }))}
          active={tab}
          onChange={(id) => {
            setTab(id)
            setCheck(null)
          }}
        />
        <div className="integrations__fields">
          {spec.fields.map((field) => (
            <Field
              key={`${tab}-${field.name}`}
              id={`${spec.kind}-${tab}-${field.name}`}
              field={field}
              value={values[tab][field.name]}
              saved={item?.[tab]?.[field.name]}
              disabled={!canChange}
              onChange={(value) => set(tab, field.name, value)}
            />
          ))}
        </div>

        {GATEWAYS.includes(spec.kind) && callbackUrl && (
          <div className="integrations__callback">
            <strong>رابط الـ Callback</strong> — ضعه في لوحة {spec.label} (Transaction processed / response
            callback، أو Return URL):
            <code dir="ltr">{callbackUrl}</code>
          </div>
        )}

        <div className="integrations__controls">
          <Select
            id={`${spec.kind}-mode`}
            label="البيئة المستخدمة فعلياً"
            options={[
              { value: 'test', label: 'تجريبي' },
              { value: 'production', label: 'إنتاج' },
            ]}
            value={mode}
            onChange={(event) => setMode(event.target.value)}
            disabled={!canChange}
          />
          <Input
            id={`${spec.kind}-notes`}
            label="ملاحظات"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            disabled={!canChange}
          />
          <Checkbox
            id={`${spec.kind}-enabled`}
            label="مفعّل"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
            disabled={!canChange}
          />
        </div>
        {missing?.length > 0 && (
          <p className="integrations__missing">بيانات البيئة المستخدمة ناقصة: {missing.join('، ')}</p>
        )}

        {check && (
          <p className={check.ok ? 'integrations__ok' : 'integrations__missing'} role="status">
            {check.detail}
          </p>
        )}

        <div className="ui-row integrations__actions">
          {canChange && (
            <Button
              variant="primary"
              loading={save.submitting}
              onClick={async () => {
                try {
                  await save.run()
                  toast.success(`تم حفظ ${spec.label}`)
                  onSaved()
                } catch (caught) {
                  toast.error(caught.message)
                }
              }}
            >
              حفظ
            </Button>
          )}
          {item && (
            <Button
              loading={test.submitting}
              onClick={async () => {
                try {
                  setCheck(await test.run(tab))
                } catch (caught) {
                  setCheck({ ok: false, detail: caught.message })
                }
              }}
            >
              اختبار بيانات «{tab === 'production' ? 'الإنتاج' : 'التجريبي'}» المحفوظة
            </Button>
          )}
          {item && canChange && (
            <Button variant="ghost" onClick={() => setRemoving(true)}>
              حذف
            </Button>
          )}
        </div>
      </CardBody>

      <ConfirmDialog
        open={removing}
        onClose={() => setRemoving(false)}
        tone="danger"
        loading={remove.submitting}
        title={`حذف ${spec.label}`}
        message="تُحذف مفاتيح البيئتين على هذا المستوى. سيُستخدم إعداد المستوى الأعلى إن وُجد."
        confirmLabel="حذف"
        onConfirm={async () => {
          try {
            await remove.run()
            toast.success('تم الحذف')
            onSaved()
          } catch (caught) {
            toast.error(caught.message)
          } finally {
            setRemoving(false)
          }
        }}
      />
    </Card>
  )
}

function Field({ id, field, value, saved, disabled, onChange }) {
  if (field.type === 'bool') {
    return (
      <Checkbox id={id} label={field.label} checked={Boolean(value)} disabled={disabled}
        onChange={(event) => onChange(event.target.checked)} />
    )
  }
  const hint = field.secret
    ? saved?.set
      ? `محفوظ (${saved.hint}) — اتركه فارغاً للإبقاء عليه`
      : 'غير محفوظ بعد'
    : undefined
  if (field.type === 'textarea') {
    return (
      <Textarea id={id} label={field.label} value={value} hint={hint} rows={4} dir="ltr" disabled={disabled}
        required={field.required} onChange={(event) => onChange(event.target.value)} />
    )
  }
  return (
    <Input
      id={id}
      label={field.label}
      value={value}
      hint={hint}
      dir="ltr"
      type={field.secret ? 'password' : field.type === 'number' ? 'number' : 'text'}
      autoComplete={field.secret ? 'new-password' : 'off'}
      required={field.required && !saved?.set}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
    />
  )
}
