import { StatTile, Table } from '@/components/ui'
import { formatMoney } from '@/lib/format'

/**
 * A shift's money, per payment method: in, out, net — then the totals and the
 * balance expected at the end (opening + net). The same figures the server
 * freezes at closing (billing/shifts.py `summarize`), so what the cashier saw
 * when they closed and what management reviews read identically.
 */
export function ShiftSummary({ summary }) {
  if (!summary) return null
  return (
    <div className="ui-stack">
      <div className="ui-grid">
        <StatTile label="الرصيد الافتتاحي" value={formatMoney(summary.opening_balance)} icon="🏦" />
        <StatTile label="الإيراد" value={formatMoney(summary.revenue)} tone="ok" icon="⬇" />
        <StatTile label="المصروف" value={formatMoney(summary.expenses)} icon="⬆" />
        <StatTile
          label="الرصيد المتوقع"
          value={formatMoney(summary.expected_balance)}
          hint={`الصافي: ${formatMoney(summary.net)}`}
          tone="primary"
          icon="🧮"
        />
      </div>
      <Table
        columns={[
          { key: 'method', header: 'طريقة الدفع' },
          {
            key: 'revenue',
            header: 'الإيراد',
            numeric: true,
            render: (row) => `${formatMoney(row.revenue)} (${row.payments_count})`,
          },
          {
            key: 'expenses',
            header: 'المصروف',
            numeric: true,
            render: (row) => `${formatMoney(row.expenses)} (${row.expenses_count})`,
          },
          {
            key: 'net',
            header: 'الصافي',
            numeric: true,
            render: (row) => <strong>{formatMoney(row.net)}</strong>,
          },
        ]}
        rows={summary.by_method.map((row) => ({ ...row, uuid: row.method }))}
        empty={{ title: 'لا مبالغ بعد', message: 'لم تُسجَّل دفعات أو مصروفات في هذه الوردية.' }}
      />
    </div>
  )
}
