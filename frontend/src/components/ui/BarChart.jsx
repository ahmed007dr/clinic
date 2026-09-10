import { useId } from 'react'

import { formatMoney, formatNumber } from '@/lib/format'

import './chart.css'

/**
 * A small bar chart, drawn directly.
 *
 * No charting library: this draws fourteen bars and a baseline, and the
 * smallest library that could do it is larger than the rest of this
 * application's JavaScript put together. Hand-drawing also means the labels
 * read right-to-left and take their colour from the theme tokens, neither of
 * which comes free from a chart library.
 *
 * `data` is `[{ label, value }]`. One scale places the bars, the axis and the
 * labels, so a bar can never disagree with the number printed under it.
 */
export function BarChart({
  data = [],
  height = 160,
  format = 'number',
  emptyMessage = 'لا توجد بيانات لهذه الفترة',
}) {
  const titleId = useId()

  if (data.length === 0) {
    return <p className="chart__empty">{emptyMessage}</p>
  }

  const values = data.map((point) => Number(point.value) || 0)
  const max = Math.max(...values, 0)
  const total = values.reduce((sum, value) => sum + value, 0)
  const formatValue = format === 'money' ? formatMoney : formatNumber

  // Everything zero is a real answer, not a missing one — a day with no
  // takings should show a flat baseline rather than an empty box.
  if (total === 0) {
    return <p className="chart__empty">{emptyMessage}</p>
  }

  return (
    <figure className="chart" role="group" aria-labelledby={titleId}>
      <figcaption id={titleId} className="u-visually-hidden">
        رسم بياني لآخر {data.length} يوم
      </figcaption>

      <div className="chart__plot" style={{ height }}>
        {data.map((point, index) => {
          const value = Number(point.value) || 0
          // A non-zero value always gets at least a sliver, so "a little" is
          // visibly different from "nothing".
          const percent = max === 0 ? 0 : (value / max) * 100
          const shown = value > 0 ? Math.max(percent, 2) : 0
          return (
            <div className="chart__column" key={index}>
              <div
                className="chart__bar"
                style={{ height: `${shown}%` }}
                title={`${point.label}: ${formatValue(value)}`}
              />
              <span className="chart__label">{point.label}</span>
            </div>
          )
        })}
      </div>

      {/* The same numbers, reachable by a screen reader and by anyone who
          wants the figure rather than the shape. */}
      <table className="u-visually-hidden">
        <tbody>
          {data.map((point, index) => (
            <tr key={index}>
              <th scope="row">{point.label}</th>
              <td>{formatValue(point.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}
