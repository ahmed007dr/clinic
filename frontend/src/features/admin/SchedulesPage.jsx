import { useEffect, useState } from 'react'

import { api } from '@/api'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button, Card, CardBody, Select } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'

import './schedules.css'

// The week as clinics count it — Saturday first. `weekday` follows the server: Monday 0 … Sunday 6.
const WEEK = [
  { weekday: 5, label: 'السبت' },
  { weekday: 6, label: 'الأحد' },
  { weekday: 0, label: 'الاثنين' },
  { weekday: 1, label: 'الثلاثاء' },
  { weekday: 2, label: 'الأربعاء' },
  { weekday: 3, label: 'الخميس' },
  { weekday: 4, label: 'الجمعة' },
]

const EMPTY = { on: false, start_time: '09:00', end_time: '17:00', break_start: '', break_end: '' }

function toRows(days) {
  const byDay = Object.fromEntries((days ?? []).map((d) => [d.weekday, d]))
  return Object.fromEntries(
    WEEK.map(({ weekday }) => {
      const d = byDay[weekday]
      return [
        weekday,
        d
          ? { on: true, start_time: d.start_time, end_time: d.end_time, break_start: d.break_start ?? '', break_end: d.break_end ?? '' }
          : { ...EMPTY },
      ]
    }),
  )
}

/**
 * When each doctor works at each clinic (docs/15, Phase 4, D7): a weekly pattern,
 * one break a day. The website offers a customer times only inside these hours,
 * minus the doctor's time off, the clinic's holidays and what is already booked.
 * Reception can still book any time by hand. The Owner picks any clinic; an Admin
 * sees their own. A doctor who works at two clinics has a week at each.
 */
export function SchedulesPage() {
  const toast = useToast()
  const [branch, setBranch] = useState('')
  const [doctor, setDoctor] = useState('')
  const { data, loading, error, reload } = useAsync(
    () => api.schedules.get({ branch: branch || undefined, doctor: doctor || undefined }),
    [branch, doctor],
  )
  const [rows, setRows] = useState(toRows([]))
  const [saving, setSaving] = useState(false)
  const [problem, setProblem] = useState(null)

  useEffect(() => setRows(toRows(data?.days)), [data])

  const set = (weekday, name, value) =>
    setRows((previous) => ({ ...previous, [weekday]: { ...previous[weekday], [name]: value } }))

  const save = async () => {
    setSaving(true)
    setProblem(null)
    try {
      const days = WEEK.filter(({ weekday }) => rows[weekday].on).map(({ weekday }) => {
        const r = rows[weekday]
        return {
          weekday,
          start_time: r.start_time,
          end_time: r.end_time,
          break_start: r.break_start || null,
          break_end: r.break_end || null,
        }
      })
      await api.schedules.save({ branch: data.branch.uuid, doctor: data.doctor, days })
      toast.success('تم حفظ مواعيد الطبيب.')
      reload()
    } catch (caught) {
      const detail = caught.fields?.days ?? caught.fields?.detail
      setProblem(detail ? [].concat(detail).map((d) => (typeof d === 'string' ? d : JSON.stringify(d))).join(' ') : caught.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <PageHeader
        title="مواعيد الأطباء"
        subtitle="أيام وساعات عمل كل طبيب في كل عيادة، بفترة راحة واحدة يوميًا. منها تُقسَّم الأوقات المتاحة للحجز من الموقع."
      />
      <Card>
        <CardBody>
          <div className="schedule-pickers">
            {data?.branches?.length > 1 && (
              <Select
                label="العيادة"
                value={data.branch?.uuid ?? ''}
                options={data.branches.map((b) => ({ value: b.uuid, label: b.name }))}
                onChange={(event) => { setBranch(event.target.value); setDoctor('') }}
              />
            )}
            <Select
              label="الطبيب"
              value={data?.doctor ?? ''}
              placeholder="— اختر الطبيب —"
              options={(data?.doctors ?? []).map((d) => ({ value: d.uuid, label: d.name }))}
              onChange={(event) => setDoctor(event.target.value)}
            />
          </div>
        </CardBody>
      </Card>

      {error && <div className="form-error" role="alert">{error.message}</div>}
      {!loading && data?.doctor && (
        <Card>
          <CardBody>
            {problem && <div className="form-error" role="alert">{problem}</div>}
            <table className="ui-table schedule-table">
              <thead>
                <tr>
                  <th>اليوم</th>
                  <th>يعمل</th>
                  <th>من</th>
                  <th>إلى</th>
                  <th>راحة من</th>
                  <th>راحة إلى</th>
                </tr>
              </thead>
              <tbody>
                {WEEK.map(({ weekday, label }) => {
                  const row = rows[weekday]
                  return (
                    <tr key={weekday}>
                      <td><strong>{label}</strong></td>
                      <td>
                        <input type="checkbox" aria-label={`يعمل يوم ${label}`} checked={row.on}
                          onChange={(e) => set(weekday, 'on', e.target.checked)} />
                      </td>
                      {['start_time', 'end_time', 'break_start', 'break_end'].map((name) => (
                        <td key={name}>
                          <input type="time" className="ui-input" dir="ltr" value={row[name]} disabled={!row.on}
                            onChange={(e) => set(weekday, name, e.target.value)} />
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <div className="schedule-actions">
              <Button variant="primary" onClick={save} loading={saving}>حفظ</Button>
              <span className="ui-muted">الأيام غير المعلَّمة إجازة أسبوعية للطبيب في هذه العيادة.</span>
            </div>
          </CardBody>
        </Card>
      )}
    </>
  )
}
