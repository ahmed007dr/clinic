import { useEffect, useState } from 'react'

import { api } from '@/api'
import { Button, Card, CardBody, EmptyState, ErrorState, Input, Loading, Select } from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { useT } from '@/i18n'
import { today } from '@/lib/format'

import './attendance.css'

const TIMELESS = ['absent', 'leave']

/**
 * The day's attendance for the clinic — every employee, one status each,
 * saved together. A clinic Admin sees their own clinic; the Owner can switch.
 */
export function AttendanceSheetPage() {
  const { t } = useT()
  const toast = useToast()
  const { permissions } = useAuth()
  const [date, setDate] = useState(today())
  const [branch, setBranch] = useState('')
  const [rows, setRows] = useState({})

  const choices = useAsync(() => api.meta.choices(), [])
  const branches = useAsync(
    () => (permissions.all_branches ? api.branches.list({ page_size: 200 }) : Promise.resolve({ results: [] })),
    [permissions.all_branches],
  )
  const sheet = useAsync(() => api.attendance.sheet({ date, branch }), [date, branch])
  const save = useMutation((body) => api.attendance.saveSheet(body))

  useEffect(() => {
    if (!sheet.data) return
    const next = {}
    sheet.data.entries.forEach((entry) => {
      const a = entry.attendance
      next[entry.employee] = {
        status: a?.status ?? '',
        check_in: a?.check_in?.slice(0, 5) ?? '',
        check_out: a?.check_out?.slice(0, 5) ?? '',
        minutes_late: a?.minutes_late ?? '',
        notes: a?.notes ?? '',
      }
    })
    setRows(next)
  }, [sheet.data])

  const update = (employee, field, value) =>
    setRows((current) => ({ ...current, [employee]: { ...current[employee], [field]: value } }))

  const statuses = choices.data?.attendance_status ?? []

  const submit = async () => {
    const entries = Object.entries(rows)
      .filter(([, r]) => r.status)
      .map(([employee, r]) => ({
        employee,
        status: r.status,
        check_in: TIMELESS.includes(r.status) ? null : r.check_in || null,
        check_out: TIMELESS.includes(r.status) ? null : r.check_out || null,
        minutes_late: r.status === 'late' && r.minutes_late !== '' ? Number(r.minutes_late) : null,
        notes: r.notes || '',
      }))
    try {
      await save.run({ date, entries })
      toast.success(t('attendance.saved'))
      sheet.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  return (
    <>
      <PageHeader title={t('attendance.title')} subtitle={t('attendance.subtitle')}
        actions={
          <>
            <Button onClick={() => setRows((current) => Object.fromEntries(
              Object.entries(current).map(([k, r]) => [k, r.status ? r : { ...r, status: 'present' }]),
            ))}>{t('attendance.all_present')}</Button>
            <Button variant="primary" loading={save.submitting} onClick={submit}>{t('attendance.save')}</Button>
          </>
        } />

      <Card>
        <CardBody>
          <div className="attendance-filters">
            <Input label={t('common.date')} type="date" value={date} max={today()}
              onChange={(event) => setDate(event.target.value)} />
            {permissions.all_branches && (
              <Select label={t('common.clinic')} value={branch} placeholder={t('common.all_clinics')}
                options={(branches.data?.results ?? []).map((b) => ({ value: b.uuid, label: b.name }))}
                onChange={(event) => setBranch(event.target.value)} />
            )}
          </div>
        </CardBody>
      </Card>

      {sheet.error && <ErrorState error={sheet.error} onRetry={sheet.reload} />}
      {sheet.loading && !sheet.data && <Loading />}
      {sheet.data && sheet.data.entries.length === 0 && <EmptyState title={t('attendance.empty')} />}

      {sheet.data && sheet.data.entries.length > 0 && (
        <div className="attendance-list">
          {sheet.data.entries.map((entry) => {
            const row = rows[entry.employee] ?? {}
            const timeless = TIMELESS.includes(row.status)
            return (
              <Card key={entry.employee}>
                <CardBody>
                  <div className="attendance-row">
                    <div className="attendance-row__who">
                      <strong>{entry.employee_name}</strong>
                      <span className="ui-muted">{[entry.employee_type, entry.branch_name].filter(Boolean).join(' · ')}</span>
                      {!row.status && <span className="ui-muted">{t('attendance.not_recorded')}</span>}
                    </div>
                    <div className="segmented attendance-row__status" role="radiogroup" aria-label={t('attendance.status')}>
                      {statuses.map((status) => (
                        <button key={status} type="button" role="radio" aria-checked={row.status === status}
                          className={`segmented__option attendance-status--${status} ${row.status === status ? 'segmented__option--on' : ''}`}
                          onClick={() => update(entry.employee, 'status', status)}>
                          {t(`choices.attendance_status.${status}`)}
                        </button>
                      ))}
                    </div>
                    <div className="attendance-row__times">
                      <Input label={t('attendance.check_in')} type="time" value={row.check_in ?? ''} disabled={timeless}
                        onChange={(event) => update(entry.employee, 'check_in', event.target.value)} />
                      <Input label={t('attendance.check_out')} type="time" value={row.check_out ?? ''} disabled={timeless}
                        onChange={(event) => update(entry.employee, 'check_out', event.target.value)} />
                      {row.status === 'late' && (
                        <Input label={t('attendance.minutes_late')} type="number" min={0} value={row.minutes_late ?? ''}
                          onChange={(event) => update(entry.employee, 'minutes_late', event.target.value)} />
                      )}
                      <Input label={t('attendance.notes')} value={row.notes ?? ''}
                        onChange={(event) => update(entry.employee, 'notes', event.target.value)} />
                    </div>
                  </div>
                </CardBody>
              </Card>
            )
          })}
        </div>
      )}
    </>
  )
}
