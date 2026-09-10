import { Link, useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import {
  APPOINTMENT_TONES,
  BarChart,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  ErrorState,
  Input,
  Loading,
  StatTile,
  Table,
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync } from '@/hooks/useApi'
import { useT } from '@/i18n'
import { formatMoney, formatNumber, startOfMonth, today } from '@/lib/format'

import './owner.css'

/**
 * The group owner's view of every clinic, with a clinic switcher.
 *
 * The filters live in the URL, so a view can be bookmarked, reloaded or sent
 * to someone, and the quick links into a clinic's own screens carry the
 * clinic with them. Every figure comes from `/api/owner/overview/`, computed
 * server-side from the real tables.
 */
export function OwnerDashboardPage() {
  const { t } = useT()
  const [params, setParams] = useSearchParams()
  const from = params.get('from') || startOfMonth()
  const to = params.get('to') || today()
  const branch = params.get('branch') || ''

  const update = (key, value) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  const { data, loading, error, reload } = useAsync(
    () => api.owner.overview({ from, to, branch }),
    [from, to, branch],
  )

  return (
    <>
      <PageHeader title={t('owner.title')} subtitle={t('owner.subtitle')} />

      <Card className="owner-filters">
        <CardBody>
          <div className="owner-filters__row">
            <div className="clinic-switcher" role="tablist" aria-label={t('common.clinic')}>
              <button type="button" role="tab" aria-selected={!branch}
                className={`clinic-switcher__chip ${!branch ? 'clinic-switcher__chip--on' : ''}`}
                onClick={() => update('branch', '')}>{t('common.all_clinics')}</button>
              {(data?.branches ?? []).map((b) => (
                <button key={b.uuid} type="button" role="tab" aria-selected={branch === b.uuid}
                  className={`clinic-switcher__chip ${branch === b.uuid ? 'clinic-switcher__chip--on' : ''}`}
                  onClick={() => update('branch', b.uuid)}>{b.name}</button>
              ))}
            </div>
            <div className="owner-filters__dates">
              <Input label={t('common.from')} type="date" value={from} max={to}
                onChange={(event) => update('from', event.target.value)} />
              <Input label={t('common.to')} type="date" value={to} min={from}
                onChange={(event) => update('to', event.target.value)} />
            </div>
          </div>
        </CardBody>
      </Card>

      {error && <ErrorState error={error} onRetry={reload} />}
      {!data && loading && <Loading />}
      {data && <Overview data={data} branch={branch} onFocus={(uuid) => update('branch', uuid)} />}
    </>
  )
}

function Overview({ data, branch, onFocus }) {
  const { t } = useT()
  const { finance, patients, appointments } = data
  const choice = (group, code) => t(`choices.${group}.${code}`)
  const day = (value) => String(new Date(value).getDate())
  const link = (path, uuid) => `${path}?branch=${uuid}`

  return (
    <div className="ui-stack">
      <div className="ui-grid owner-tiles">
        <StatTile label={t('owner.revenue')} value={formatMoney(finance.revenue)}
          hint={t('owner.payments_count', { n: formatNumber(finance.payments) })} />
        <StatTile label={t('owner.expenses')} value={formatMoney(finance.expenses)} />
        <StatTile label={t('owner.net')} value={formatMoney(finance.net)} tone={Number(finance.net) >= 0 ? 'ok' : 'urgent'} />
        <StatTile label={t('owner.collected')} value={formatMoney(finance.collected)}
          hint={`${t('owner.billed')}: ${formatMoney(finance.billed)} · ${t('owner.outstanding')}: ${formatMoney(finance.outstanding)}`}
          tone={Number(finance.outstanding) > 0 ? 'warn' : 'neutral'} />
        <StatTile label={t('owner.patients_new')} value={formatNumber(patients.new)}
          hint={`${t('owner.patients_returning')}: ${formatNumber(patients.returning)} · ${t('owner.patients_total')}: ${formatNumber(patients.total)}`} />
        <StatTile label={t('owner.appointments_today')} value={formatNumber(appointments.today)}
          hint={`${t('owner.upcoming')}: ${formatNumber(appointments.upcoming_7_days)}`} />
        <StatTile label={t('owner.attendance_rate')}
          value={data.attendance.rate === null ? '—' : `${data.attendance.rate}%`}
          hint={`${t('owner.col.absent')}: ${data.attendance.absent} · ${t('owner.col.late')}: ${data.attendance.late}`} />
        {patients.pending_review > 0 && (
          <StatTile label={t('owner.patients_pending')} value={formatNumber(patients.pending_review)}
            tone="warn" to="/patients/review" />
        )}
      </div>

      <Card>
        <CardHeader title={t('owner.clinics_title')} />
        <CardBody flush>
          <Table
            rows={data.clinics}
            empty={{ title: t('owner.no_data') }}
            columns={[
              { key: 'name', header: t('owner.col.clinic'), render: (c) => <strong>{c.name}</strong> },
              { key: 'revenue', header: t('owner.col.revenue'), numeric: true, render: (c) => formatMoney(c.revenue) },
              { key: 'expenses', header: t('owner.col.expenses'), numeric: true, render: (c) => formatMoney(c.expenses) },
              { key: 'net', header: t('owner.col.net'), numeric: true,
                render: (c) => <span className={Number(c.net) < 0 ? 'owner-negative' : ''}>{formatMoney(c.net)}</span> },
              { key: 'appointments', header: t('owner.col.appointments'), numeric: true },
              { key: 'completed', header: t('owner.col.completed'), numeric: true },
              { key: 'no_show', header: t('owner.col.no_show'), numeric: true },
              { key: 'new_patients', header: t('owner.col.new_patients'), numeric: true },
              { key: 'doctors', header: t('owner.col.doctors'), numeric: true },
              { key: 'attendance_rate', header: t('owner.col.attendance'), numeric: true,
                render: (c) => (c.attendance_rate === null ? '—' : `${c.attendance_rate}%`) },
              {
                key: '__links', actions: true,
                render: (c) => (
                  <div className="ui-row owner-links">
                    {branch !== c.uuid && (
                      <Button size="sm" variant="ghost" onClick={() => onFocus(c.uuid)}>{t('owner.focus_clinic')}</Button>
                    )}
                    <Link to={link('/patients', c.uuid)}>{t('owner.link.patients')}</Link>
                    <Link to={link('/appointments', c.uuid)}>{t('owner.link.appointments')}</Link>
                    <Link to={link('/payments', c.uuid)}>{t('owner.link.payments')}</Link>
                  </div>
                ),
              },
            ]}
            rowKey={(c) => c.uuid}
          />
        </CardBody>
      </Card>

      <div className="ui-grid ui-grid--2">
        <Card>
          <CardHeader title={t('owner.trend_revenue')} />
          <CardBody>
            <BarChart format="money" data={data.series.map((p) => ({ label: day(p.date), value: p.revenue }))}
              emptyMessage={t('owner.no_data')} />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title={t('owner.trend_expenses')} />
          <CardBody>
            <BarChart format="money" data={data.series.map((p) => ({ label: day(p.date), value: p.expenses }))}
              emptyMessage={t('owner.no_data')} />
          </CardBody>
        </Card>
      </div>

      <div className="ui-grid ui-grid--3 owner-breakdowns">
        <Breakdown title={t('owner.by_doctor')} rows={data.revenue_by_doctor}
          label={(r) => r.name || t('owner.unassigned')} value={(r) => formatMoney(r.total)} />
        <Breakdown title={t('owner.by_specialty')} rows={data.revenue_by_specialty}
          label={(r) => r.name || t('owner.unassigned')} value={(r) => formatMoney(r.total)} />
        <Breakdown title={t('owner.by_category')} rows={data.expense_by_category}
          label={(r) => r.name || t('owner.unassigned')} value={(r) => formatMoney(r.total)} />
      </div>

      <div className="ui-grid ui-grid--3 owner-breakdowns">
        <Card>
          <CardHeader title={t('owner.appointments_title')} />
          <CardBody>
            <ul className="owner-statuses">
              {Object.entries(appointments.by_status).map(([status, n]) => (
                <li key={status}>
                  <Badge tone={APPOINTMENT_TONES[status] ?? 'neutral'}>{choice('appointment_status', status)}</Badge>
                  <span className="ui-num">{formatNumber(n)}</span>
                </li>
              ))}
            </ul>
            {Object.keys(appointments.by_status).length === 0 && <p className="ui-muted">{t('owner.no_data')}</p>}
          </CardBody>
        </Card>
        <Breakdown title={t('owner.referral_title')}
          rows={Object.entries(patients.by_referral_source).map(([code, n]) => ({ code, n }))}
          label={(r) => (r.code === 'unknown' ? t('owner.source_unknown') : choice('referral_source', r.code))}
          value={(r) => formatNumber(r.n)} />
        <Breakdown title={t('owner.cases_title')}
          rows={Object.entries(data.cases.by_case_type).map(([code, n]) => ({ code, n }))}
          label={(r) => choice('case_type', r.code)} value={(r) => formatNumber(r.n)} />
      </div>

      <Card>
        <CardHeader title={t('owner.doctors_title')} />
        <CardBody flush>
          <Table
            rows={data.doctors}
            rowKey={(d) => d.uuid}
            empty={{ title: t('owner.no_data') }}
            columns={[
              { key: 'name', header: t('owner.col.name') },
              { key: 'branch', header: t('owner.col.clinic'), render: (d) => d.branch || '—' },
              { key: 'appointments', header: t('owner.col.appointments'), numeric: true },
              { key: 'completed', header: t('owner.col.completed'), numeric: true },
              { key: 'no_show', header: t('owner.col.no_show'), numeric: true },
              { key: 'present', header: t('owner.col.present'), numeric: true },
              { key: 'late', header: t('owner.col.late'), numeric: true },
              { key: 'absent', header: t('owner.col.absent'), numeric: true },
              { key: 'leave', header: t('owner.col.leave'), numeric: true },
            ]}
          />
        </CardBody>
      </Card>
    </div>
  )
}

function Breakdown({ title, rows, label, value }) {
  const { t } = useT()
  return (
    <Card>
      <CardHeader title={title} />
      <CardBody>
        {rows.length === 0 ? (
          <p className="ui-muted">{t('owner.no_data')}</p>
        ) : (
          <ul className="owner-breakdown">
            {rows.map((row, index) => (
              <li key={index}>
                <span>{label(row)}</span>
                <strong className="ui-num">{value(row)}</strong>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  )
}
