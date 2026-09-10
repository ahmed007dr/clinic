import { Button } from './Button'
import { Spinner } from './Spinner'

/** The four things a data region can be, other than showing data. */

export function Loading({ message = 'جارٍ التحميل…' }) {
  return (
    <div className="ui-state">
      <Spinner size="lg" />
      <div className="ui-state__message">{message}</div>
    </div>
  )
}

export function EmptyState({ title = 'لا توجد سجلات', message, action, icon }) {
  return (
    <div className="ui-state">
      {icon && (
        <div className="ui-state__icon" aria-hidden="true">
          {icon}
        </div>
      )}
      <div className="ui-state__title">{title}</div>
      {message && <p className="ui-state__message">{message}</p>}
      {action}
    </div>
  )
}

/**
 * An error the user can act on.
 *
 * The server's own message is shown when there is one — it is written in
 * Arabic and says what was actually wrong, which is more use than a generic
 * apology. A retry is offered because most of these are transient.
 */
export function ErrorState({ error, onRetry, title = 'تعذّر تحميل البيانات' }) {
  const message =
    typeof error === 'string' ? error : error?.message || 'حدث خطأ غير متوقع.'
  return (
    <div className="ui-state">
      <div className="ui-state__icon" aria-hidden="true">
        ⚠
      </div>
      <div className="ui-state__title">{title}</div>
      <p className="ui-state__message">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          إعادة المحاولة
        </Button>
      )}
    </div>
  )
}

/** Keeps a table's height while it loads, so the page does not jump. */
export function TableSkeleton({ columns = 4, rows = 6 }) {
  return (
    <div className="ui-table-wrap" aria-busy="true">
      <table className="ui-table">
        <tbody>
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <tr key={rowIndex}>
              {Array.from({ length: columns }).map((__, columnIndex) => (
                <td key={columnIndex}>
                  <div
                    className="ui-skeleton"
                    style={{ width: columnIndex === 0 ? '60%' : '80%' }}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
