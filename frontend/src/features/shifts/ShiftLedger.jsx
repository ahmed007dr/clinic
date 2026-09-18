import { useState } from 'react'

import { Badge, Card, CardBody, CardHeader, Table, Tabs } from '@/components/ui'
import { formatDateTime, formatMoney } from '@/lib/format'

import { ShiftSummary } from './ShiftSummary'

/**
 * A shift in tabs: the count of the drawer first, then the bookings made in it
 * (with what is paid and what is still owed), every payment, every expense —
 * each newest first. Counting the drawer at any moment means comparing the
 * cash against this, so it lists the records themselves, not only totals.
 *
 * `summaries` are the leading tabs, `[{ id, label, summary, note? }]`: the
 * cashier has one ("الجرد"); management also gets the summary frozen at
 * closing. The chosen tab survives the open shift's refresh, because this
 * component stays mounted while its data is replaced.
 */
export function ShiftTabs({ shift, summaries, title, subtitle, actions, live = false }) {
  const bookings = shift.bookings ?? []
  const payments = shift.payments ?? []
  const expenses = shift.expenses ?? []
  const [tab, setTab] = useState(summaries[0].id)

  const owing = bookings.filter((row) => Number(row.amount_due) > 0).length
  const items = [
    ...summaries.map(({ id, label }) => ({ id, label })),
    { id: 'bookings', label: 'الحجوزات', badge: bookings.length },
    { id: 'payments', label: 'الدفعات', badge: payments.length },
    { id: 'expenses', label: 'المصروفات', badge: expenses.length },
  ]
  const summary = summaries.find((item) => item.id === tab)

  return (
    <Card>
      <CardHeader
        title={title}
        subtitle={subtitle ?? (live ? 'تُحدَّث تلقائياً' : undefined)}
        actions={actions}
      />
      <div style={{ paddingInline: 'var(--s4)' }}>
        <Tabs items={items} active={tab} onChange={setTab} />
      </div>

      {summary && (
        <CardBody>
          {summary.note && <p className="ui-muted">{summary.note}</p>}
          <ShiftSummary summary={summary.summary} />
        </CardBody>
      )}

      {tab === 'bookings' && (
        <CardBody flush>
          {owing > 0 && (
            <p className="ui-muted" style={{ padding: 'var(--s3) var(--s4) 0' }}>
              {owing} حجز عليه متبقٍّ لم يُسدَّد بعد.
            </p>
          )}
          <Table
            columns={[
              { key: 'serial_number', header: 'الرقم', numeric: true },
              { key: 'patient_name', header: 'المريض' },
              {
                key: 'service_name',
                header: 'الخدمة',
                render: (row) => (
                  <>
                    {row.service_name || '—'}
                    {row.doctor_name && <div className="ui-muted">{row.doctor_name}</div>}
                  </>
                ),
              },
              {
                key: 'net_price',
                header: 'المطلوب',
                numeric: true,
                render: (row) => (
                  <>
                    {formatMoney(row.net_price)}
                    {Number(row.discount) > 0 && <div className="ui-muted">خصم {formatMoney(row.discount)}</div>}
                  </>
                ),
              },
              { key: 'paid_total', header: 'المدفوع', numeric: true, render: (row) => formatMoney(row.paid_total) },
              {
                key: 'amount_due',
                header: 'المتبقي',
                numeric: true,
                render: (row) =>
                  Number(row.amount_due) > 0 ? (
                    <Badge tone="warn">{formatMoney(row.amount_due)}</Badge>
                  ) : (
                    <Badge tone="ok">مسدد</Badge>
                  ),
              },
              { key: 'status_label', header: 'الحالة' },
            ]}
            rows={bookings}
            empty={{ title: 'لا حجوزات', message: 'ستظهر هنا الحجوزات التي تُسجَّل في هذه الوردية.' }}
          />
        </CardBody>
      )}

      {tab === 'payments' && (
        <CardBody flush>
          <Table
            columns={[
              { key: 'receipt_number', header: 'الإيصال', numeric: true },
              { key: 'date', header: 'الوقت', render: (row) => formatDateTime(row.date) },
              { key: 'patient_name', header: 'المريض' },
              { key: 'appointment_serial', header: 'الحجز', render: (row) => row.appointment_serial || '—' },
              { key: 'method_name', header: 'الطريقة', render: (row) => row.method_name || '—' },
              {
                key: 'amount',
                header: 'المبلغ',
                numeric: true,
                render: (row) => <strong>{formatMoney(row.amount)}</strong>,
              },
            ]}
            rows={payments}
            empty={{ title: 'لا دفعات' }}
          />
        </CardBody>
      )}

      {tab === 'expenses' && (
        <CardBody flush>
          <Table
            columns={[
              { key: 'category_name', header: 'البند', render: (row) => row.category_name || '—' },
              { key: 'method_name', header: 'الطريقة', render: (row) => row.method_name || '—' },
              { key: 'notes', header: 'ملاحظات', render: (row) => row.notes || '—' },
              {
                key: 'amount',
                header: 'المبلغ',
                numeric: true,
                render: (row) => <strong>{formatMoney(row.amount)}</strong>,
              },
            ]}
            rows={expenses}
            empty={{ title: 'لا مصروفات' }}
          />
        </CardBody>
      )}
    </Card>
  )
}
