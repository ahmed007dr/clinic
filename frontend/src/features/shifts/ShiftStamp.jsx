import { formatDateTime } from '@/lib/format'

/**
 * Whose shift a payment or expense sits in, and when that shift was opened and
 * closed — the answer to "who took this money" wherever money is listed.
 */
export function ShiftStamp({ row }) {
  if (!row.shift_user_name) return <span className="ui-muted">بدون وردية</span>
  return (
    <div>
      <strong>{row.shift_user_name}</strong>
      <div className="ui-muted">
        فُتحت {formatDateTime(row.shift_opened_at)}
        {row.shift_closed_at ? ` · أُغلقت ${formatDateTime(row.shift_closed_at)}` : ' · مفتوحة الآن'}
      </div>
    </div>
  )
}
