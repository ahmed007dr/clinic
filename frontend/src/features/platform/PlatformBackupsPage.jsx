import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '@/api'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Checkbox,
  ErrorState,
  Input,
  Loading,
  Table,
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { fileSize, formatDateTime } from '@/lib/format'

const TONES = { running: 'warn', done: 'ok', failed: 'urgent' }

/**
 * Backups of the platform and every group — an encrypted archive on the
 * server and a copy on Google Drive — a cPanel full-account backup on request,
 * and importing a group's export as a new group.
 */
export function PlatformBackupsPage() {
  const { platformUser } = useAuth()
  const canChange = platformUser?.role === 'super'
  const toast = useToast()
  const { data, loading, error, reload } = useAsync(() => api.platform.backups(), [])
  const [policy, setPolicy] = useState(null)
  const act = useMutation((fn) => fn())

  useEffect(() => { if (data) setPolicy(data.policy) }, [data])
  // A running backup finishes in the background: look again every 10 s.
  useEffect(() => {
    if (!data?.runs.some((row) => row.status === 'running')) return undefined
    const timer = setInterval(reload, 10000)
    return () => clearInterval(timer)
  }, [data, reload])

  if (loading && !data) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const run = async (fn, message) => {
    try {
      const result = await act.run(fn)
      toast.success(result?.detail ?? message)
      reload()
    } catch (caught) {
      toast.error(caught.message)
    }
  }

  return (
    <>
      <PageHeader
        title="النسخ الاحتياطي والنقل"
        subtitle="نسخة مشفّرة على السيرفر + نسخة على Google Drive، ونسخة cPanel كاملة عند الطلب"
        actions={canChange && (
          <Button variant="primary" loading={act.submitting}
            onClick={() => run(() => api.platform.startBackup(), 'بدأ النسخ الاحتياطي')}>
            نسخة احتياطية الآن
          </Button>
        )}
      />
      <div className="ui-stack">
        {!data.drive_configured && (
          <p className="integrations__missing">
            Google Drive غير مضبوط — اضبطه من <Link to="/platform/integrations">المفاتيح والتكاملات</Link> (مجلد داخل
            Shared Drive أضفت إليه حساب الخدمة).
          </p>
        )}
        <div className="ui-grid ui-grid--2" style={{ alignItems: 'start' }}>
          <Card>
            <CardHeader title="سياسة الاحتفاظ" subtitle="النسخة اليومية تعمل من cron: manage.py platform_backup" />
            <CardBody>
              {policy && (
                <div className="ui-stack">
                  <div className="integrations__controls">
                    <Input id="keep-local" label="عدد النسخ على السيرفر" type="number" min="1" value={policy.keep_local}
                      disabled={!canChange} onChange={(e) => setPolicy({ ...policy, keep_local: e.target.value })} />
                    <Input id="keep-drive" label="عدد النسخ على Drive" type="number" min="1" value={policy.keep_drive}
                      disabled={!canChange} onChange={(e) => setPolicy({ ...policy, keep_drive: e.target.value })} />
                  </div>
                  <Checkbox id="to-drive" label="رفع كل نسخة إلى Google Drive" checked={policy.upload_to_drive}
                    disabled={!canChange} onChange={(e) => setPolicy({ ...policy, upload_to_drive: e.target.checked })} />
                  <Checkbox id="with-files" label="تضمين الملفات (الصور والمرفقات الطبية)" checked={policy.include_files}
                    disabled={!canChange} onChange={(e) => setPolicy({ ...policy, include_files: e.target.checked })} />
                  {canChange && (
                    <div className="ui-row">
                      <Button loading={act.submitting}
                        onClick={() => run(() => api.platform.setBackupPolicy(policy), 'تم الحفظ')}>
                        حفظ
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="نسخة cPanel الكاملة" subtitle="نسخة لحساب الاستضافة كله في المجلد الرئيسي" />
            <CardBody>
              <p className="ui-muted" style={{ marginTop: 0 }}>
                تشمل الملفات وقواعد البيانات والبريد. يبنيها cPanel في الخلفية ويرسل بريداً عند انتهائها.
              </p>
              {canChange && (
                <Button disabled={!data.cpanel_configured} loading={act.submitting}
                  onClick={() => run(() => api.platform.cpanelBackup(), 'تم الطلب')}>
                  طلب نسخة cPanel كاملة
                </Button>
              )}
              {!data.cpanel_configured && <p className="ui-muted">اضبط cPanel من المفاتيح والتكاملات أولاً.</p>}
            </CardBody>
          </Card>
        </div>

        <Card>
          <CardHeader title="النسخ" subtitle="مشفّرة بمفتاح PLATFORM_VAULT_KEY — احفظه بعيداً عن النسخ" />
          <CardBody flush>
            <Table
              rows={data.runs}
              rowKey={(row) => row.id}
              empty={{ title: 'لا توجد نسخ بعد' }}
              columns={[
                { key: 'started_at', header: 'الوقت', render: (row) => formatDateTime(row.started_at) },
                { key: 'status', header: 'الحالة', render: (row) => (
                  <>
                    <Badge tone={TONES[row.status]}>{row.status_label}</Badge>
                    {row.error && <div className="ui-muted">{row.error}</div>}
                  </>
                ) },
                { key: 'groups', header: 'المجموعات', numeric: true },
                { key: 'size', header: 'الحجم', numeric: true, render: (row) => (row.size ? fileSize(row.size) : '—') },
                { key: 'drive', header: 'Google Drive', render: (row) => (row.drive_file_id
                  ? <Badge tone="ok">مرفوعة</Badge>
                  : row.drive_error ? <span className="ui-muted">{row.drive_error}</span> : '—') },
                { key: 'trigger', header: 'المصدر', render: (row) => (row.trigger === 'schedule' ? 'مجدولة' : row.created_by ?? 'يدوي') },
                { key: 'download', header: '', render: (row) => canChange && row.on_server && (
                  <Button size="sm" onClick={() => api.platform.downloadBackup(row.id, row.file_name)
                    .catch((caught) => toast.error(caught.message))}>
                    تنزيل
                  </Button>
                ) },
              ]}
            />
          </CardBody>
        </Card>

        {canChange && <ImportCard />}
      </div>
    </>
  )
}

/** Bring a group's export in as a new group: a dry run first, then the real
 * thing. */
function ImportCard() {
  const toast = useToast()
  const [file, setFile] = useState(null)
  const [slug, setSlug] = useState('')
  const [name, setName] = useState('')
  const [accounts, setAccounts] = useState(true)
  const [report, setReport] = useState(null)
  const act = useMutation((dryRun) => {
    const body = new FormData()
    body.append('file', file)
    body.append('slug', slug)
    if (name) body.append('name', name)
    body.append('accounts', accounts ? '1' : '0')
    body.append('dry_run', dryRun ? '1' : '0')
    return api.platform.importGroup(body)
  })

  const go = async (dryRun) => {
    try {
      const result = await act.run(dryRun)
      setReport(result)
      if (!dryRun && result.tenant) toast.success('تم استيراد المجموعة')
    } catch (caught) {
      toast.error(caught.message)
    }
  }

  return (
    <Card>
      <CardHeader title="استيراد مجموعة" subtitle="من ملف تصدير مجموعة (zip) — من صفحة المجموعة أو من داخل نسخة احتياطية" />
      <CardBody>
        <div className="integrations__controls">
          <Input id="import-file" label="ملف التصدير" type="file" accept=".zip"
            onChange={(e) => { setFile(e.target.files?.[0] ?? null); setReport(null) }} />
          <Input id="import-slug" label="معرّف المجموعة الجديدة" dir="ltr" value={slug}
            onChange={(e) => { setSlug(e.target.value.toLowerCase()); setReport(null) }} />
          <Input id="import-name" label="الاسم (اختياري)" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <Checkbox id="import-accounts" label="استيراد الحسابات أيضاً (بكلمات مرورها)" checked={accounts}
          onChange={(e) => { setAccounts(e.target.checked); setReport(null) }} />
        <div className="ui-row integrations__actions">
          <Button disabled={!file || !slug} loading={act.submitting} onClick={() => go(true)}>فحص (بدون كتابة)</Button>
          <Button variant="primary" disabled={!report?.ok || !report?.dry_run} loading={act.submitting}
            onClick={() => go(false)}>
            استيراد فعلي
          </Button>
        </div>
        {report && (
          <div className="ui-stack" style={{ marginTop: 'var(--s3)' }}>
            {report.problems.map((problem) => <p key={problem} className="integrations__missing">{problem}</p>)}
            {report.warnings.map((warning) => <p key={warning} className="ui-muted">{warning}</p>)}
            <p>
              {report.tenant
                ? <>تم إنشاء <Link to={`/platform/tenants/${report.tenant.uuid}`}>{report.tenant.name}</Link>.</>
                : report.ok ? 'الفحص سليم — يمكنك الاستيراد.' : 'لا يمكن الاستيراد حتى تُحل المشكلات.'}
              {' '}المصدر: {report.source?.name} · {Object.values(report.counts).reduce((a, b) => a + b, 0)} صفاً ·
              {' '}{report.files} ملفاً
            </p>
          </div>
        )}
      </CardBody>
    </Card>
  )
}
