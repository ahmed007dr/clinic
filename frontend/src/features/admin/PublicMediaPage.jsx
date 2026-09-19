import { useState } from 'react'

import { api } from '@/api'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge, Button, Card, CardBody, CardHeader, ErrorState, Loading } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { serverUrl } from '@/lib/config'

import './publicMedia.css'

const KINDS = [
  { kind: 'logo', label: 'الشعار', hint: 'مربع أو مستطيل — حتى ١ ميجابايت' },
  { kind: 'cover', label: 'صورة الغلاف', hint: 'صورة عريضة — حتى ٣ ميجابايت' },
]

/**
 * The logo and cover the public page shows (docs/15, D8).
 *
 * The Owner sets the group's own and any clinic's, live at once. A clinic's
 * Admin can upload for their clinic, but it waits here as «بانتظار الموافقة» and
 * reaches the public only when the Owner approves it. These are separate from the
 * printed letterhead's logo (Print design), which is unchanged.
 */
export function PublicMediaPage() {
  const { permissions } = useAuth()
  const { data, loading, error, reload } = useAsync(() => api.publicMedia.get(), [])

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  return (
    <>
      <PageHeader
        title="صور الصفحة العامة"
        subtitle={
          permissions.is_owner
            ? 'شعار وغلاف المجمع وكل عيادة. ما يرفعه مدير العيادة يظهر للعامة بعد موافقتك.'
            : 'ارفع شعار وغلاف عيادتك. تظهر للعامة بعد موافقة مالك المجموعة.'
        }
        back={{ to: '/about', label: 'عن العيادة' }}
      />
      <div className="media-page">
        {data.group && (
          <MediaCard
            title="المجمع (الصفحة الرئيسية)"
            live={data.group}
            upload={(form) => api.publicMedia.uploadGroup(form)}
            remove={(kind) => api.publicMedia.removeGroup(kind)}
            onChange={reload}
          />
        )}
        {data.branches.map((branch) => (
          <MediaCard
            key={branch.uuid}
            title={branch.name}
            live={branch}
            pending={branch}
            status={branch.status}
            note={branch.review_note}
            canApprove={data.can_approve}
            upload={(form) => api.publicMedia.uploadBranch(branch.uuid, form)}
            remove={(kind, pendingOne) => api.publicMedia.removeBranch(branch.uuid, kind, pendingOne)}
            review={(decision, note) => api.publicMedia.review(branch.uuid, decision, note)}
            onChange={reload}
          />
        ))}
      </div>
    </>
  )
}

function MediaCard({ title, live, pending, status, note, canApprove, upload, remove, review, onChange }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')

  const act = async (work, done) => {
    setBusy(true)
    try {
      await work()
      if (done) toast.success(done)
      onChange()
    } catch (caught) {
      const fields = caught.fields ? Object.values(caught.fields).flat().join(' ') : ''
      toast.error(fields || caught.message)
    } finally {
      setBusy(false)
    }
  }

  const send = (kind, file) => {
    if (!file) return
    const form = new FormData()
    form.append(kind, file)
    act(() => upload(form), 'تم رفع الصورة.')
  }

  const hasPending = pending && (pending.pending_logo || pending.pending_cover)

  return (
    <Card>
      <CardHeader
        title={title}
        actions={
          status === 'pending' ? (
            <Badge tone="warn">بانتظار موافقة المالك</Badge>
          ) : status === 'rejected' ? (
            <Badge tone="urgent">مرفوض{note ? ` — ${note}` : ''}</Badge>
          ) : null
        }
      />
      <CardBody>
        <div className="media-slots">
          {KINDS.map(({ kind, label, hint }) => {
            const liveUrl = live?.[kind]
            const waitingUrl = pending?.[`pending_${kind}`]
            return (
              <div key={kind} className="media-slot">
                <strong>{label}</strong>
                <span className="ui-muted">{hint}</span>
                <div className="media-slot__pair">
                  <figure>
                    {liveUrl ? <img src={serverUrl(liveUrl)} alt="" /> : <div className="media-slot__empty">لا توجد</div>}
                    <figcaption>المعتمدة (الظاهرة للعامة)</figcaption>
                  </figure>
                  {pending && (
                    <figure>
                      {waitingUrl ? <img src={serverUrl(waitingUrl)} alt="" /> : <div className="media-slot__empty">—</div>}
                      <figcaption>بانتظار الموافقة</figcaption>
                    </figure>
                  )}
                </div>
                <div className="media-slot__actions">
                  <label className="ui-btn ui-btn--secondary ui-btn--sm">
                    {liveUrl || waitingUrl ? 'استبدال' : 'رفع'}
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      className="u-visually-hidden"
                      disabled={busy}
                      onChange={(event) => {
                        send(kind, event.target.files?.[0])
                        event.target.value = ''
                      }}
                    />
                  </label>
                  {waitingUrl && (
                    <Button size="sm" variant="ghost" disabled={busy}
                      onClick={() => act(() => remove(kind, true), 'تم سحب الصورة.')}>
                      سحب المعلّقة
                    </Button>
                  )}
                  {liveUrl && (
                    <Button size="sm" variant="ghost" disabled={busy}
                      onClick={() => act(() => remove(kind, false), 'تم إنزال الصورة.')}>
                      إنزال المعتمدة
                    </Button>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {canApprove && status === 'pending' && hasPending && (
          <div className="media-review">
            {rejecting ? (
              <>
                <input
                  className="ui-input"
                  placeholder="سبب الرفض (اختياري)"
                  value={reason}
                  maxLength={300}
                  onChange={(event) => setReason(event.target.value)}
                />
                <Button variant="danger" disabled={busy}
                  onClick={() => act(() => review('reject', reason), 'تم الرفض.')}>
                  تأكيد الرفض
                </Button>
                <Button variant="ghost" onClick={() => setRejecting(false)}>رجوع</Button>
              </>
            ) : (
              <>
                <Button variant="primary" disabled={busy}
                  onClick={() => act(() => review('approve'), 'تمت الموافقة، والصور ظاهرة للعامة الآن.')}>
                  موافقة ونشر
                </Button>
                <Button variant="secondary" onClick={() => setRejecting(true)}>رفض</Button>
              </>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  )
}
