import { useState } from 'react'

import { api } from '@/api'
import { Badge, Button, Card, CardBody, CardHeader, Input } from '@/components/ui'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'

/**
 * Doctors' footer requests waiting for the clinic's approval. Shown on the
 * Print design screen, and only when there is something to decide: the
 * approved version keeps printing until a new one is approved here.
 */
export function DoctorProfileRequests() {
  const toast = useToast()
  const pending = useAsync(() => api.doctorProfile.list({ status: 'pending' }), [])
  const [notes, setNotes] = useState({})
  const decide = useMutation((doctor, approve) =>
    approve ? api.doctorProfile.approve(doctor) : api.doctorProfile.reject(doctor, notes[doctor] ?? ''),
  )

  const rows = pending.data ?? []
  if (rows.length === 0) return null

  const run = async (doctor, approve) => {
    try {
      await decide.run(doctor, approve)
      toast.success(approve ? 'تم الاعتماد' : 'تم الرفض')
      pending.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  return (
    <Card>
      <CardHeader
        title="طلبات روابط الأطباء"
        subtitle="ما يعتمده الطبيب يظهر في تذييل روشتاته هو فقط، بعد موافقتك"
      />
      <CardBody>
        <div className="ui-stack">
          {rows.map((row) => (
            <div key={row.doctor} className="ui-stack" style={{ gap: 'var(--s2)' }}>
              <div className="ui-row" style={{ justifyContent: 'space-between', flexWrap: 'wrap' }}>
                <strong>{row.doctor_name}</strong>
                <Badge tone="warn">بانتظار الموافقة</Badge>
              </div>
              {row.pending?.tagline && <div>{row.pending.tagline}</div>}
              <div className="ui-row" style={{ flexWrap: 'wrap', gap: 'var(--s3)' }}>
                {row.pending_links.map((link) => (
                  <a key={link.kind} href={link.url} target="_blank" rel="noopener noreferrer" dir="ltr">
                    {link.label}: {link.text}
                  </a>
                ))}
              </div>
              <div className="ui-row" style={{ flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <Input
                  id={`reject-note-${row.doctor}`}
                  placeholder="سبب الرفض (اختياري)"
                  value={notes[row.doctor] ?? ''}
                  onChange={(event) => setNotes((current) => ({ ...current, [row.doctor]: event.target.value }))}
                />
                <Button variant="primary" size="sm" onClick={() => run(row.doctor, true)} disabled={decide.submitting}>
                  اعتماد
                </Button>
                <Button variant="ghost" size="sm" onClick={() => run(row.doctor, false)} disabled={decide.submitting}>
                  رفض
                </Button>
              </div>
            </div>
          ))}
        </div>
      </CardBody>
    </Card>
  )
}
