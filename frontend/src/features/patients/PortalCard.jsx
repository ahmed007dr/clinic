import { useState } from 'react'

import { api } from '@/api'
import { Badge, Button, Card, CardBody, CardHeader, ConfirmDialog } from '@/components/ui'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { formatDateTime } from '@/lib/format'

/**
 * The patient's portal access, from the front desk.
 *
 * The invitation link is shown once: only its hash is stored, so closing this
 * card loses it and a new one has to be issued — which also cancels the old.
 */
export function PortalCard({ patientUuid, hasPhone }) {
  const toast = useToast()
  const { data, reload } = useAsync(() => api.patients.portalStatus(patientUuid), [patientUuid])
  const invite = useMutation(() => api.patients.portalInvite(patientUuid))
  const revoke = useMutation(() => api.patients.portalRevoke(patientUuid))
  const [link, setLink] = useState(null)
  const [confirming, setConfirming] = useState(false)

  const issue = async () => {
    try {
      const result = await invite.run()
      setLink(result.url)
      reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link)
      toast.success('تم نسخ الرابط')
    } catch {
      toast.warn('انسخ الرابط يدوياً')
    }
  }

  const state = !data
    ? null
    : data.has_account
      ? data.is_active
        ? { tone: 'ok', label: 'مفعّل' }
        : { tone: 'neutral', label: 'موقوف' }
      : { tone: 'neutral', label: 'لا يوجد حساب' }

  return (
    <Card>
      <CardHeader title="بوابة المرضى" actions={state && <Badge tone={state.tone}>{state.label}</Badge>} />
      <CardBody>
        <div className="ui-stack" style={{ gap: 'var(--s3)' }}>
          {data?.last_login && (
            <span className="ui-muted" style={{ fontSize: 'var(--text-sm)' }}>
              آخر دخول: {formatDateTime(data.last_login)}
            </span>
          )}
          {data?.invite_expires_at && !link && (
            <span className="ui-muted" style={{ fontSize: 'var(--text-sm)' }}>
              دعوة سابقة صالحة حتى {formatDateTime(data.invite_expires_at)}
            </span>
          )}

          {link ? (
            <div className="ui-stack" style={{ gap: 'var(--s2)' }}>
              <input className="ui-input" dir="ltr" readOnly value={link} onFocus={(e) => e.target.select()} />
              <Button size="sm" variant="primary" onClick={copy}>
                نسخ الرابط
              </Button>
              <span className="ui-muted" style={{ fontSize: 'var(--text-xs)' }}>
                صالح ٧٢ ساعة ولمرة واحدة. أرسله للمريض على هاتفه.
              </span>
            </div>
          ) : (
            <Button size="sm" onClick={issue} loading={invite.submitting} disabled={!hasPhone}>
              {data?.has_account ? 'رابط دعوة جديد' : 'دعوة للبوابة'}
            </Button>
          )}
          {!hasPhone && (
            <span className="ui-muted" style={{ fontSize: 'var(--text-xs)' }}>
              سجّل رقم هاتف المريض أولاً — الدخول يتم برقم الهاتف.
            </span>
          )}

          {data?.has_account && data.is_active && (
            <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>
              إيقاف الوصول
            </Button>
          )}
        </div>
      </CardBody>

      <ConfirmDialog
        open={confirming}
        onClose={() => setConfirming(false)}
        loading={revoke.submitting}
        title="إيقاف وصول المريض"
        message="سيُسجَّل خروج المريض من البوابة فوراً ولن يستطيع الدخول حتى تُرسل له دعوة جديدة."
        confirmLabel="إيقاف الوصول"
        onConfirm={async () => {
          try {
            await revoke.run()
            toast.success('تم إيقاف الوصول')
            setLink(null)
            reload()
          } catch (error) {
            toast.error(error.message)
          } finally {
            setConfirming(false)
          }
        }}
      />
    </Card>
  )
}
