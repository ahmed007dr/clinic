import { useEffect, useState } from 'react'

import { api } from '@/api'
import { Badge, Button, Card, CardBody, CardHeader, Input, Loading } from '@/components/ui'
import { LinkFields } from '@/features/admin/LinkFields'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'

const STATUS = {
  pending: { label: 'بانتظار موافقة الإدارة', tone: 'warn' },
  approved: { label: 'معتمد ويظهر في روشتاتك', tone: 'ok' },
  rejected: { label: 'مرفوض', tone: 'urgent' },
}

/**
 * The doctor's own line and links under their name on their prescriptions.
 * They write it here; it prints only after the clinic's Admin approves it
 * (api/views/doctor_profile.py), and the last approved version keeps
 * printing while a change is waiting.
 */
export function MyPrescriptionFooter() {
  const toast = useToast()
  const profile = useAsync(() => api.doctorProfile.mine(), [])
  const [tagline, setTagline] = useState('')
  const [links, setLinks] = useState({})
  const save = useMutation(() => api.doctorProfile.save({ tagline, links }))

  useEffect(() => {
    if (!profile.data) return
    const draft = profile.data.pending ?? profile.data.approved ?? {}
    setTagline(draft.tagline ?? '')
    setLinks({ ...(draft.links ?? {}) })
  }, [profile.data])

  if (profile.loading && !profile.data) return <Loading />
  if (profile.error) return null // not a linked doctor account

  const data = profile.data
  const status = STATUS[data.status]

  const submit = async () => {
    try {
      await save.run()
      toast.success('أُرسلت للإدارة للموافقة')
      profile.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  return (
    <Card>
      <CardHeader
        title="روابطي في الروشتة"
        subtitle="سطر تعريفي وروابطك تحت اسمك في روشتاتك — بعد موافقة إدارة العيادة"
        actions={status && <Badge tone={status.tone}>{status.label}</Badge>}
      />
      <CardBody>
        <div className="ui-stack">
          {data.status === 'rejected' && data.note && <div className="form-error">سبب الرفض: {data.note}</div>}
          <Input
            id="doctor-tagline"
            label="سطر تعريفي"
            placeholder="مثل: استشاري الأمراض الجلدية والتجميل"
            value={tagline}
            onChange={(event) => setTagline(event.target.value)}
          />
          <LinkFields kinds={data.link_kinds} value={links} onChange={setLinks} />
          {data.approved_links?.length > 0 && data.status === 'pending' && (
            <p className="ui-muted">حتى الموافقة، تظهر في روشتاتك النسخة المعتمدة السابقة.</p>
          )}
          <div className="form-actions">
            <Button variant="primary" onClick={submit} loading={save.submitting}>
              إرسال للموافقة
            </Button>
          </div>
        </div>
      </CardBody>
    </Card>
  )
}
