import { EmptyState, ErrorState, TableSkeleton } from './State'

/**
 * A table driven by a column definition, so every list screen renders the same
 * way and a new one is a list of columns rather than a block of markup.
 *
 * `columns` is `[{ key, header, render?, numeric?, actions? }]`.
 * `render(row)` gets the whole row, because most cells combine two fields.
 *
 * Loading, empty and error are handled here rather than in each screen. A list
 * screen that forgets one of those states is the most common way a page ends
 * up blank with no explanation.
 */
export function Table({
  columns,
  rows,
  loading = false,
  error = null,
  empty,
  onRetry,
  onRowClick,
  rowKey = (row) => row.uuid,
  caption,
}) {
  if (error) {
    return <ErrorState error={error} onRetry={onRetry} />
  }

  if (loading && rows.length === 0) {
    return <TableSkeleton columns={columns.length} />
  }

  if (!loading && rows.length === 0) {
    return (
      <EmptyState
        title={empty?.title ?? 'لا توجد سجلات'}
        message={empty?.message}
        action={empty?.action}
      />
    )
  }

  return (
    <div className="ui-table-wrap">
      <table className={`ui-table ${onRowClick ? 'ui-table--clickable' : ''}`}>
        {caption && <caption className="u-visually-hidden">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className={column.actions ? 'ui-table__cell--actions' : undefined}
                scope="col"
              >
                {column.actions ? <span className="u-visually-hidden">إجراءات</span> : column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              // Rows are reachable and activatable from the keyboard when they
              // are clickable — otherwise the whole list is mouse-only.
              tabIndex={onRowClick ? 0 : undefined}
              onKeyDown={
                onRowClick
                  ? (event) => {
                      if (event.key === 'Enter') onRowClick(row)
                    }
                  : undefined
              }
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={[
                    column.numeric && 'ui-table__cell--num',
                    column.actions && 'ui-table__cell--actions',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  // An action button inside a clickable row must not also
                  // navigate — the click would fire twice with two outcomes.
                  onClick={
                    column.actions ? (event) => event.stopPropagation() : undefined
                  }
                >
                  {column.render ? column.render(row) : row[column.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
