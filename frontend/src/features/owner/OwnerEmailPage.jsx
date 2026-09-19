import { useEffect, useState } from 'react'

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
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { formatDateTime } from '@/lib/format'

import './owner.css'

const SOURCES = {
  clinic: { tone: 'ok', label: 'إعداد هذه العيادة' },
  group: { tone: 'primary', label: 'الإعداد الافتراضي للمجموعة' },
  platform: { tone: 'neutral', label: 'إعداد المنصة' },
  server: { tone: 'neutral', label: 'إعداد الخادم' },
  none: { tone: 'urgent', label: 'لا يوجد خادم بريد — لن تُرسل رسائل' },
}

/**
 * The Owner's email: one mail server for the whole group, and — if a clinic
 * should send from its own address — a different one for that clinic.
 *
 * A clinic uses its own settings if it has them, else the group's, else the
 * platform's. Passwords are saved encrypted and never come back: a saved one
 * shows as "saved …last four", and leaving it blank keeps it.
 */
export function OwnerEmailPage() {
  const { data, loading, error, reload } = useAsync(() => api.owner.email(), [])

  return (
    <>
      <PageHeader
        title="البريد الإلكتروني"
        subtitle="الخادم الذي تُرسل منه رسائل المجموعة وعياداتها: تقارير، إشعارات الأطباء، ودعوات بوابة المرضى"
      />
      {loading && !data && <Loading />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && (
        <div className="ui-stack">
          <MailCard
            title="الإعداد الافتراضي لكل العيادات"
            subtitle="تستخدمه كل عيادة ليس لها إعداد خاص بها"
            target="group"
            fields={data.fields}
            item={data.group}
            source={data.group_source}
            onSaved={reload}
          />
          <h2 className="owner-section-title">إعداد خاص بعيادة</h2>
          <p className="ui-muted">
            اضبط عيادة بعينها لترسل من بريدها هي. عند حذف إعدادها تعود إلى الافتراضي.
          </p>
          <UseDefaultForAll
            count={data.branches.filter((branch) => branch.own).length}
            ready={Boolean(data.group?.enabled) && !data.group?.missing?.length && !data.group?.error}
            onDone={reload}
          />
          {data.branches.map((branch) => (
            <MailCard
              key={branch.id}
              title={branch.name}
              subtitle={branch.is_active ? undefined : 'عيادة موقوفة'}
              target={String(branch.id)}
              fields={data.fields}
              item={branch.own}
              source={branch.source}
              onSaved={reload}
              collapsible
            />
          ))}
        </div>
      )}
    </>
  )
}

/** One default for every clinic: drops each clinic's own settings so they all
 * send through the group's. Offered only when there is something to drop. */
function UseDefaultForAll({ count, ready, onDone }) {
  const toast = useToast()
  const [confirming, setConfirming] = useState(false)
  const apply = useMutation(() => api.owner.applyEmailDefault())

  if (count === 0) return null
  return (
    <>
      <div className="ui-row">
        <Button onClick={() => setConfirming(true)} disabled={!ready}>
          جعل كل العيادات تستخدم الإعداد الافتراضي ({count})
        </Button>
        {!ready && <span className="ui-muted">اضبط الإعداد الافتراضي وفعّله أولاً.</span>}
      </div>
      <ConfirmDialog
        open={confirming}
        onClose={() => setConfirming(false)}
        tone="danger"
        loading={apply.submitting}
        title="إعداد واحد لكل العيادات"
        message={`ستُحذف الإعدادات الخاصة بـ ${count} عيادة، وتُرسل كل عياداتك من الإعداد الافتراضي للمجموعة.`}
        confirmLabel="تطبيق"
        onConfirm={async () => {
          try {
            const result = await apply.run()
            toast.success(`تم: ${result.cleared} عيادة تستخدم الآن الإعداد الافتراضي`)
            onDone()
          } catch (caught) {
            toast.error(caught.message)
          } finally {
            setConfirming(false)
          }
        }}
      />
    </>
  )
}

function blank(fields, masked) {
  const values = {}
  fields.forEach((field) => {
    const shown = masked?.[field.name]
    if (field.secret) values[field.name] = ''
    else if (field.type === 'bool') values[field.name] = Boolean(shown)
    else values[field.name] = shown ?? ''
  })
  // A new record defaults to the common secure setup.
  if (!masked) {
    values.port = '465'
    values.use_ssl = true
  }
  return values
}

function MailCard({ title, subtitle, target, fields, item, source, onSaved, collapsible = false }) {
  const toast = useToast()
  const [values, setValues] = useState(() => blank(fields, item?.values))
  const [enabled, setEnabled] = useState(item?.enabled ?? true)
  const [open, setOpen] = useState(!collapsible || Boolean(item))
  const [check, setCheck] = useState(null)
  const [removing, setRemoving] = useState(false)

  useEffect(() => {
    setValues(blank(fields, item?.values))
    setEnabled(item?.enabled ?? true)
    setCheck(null)
  }, [item, fields])

  const body = { ...values, enabled }
  const save = useMutation(() => api.owner.saveEmail(target, body))
  const test = useMutation(() => api.owner.testEmail(target, body))
  const remove = useMutation(() => api.owner.removeEmail(target))
  const set = (name, value) => setValues((all) => ({ ...all, [name]: value }))
  const shown = SOURCES[source] ?? SOURCES.none

  return (
    <Card>
      <CardHeader
        title={title}
        subtitle={
          subtitle ??
          (item?.updated_at
            ? `آخر تعديل ${formatDateTime(item.updated_at)}${item.updated_by ? ` · ${item.updated_by}` : ''}`
            : undefined)
        }
        actions={
          <div className="ui-row">
            <Badge tone={shown.tone}>{collapsible ? `يرسل من: ${shown.label}` : shown.label}</Badge>
            {item && !item.enabled && <Badge tone="neutral">موقوف</Badge>}
            {collapsible && !item && (
              <Button size="sm" onClick={() => setOpen((value) => !value)}>
                {open ? 'إخفاء' : 'إعداد خاص'}
              </Button>
            )}
          </div>
        }
      />
      {open && (
        <CardBody>
          {item?.error && <p className="mail-note mail-note--bad">{item.error}</p>}
          <div className="mail-fields">
            {fields.map((field) =>
              field.type === 'bool' ? (
                <Checkbox
                  key={field.name}
                  id={`${target}-${field.name}`}
                  label={field.label}
                  checked={Boolean(values[field.name])}
                  onChange={(event) => set(field.name, event.target.checked)}
                />
              ) : (
                <Input
                  key={field.name}
                  id={`${target}-${field.name}`}
                  label={field.label}
                  dir="ltr"
                  type={field.secret ? 'password' : field.type === 'number' ? 'number' : 'text'}
                  autoComplete={field.secret ? 'new-password' : 'off'}
                  value={values[field.name]}
                  hint={
                    field.secret
                      ? item?.values?.[field.name]?.set
                        ? `محفوظة (${item.values[field.name].hint}) — اتركها فارغة للإبقاء عليها`
                        : 'غير محفوظة بعد'
                      : undefined
                  }
                  required={field.required && !(field.secret && item?.values?.[field.name]?.set)}
                  onChange={(event) => set(field.name, event.target.value)}
                />
              ),
            )}
          </div>
          <Checkbox
            id={`${target}-enabled`}
            label="مفعّل"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />

          {check && (
            <p className={check.ok ? 'mail-note mail-note--ok' : 'mail-note mail-note--bad'} role="status">
              {check.detail}
            </p>
          )}

          <div className="ui-row mail-actions">
            <Button
              variant="primary"
              loading={save.submitting}
              onClick={async () => {
                try {
                  await save.run()
                  toast.success(`تم حفظ إعداد «${title}»`)
                  onSaved()
                } catch (caught) {
                  toast.error(caught.message)
                }
              }}
            >
              حفظ
            </Button>
            <Button
              loading={test.submitting}
              onClick={async () => {
                try {
                  setCheck(await test.run())
                } catch (caught) {
                  setCheck({ ok: false, detail: caught.message })
                }
              }}
            >
              اختبار الاتصال
            </Button>
            {item && (
              <Button variant="ghost" onClick={() => setRemoving(true)}>
                حذف
              </Button>
            )}
          </div>
        </CardBody>
      )}

      <ConfirmDialog
        open={removing}
        onClose={() => setRemoving(false)}
        tone="danger"
        loading={remove.submitting}
        title={`حذف إعداد «${title}»`}
        message={
          collapsible
            ? 'ستعود هذه العيادة إلى الإعداد الافتراضي للمجموعة.'
            : 'ستعود كل العيادات التي ليس لها إعداد خاص إلى إعداد المنصة.'
        }
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
