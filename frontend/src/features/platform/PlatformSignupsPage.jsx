import { useState } from 'react'
import { Link } from 'react-router-dom'

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
  Tabs,
  Table,
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { formatDateTime } from '@/lib/format'

const TONES = { pending: 'warn', approved: 'ok', rejected: 'neutral' }

/**
 * Requests to open a clinic group, from the public form (`/app/signup`).
 * Approving opens the group exactly as «new group» does — its first clinic,
 * its owner account, the requested plan and billing cycle — and emails the
 * owner their sign-in; rejecting emails the reason.
 */
export function PlatformSignupsPage() {
  const { platformUser } = useAuth()
  const canChange = platformUser?.role === 'super'
  const [status, setStatus] = useState('pending')
  const { data, loading, error, reload } = useAsync(() => api.platform.signups({ status }), [status])
  const [approving, setApproving] = useState(null)
  const [rejecting, setRejecting] = useState(null)

  if (loading && !data) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  return (
    <>
      <PageHeader title="طلبات فتح العيادات" subtitle="من نموذج التسجيل العام /app/signup" />
      <Tabs
        items={[
          { id: 'pending', label: 'بانتظار المراجعة', badge: data.counts.pending },
          { id: 'approved', label: 'تمت الموافقة' },
          { id: 'rejected', label: 'مرفوضة' },
        ]}
        active={status}
        onChange={setStatus}
      />
      <Card>
        <CardBody flush>
          <Table
            rows={data.items}
            rowKey={(row) => row.id}
            empty={{ title: 'لا توجد طلبات' }}
            columns={[
              {
                key: 'group_name', header: 'المجموعة',
                render: (row) => (
                  <>
                    <strong>{row.group_name}</strong>
                    {row.clinic_name && <div className="ui-muted">{row.clinic_name}</div>}
                  </>
                ),
              },
              {
                key: 'owner', header: 'المالك',
                render: (row) => (
                  <>
                    {row.owner_name}
                    <div className="ui-muted" dir="ltr">{row.email}</div>
                    <div className="ui-muted" dir="ltr">{row.phone}</div>
                  </>
                ),
              },
              {
                key: 'size', header: 'الحجم',
                render: (row) => `${row.branches} فرع · ${row.doctors} طبيب${row.city ? ` · ${row.city}` : ''}`,
              },
              {
                key: 'plan', header: 'الباقة',
                render: (row) => `${row.plan_name ?? 'لم يحدد'} · ${row.cycle_label}`,
              },
              { key: 'message', header: 'ملاحظات', render: (row) => row.message || '—' },
              { key: 'created_at', header: 'التاريخ', render: (row) => formatDateTime(row.created_at) },
              {
                key: 'status', header: 'الحالة',
                render: (row) => (
                  <>
                    <Badge tone={TONES[row.status]}>{row.status_label}</Badge>
                    {row.tenant && <div><Link to={`/platform/tenants/${row.tenant}`}>فتح المجموعة</Link></div>}
                    {row.reject_reason && <div className="ui-muted">{row.reject_reason}</div>}
                  </>
                ),
              },
              {
                key: 'actions', header: '',
                render: (row) => canChange && row.status === 'pending' && (
                  <div className="ui-row">
                    <Button size="sm" variant="primary" onClick={() => setApproving(row)}>موافقة</Button>
                    <Button size="sm" variant="ghost" onClick={() => setRejecting(row)}>رفض</Button>
                  </div>
                ),
              },
            ]}
          />
        </CardBody>
      </Card>
      {approving && <ApproveModal signup={approving} onClose={() => setApproving(null)} onDone={reload} />}
      {rejecting && <RejectModal signup={rejecting} onClose={() => setRejecting(null)} onDone={reload} />}
    </>
  )
}

function latinSlug(text) {
  return (text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40)
}

function ApproveModal({ signup, onClose, onDone }) {
  const toast = useToast()
  const plans = useAsync(() => api.platform.plans(), [])
  const [form, setForm] = useState({
    name: signup.group_name,
    slug: latinSlug(signup.group_name),
    branch_name: signup.clinic_name || 'الفرع الرئيسي',
    plan: signup.plan ?? '',
    cycle: signup.cycle,
    status: 'trial',
    send_email: true,
  })
  const [errors, setErrors] = useState({})
  const [result, setResult] = useState(null)
  const approve = useMutation(() => api.platform.approveSignup(signup.id, form))
  const set = (name) => (event) => setForm({ ...form, [name]: event.target.value })

  if (result) {
    return (
      <Modal open onClose={() => { onClose(); onDone() }} title="تم فتح المجموعة"
        footer={<Button variant="primary" onClick={() => { onClose(); onDone() }}>تم</Button>}>
        <div className="platform__credentials" role="status">
          <div>البريد: <code dir="ltr">{result.admin_email}</code></div>
          <div>كلمة المرور المؤقتة: <code dir="ltr">{result.admin_password}</code></div>
          <p className="ui-muted">
            {result.emailed ? 'أُرسلت بيانات الدخول إلى بريد المالك.' : 'لم تُرسل بالبريد — سلّمها للمالك بنفسك.'}
            {' '}تُعرض كلمة المرور هنا مرة واحدة فقط.
          </p>
        </div>
      </Modal>
    )
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`موافقة على «${signup.group_name}»`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>إلغاء</Button>
          <Button
            variant="primary"
            loading={approve.submitting}
            onClick={async () => {
              setErrors({})
              try {
                setResult(await approve.run())
                toast.success('تم فتح المجموعة')
              } catch (caught) {
                const fields = {}
                Object.entries(caught.fields || {}).forEach(([name, messages]) => {
                  fields[name] = Array.isArray(messages) ? messages.join(' ') : String(messages)
                })
                setErrors(fields)
                toast.error(caught.message)
              }
            }}
          >
            فتح المجموعة
          </Button>
        </>
      }
    >
      <div className="ui-stack">
        <Input id="approve-name" label="اسم المجموعة" value={form.name} onChange={set('name')} error={errors.name} />
        <Input id="approve-slug" label="المعرّف (حروف لاتينية)" dir="ltr" value={form.slug} onChange={set('slug')}
          error={errors.slug} hint="يظهر في رابط بوابة المرضى" />
        <Input id="approve-branch" label="اسم أول فرع" value={form.branch_name} onChange={set('branch_name')} />
        <div className="integrations__controls">
          <Select id="approve-plan" label="الباقة" value={form.plan} onChange={set('plan')}
            placeholder="الباقة الافتراضية (تجريبي)"
            options={(plans.data ?? []).map((p) => ({ value: p.code, label: p.name }))} />
          <Select id="approve-cycle" label="الدورة" value={form.cycle} onChange={set('cycle')}
            options={[{ value: 'monthly', label: 'شهري' }, { value: 'yearly', label: 'سنوي' }]} />
          <Select id="approve-status" label="الحالة" value={form.status} onChange={set('status')}
            options={[{ value: 'trial', label: 'تجريبي' }, { value: 'active', label: 'نشط' }]} />
        </div>
        <Checkbox id="approve-email" label="إرسال بيانات الدخول إلى بريد المالك" checked={form.send_email}
          onChange={(e) => setForm({ ...form, send_email: e.target.checked })} />
      </div>
    </Modal>
  )
}

function RejectModal({ signup, onClose, onDone }) {
  const toast = useToast()
  const [reason, setReason] = useState('')
  const [sendEmail, setSendEmail] = useState(true)
  const reject = useMutation(() => api.platform.rejectSignup(signup.id, { reason, send_email: sendEmail }))

  return (
    <Modal
      open
      onClose={onClose}
      title={`رفض «${signup.group_name}»`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>إلغاء</Button>
          <Button
            variant="danger"
            disabled={!reason.trim()}
            loading={reject.submitting}
            onClick={async () => {
              try {
                await reject.run()
                toast.success('رُفض الطلب')
                onClose()
                onDone()
              } catch (caught) {
                toast.error(caught.message)
              }
            }}
          >
            رفض الطلب
          </Button>
        </>
      }
    >
      <div className="ui-stack">
        <Input id="reject-reason" label="السبب" required value={reason} onChange={(e) => setReason(e.target.value)} />
        <Checkbox id="reject-email" label="إبلاغ مقدّم الطلب بالبريد" checked={sendEmail}
          onChange={(e) => setSendEmail(e.target.checked)} />
      </div>
    </Modal>
  )
}
