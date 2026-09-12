import { useState } from 'react'

import { api } from '@/api'
import { Badge, Button, Card, CardBody, CardHeader, Input, Modal, Table } from '@/components/ui'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { formatDateTime, formatRelative } from '@/lib/format'

/** One group's clinics (doctors, employees, accounts, online) and every
 * account with its role and last activity — and, for a full administrator,
 * what can be done to each: stop or restart a clinic; give an account a new
 * password, stop or restart it, sign it out everywhere, or sign in as it for
 * support; add another owner. */
export function TenantPeople({ tenant }) {
  const { platformUser } = useAuth()
  const canChange = platformUser?.role === 'super'
  const toast = useToast()
  const { data, loading, error, reload } = useAsync(() => api.platform.people(tenant), [tenant])
  const [secret, setSecret] = useState(null) // {title, email, password}
  const [supporting, setSupporting] = useState(null)
  const [owner, setOwner] = useState(null)
  const act = useMutation((fn) => fn())

  const run = async (fn, message) => {
    try {
      const result = await act.run(fn)
      if (message) toast.success(message)
      reload()
      return result
    } catch (caught) {
      toast.error(caught.message)
      return null
    }
  }

  return (
    <>
      <Card>
        <CardHeader title="العيادات" subtitle="الأطباء والموظفون والحسابات لكل عيادة" />
        <CardBody flush>
          <Table
            columns={[
              { key: 'name', header: 'العيادة', render: (row) => (
                <>
                  {row.name} {!row.is_active && <Badge tone="neutral">موقوفة</Badge>}
                </>
              ) },
              { key: 'doctors', header: 'أطباء', numeric: true },
              { key: 'employees', header: 'موظفون', numeric: true },
              { key: 'accounts', header: 'حسابات', numeric: true },
              { key: 'online', header: 'أونلاين', numeric: true,
                render: (row) => (row.online ? <Badge tone="ok">{row.online}</Badge> : 0) },
              {
                key: 'actions', header: '',
                render: (row) => canChange && (
                  <Button
                    size="sm"
                    variant={row.is_active ? 'ghost' : 'secondary'}
                    onClick={() => run(
                      () => api.platform.setBranchActive(tenant, row.id, !row.is_active),
                      row.is_active ? 'أُوقفت العيادة' : 'أُعيد تشغيل العيادة',
                    )}
                  >
                    {row.is_active ? 'إيقاف' : 'تشغيل'}
                  </Button>
                ),
              },
            ]}
            rows={data?.branches ?? []}
            loading={loading}
            error={error}
            onRetry={reload}
            empty={{ title: 'لا توجد عيادات' }}
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="الحسابات"
          subtitle="آخر نشاط وآخر دخول لكل حساب"
          actions={canChange && <Button size="sm" onClick={() => setOwner({ email: '' })}>إضافة مالك</Button>}
        />
        <CardBody flush>
          <Table
            columns={[
              { key: 'username', header: 'الحساب', render: (row) => (
                <>
                  <strong>{row.username}</strong>
                  <div className="ui-muted" dir="ltr">{row.email}</div>
                </>
              ) },
              { key: 'role', header: 'الدور', render: (row) => row.role ?? '—' },
              { key: 'branch', header: 'العيادة', render: (row) => row.branch ?? '—' },
              {
                key: 'status',
                header: 'الحالة',
                render: (row) =>
                  !row.is_active ? <Badge tone="neutral">موقوف</Badge>
                    : row.online ? <Badge tone="ok">أونلاين</Badge> : <Badge tone="neutral">غير متصل</Badge>,
              },
              { key: 'last_seen_at', header: 'آخر نشاط',
                render: (row) => (row.last_seen_at ? formatRelative(row.last_seen_at) : 'لم يظهر بعد') },
              { key: 'last_login', header: 'آخر دخول',
                render: (row) => (row.last_login ? formatDateTime(row.last_login) : '—') },
              {
                key: 'actions', header: '',
                render: (row) => canChange && (
                  <div className="ui-row account-actions">
                    <Button size="sm" variant="primary" disabled={!row.is_active}
                      onClick={() => setSupporting({ user: row, minutes: 30, reason: '' })}>
                      دخول كـ
                    </Button>
                    <Button size="sm" onClick={async () => {
                      const result = await run(() => api.platform.accountAction(row.uuid, 'reset-password'))
                      if (result) setSecret({ title: `كلمة مرور جديدة لـ ${row.username}`, email: row.email, password: result.password })
                    }}>
                      كلمة مرور جديدة
                    </Button>
                    <Button size="sm" variant="ghost"
                      onClick={() => run(() => api.platform.accountAction(row.uuid, 'logout'), 'تم تسجيل خروجه من كل الأجهزة')}>
                      تسجيل خروج
                    </Button>
                    <Button size="sm" variant="ghost"
                      onClick={() => run(
                        () => api.platform.accountAction(row.uuid, row.is_active ? 'deactivate' : 'activate'),
                        row.is_active ? 'أُوقف الحساب' : 'أُعيد تفعيل الحساب',
                      )}>
                      {row.is_active ? 'إيقاف' : 'تفعيل'}
                    </Button>
                  </div>
                ),
              },
            ]}
            rows={data?.accounts ?? []}
            loading={loading}
            empty={{ title: 'لا توجد حسابات' }}
          />
        </CardBody>
      </Card>

      {secret && (
        <Modal open onClose={() => setSecret(null)} title={secret.title}
          footer={<Button variant="primary" onClick={() => setSecret(null)}>تم</Button>}>
          <div className="platform__credentials" role="status">
            <div>البريد: <code dir="ltr">{secret.email}</code></div>
            <div>كلمة المرور: <code dir="ltr">{secret.password}</code></div>
            <p className="ui-muted">تُعرض مرة واحدة فقط. سُجّل خروج الحساب من كل الأجهزة.</p>
          </div>
        </Modal>
      )}

      {owner && (
        <Modal
          open
          onClose={() => setOwner(null)}
          title="إضافة مالك للمجموعة"
          footer={
            <>
              <Button variant="ghost" onClick={() => setOwner(null)}>إلغاء</Button>
              <Button variant="primary" loading={act.submitting} disabled={!owner.email}
                onClick={async () => {
                  const result = await run(() => api.platform.addOwner(tenant, owner), 'أُضيف المالك')
                  if (result) {
                    setOwner(null)
                    setSecret({ title: 'حساب المالك الجديد', email: result.email, password: result.password })
                  }
                }}>
                إضافة
              </Button>
            </>
          }
        >
          <Input id="owner-email" label="البريد الإلكتروني" type="email" dir="ltr" required value={owner.email}
            onChange={(e) => setOwner({ ...owner, email: e.target.value })} />
        </Modal>
      )}

      {supporting && (
        <Modal
          open
          onClose={() => setSupporting(null)}
          title={`الدخول كـ ${supporting.user.username}`}
          footer={
            <>
              <Button variant="ghost" onClick={() => setSupporting(null)}>إلغاء</Button>
              <Button variant="danger" loading={act.submitting} disabled={!supporting.reason.trim()}
                onClick={async () => {
                  const result = await run(() => api.platform.startSupport(tenant, {
                    user: supporting.user.uuid, minutes: supporting.minutes, reason: supporting.reason,
                  }))
                  if (result) window.location.assign(result.redirect)
                }}>
                دخول
              </Button>
            </>
          }
        >
          <div className="ui-stack">
            <p className="ui-muted" style={{ margin: 0 }}>
              ستعمل داخل المجموعة بصلاحيات هذا الحساب. يُبلَّغ مالكو المجموعة بالدخول وسببه، ويُسجَّل كل تعديل
              باسم الدعم، وتنتهي الجلسة تلقائياً بانتهاء المدة.
            </p>
            <Input id="support-reason" label="السبب" required value={supporting.reason}
              onChange={(e) => setSupporting({ ...supporting, reason: e.target.value })} />
            <Input id="support-minutes" label="المدة (دقيقة، 5–120)" type="number" min="5" max="120"
              value={supporting.minutes} onChange={(e) => setSupporting({ ...supporting, minutes: e.target.value })} />
          </div>
        </Modal>
      )}
    </>
  )
}
