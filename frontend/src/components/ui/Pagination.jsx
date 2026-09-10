import { Button } from './Button'

/**
 * Page controls that also say where you are.
 *
 * The count matters as much as the arrows: "١٢٠ سجل" tells a receptionist
 * whether their search worked, which "الصفحة ١ من ٥" alone does not.
 *
 * In RTL the *previous* page is on the right, so the arrows are written to
 * follow the reading direction rather than the Latin convention.
 */
export function Pagination({ page, pages, count, pageSize, onChange, loading }) {
  if (!count) return null

  const first = (page - 1) * pageSize + 1
  const last = Math.min(page * pageSize, count)

  return (
    <div className="ui-pagination">
      <span>
        {count > pageSize
          ? `${first}–${last} من ${count}`
          : `${count} ${count === 1 ? 'سجل' : 'سجل'}`}
      </span>

      {pages > 1 && (
        <div className="ui-pagination__pages">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onChange(page - 1)}
            disabled={page <= 1 || loading}
            aria-label="الصفحة السابقة"
          >
            ›
          </Button>
          <span className="ui-num">
            {page} / {pages}
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onChange(page + 1)}
            disabled={page >= pages || loading}
            aria-label="الصفحة التالية"
          >
            ‹
          </Button>
        </div>
      )}
    </div>
  )
}
