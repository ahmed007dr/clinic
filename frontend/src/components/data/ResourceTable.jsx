import { useEffect, useState } from 'react'

import { Card, CardBody, CardHeader, Pagination, SearchInput, Table } from '@/components/ui'
import { useList } from '@/hooks/useApi'
import { useDebounce } from '@/hooks/useDebounce'

import './data.css'

/**
 * A searchable, filterable, paginated list — the shape of eleven screens.
 *
 * Writing those eleven by hand would be eleven chances to forget the empty
 * state, the error state, or to reset the page number when a filter changes.
 * That last one is the subtle one: change a filter while on page 4 and the
 * server returns page 4 of the new result set, which is usually empty, and the
 * screen looks broken.
 *
 * `columns` is passed through to `Table`. `filters` is whatever the caller
 * wants to render in the toolbar. Anything genuinely specific to one screen —
 * a custom row action, a bulk operation — belongs in that screen, not here.
 */
export function ResourceTable({
  resource,
  columns,
  title,
  subtitle,
  actions,
  filters,
  params = {},
  searchPlaceholder = 'بحث…',
  searchable = true,
  onRowClick,
  empty,
  refreshKey,
  pageSize,
}) {
  const [page, setPage] = useState(1)
  const [query, setQuery] = useState('')
  const search = useDebounce(query, 300)

  const filterKey = JSON.stringify(params)

  // Back to page one whenever what is being listed changes. Without this a
  // filtered list lands on a page that no longer exists.
  useEffect(() => {
    setPage(1)
  }, [search, filterKey])

  const { rows, count, pages, pageSize: size, loading, error, reload } = useList(
    resource,
    {
      page,
      ...(pageSize ? { page_size: pageSize } : {}),
      ...(searchable && search ? { search } : {}),
      ...params,
    },
  )

  // Lets a parent force a refresh after it creates or deletes something.
  useEffect(() => {
    if (refreshKey !== undefined) reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey])

  return (
    <Card>
      {(title || actions) && (
        <CardHeader title={title} subtitle={subtitle} actions={actions} />
      )}

      {(searchable || filters) && (
        <div className="listing__toolbar">
          {searchable && (
            <SearchInput
              className="listing__search"
              value={query}
              onChange={setQuery}
              placeholder={searchPlaceholder}
            />
          )}
          {filters && <div className="listing__filters">{filters}</div>}
        </div>
      )}

      <CardBody flush>
        <Table
          columns={columns}
          rows={rows}
          loading={loading}
          error={error}
          onRetry={reload}
          onRowClick={onRowClick}
          empty={
            empty ?? {
              title: search ? 'لا توجد نتائج' : 'لا توجد سجلات',
              message: search
                ? `لم يُعثر على شيء يطابق «${search}».`
                : undefined,
            }
          }
        />
        <Pagination
          page={page}
          pages={pages}
          count={count}
          pageSize={size}
          onChange={setPage}
          loading={loading}
        />
      </CardBody>
    </Card>
  )
}
