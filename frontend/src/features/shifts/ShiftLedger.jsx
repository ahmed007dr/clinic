import { Badge, Card, CardBody, CardHeader, Table } from '@/components/ui'
import { formatDateTime, formatMoney } from '@/lib/format'

/**
 * Everything the shift holds, as it stands: the bookings made in it with what
 * is paid and what is still owed, every payment, every expense. Counting the
 * drawer at any moment means comparing the cash against this — so it lists the
 * records themselves, not only totals.
 */
export function ShiftLedger({ shift, live = false }) {
  const bookings = shift.bookings ?? []
  const payments = shift.payments ?? []
  const expenses = shift.expenses ?? []
  return (
    <>
      <Card>
        <CardHeader title="الحجوزات" subtitle={`${bookings.length} حجز${live ? ' · تُحدَّث تلقائياً' : ''}`} />
        <CardBody flush>
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
      </Card>

      <Card>
        <CardHeader title="الدفعات" subtitle={`${payments.length} دفعة`} />
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
      </Card>

      <Card>
        <CardHeader title="المصروفات" subtitle={`${expenses.length} مصروف`} />
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
      </Card>
    </>
  )
}
