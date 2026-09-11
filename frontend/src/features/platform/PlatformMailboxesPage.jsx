import { useState } from 'react'

import { api } from '@/api'
import { Badge, Button, Card, CardBody, CardHeader, Checkbox, ErrorState, Input, Table } from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { formatDate } from '@/lib/format'

import { ScopePicker, scopeReady } from './ScopePicker'

/**
 * Email accounts for an owner group or one of its clinics, created on the
 * platform's cPanel. The new address can become that group's or clinic's
 * sender at once: its mail settings are stored (encrypted) as their SMTP
 * integration, so their emails go out from their own address.
 */
export function PlatformMailboxesPage() {
  const { platformUser } = useAuth()
  const canChange = platformUser?.role === 'super'
  const toast = useToast()
  const { data, error, reload } = useAsync(() => api.platform.mailboxes(), [])
  const [place, setPlace] = useState({ scope: 'group', customer: '', branch: '' })
  const [form, setForm] = useState({ local_part: '', quota_mb: 1024, use_for_sending: true })
  const [created, setCreated] = useState(null)
  const create = useMutation(() =>
    api.platform.createMailbox({
      customer: place.customer,
      branch: place.scope === 'clinic' ? place.branch : undefined,
      ...form,
    }),
  )

  if (error) return <ErrorState error={error} onRetry={reload} />

  return (
    <>
      <PageHeader title="الإيميلات" subtitle="إنشاء إيميل لكل مجموعة أو لكل عيادة على cPanel المنصة" />
      <div className="ui-stack">
        {data && !data.domain && (
          <p className="integrations__missing">
            اضبط بيانات cPanel أولاً من «المفاتيح والتكاملات» (مستوى المنصة) لتتمكن من إنشاء الإيميلات.
          </p>
        )}

        {canChange && (
          <Card>
            <CardHeader title="إيميل جديد" />
            <CardBody>
              <ScopePicker value={place} onChange={setPlace} scopes={['group', 'clinic']} />
              <div className="integrations__controls">
                <Input
                  id="mailbox-local"
                  label="اسم الإيميل"
                  dir="ltr"
                  value={form.local_part}
                  hint={data?.domain ? `${form.local_part || 'name'}@${data.domain}` : undefined}
                  onChange={(event) => setForm({ ...form, local_part: event.target.value.toLowerCase() })}
                />
                <Input
                  id="mailbox-quota"
                  label="المساحة (ميجابايت)"
                  type="number"
                  min="50"
                  value={form.quota_mb}
                  onChange={(event) => setForm({ ...form, quota_mb: event.target.value })}
                />
                <Checkbox
                  id="mailbox-sender"
                  label="اجعله بريد الإرسال لهذه المجموعة/العيادة"
                  checked={form.use_for_sending}
                  onChange={(event) => setForm({ ...form, use_for_sending: event.target.checked })}
                />
              </div>
              <div className="ui-row integrations__actions">
                <Button
                  variant="primary"
                  disabled={!scopeReady(place) || !form.local_part || !data?.domain}
                  loading={create.submitting}
                  onClick={async () => {
                    try {
                      setCreated(await create.run())
                      setForm({ ...form, local_part: '' })
                      toast.success('تم إنشاء الإيميل')
                      reload()
                    } catch (caught) {
                      toast.error(caught.message)
                    }
                  }}
                >
                  إنشاء الإيميل
                </Button>
              </div>
              {created && (
                <div className="platform__credentials" role="status">
                  <div>
                    الإيميل: <code dir="ltr">{created.address}</code>
                  </div>
                  <div>
                    كلمة المرور: <code dir="ltr">{created.password}</code>
                  </div>
                  <p className="ui-muted">تُعرض كلمة المرور هذه مرة واحدة فقط. انسخها وسلّمها لصاحب الإيميل.</p>
                </div>
              )}
            </CardBody>
          </Card>
        )}

        <Card>
          <CardHeader title="الإيميلات المنشأة" />
          <CardBody flush>
            <Table
              rows={data?.items ?? []}
              rowKey={(row) => row.id}
              empty={{ title: 'لا توجد إيميلات بعد' }}
              columns={[
                { key: 'address', header: 'الإيميل', render: (row) => <span dir="ltr">{row.address}</span> },
                { key: 'customer_name', header: 'المجموعة' },
                { key: 'branch', header: 'المستوى', render: (row) => (row.branch ? 'عيادة' : 'المجموعة') },
                { key: 'quota_mb', header: 'المساحة', numeric: true },
                {
                  key: 'used_for_sending', header: 'بريد الإرسال',
                  render: (row) => (row.used_for_sending ? <Badge tone="ok">نعم</Badge> : '—'),
                },
                { key: 'created_at', header: 'أُنشئ', render: (row) => formatDate(row.created_at) },
              ]}
            />
          </CardBody>
        </Card>
      </div>
    </>
  )
}
