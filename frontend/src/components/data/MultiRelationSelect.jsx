import { useEffect, useState } from 'react'

import { Field, Input, Spinner } from '@/components/ui'
import { useDebounce } from '@/hooks/useDebounce'

/**
 * Pick one or several related records by searching.
 *
 * The many-valued sibling of `RelationSelect`'s search box: type a name (or
 * whatever the resource's `search` matches — a phone number, for doctors),
 * click a result to add it as a chip, click the chip to take it off. The value
 * is a list of UUIDs; the labels of what was chosen are kept here, since a
 * UUID alone cannot be named once it has left the search results.
 */
export function MultiRelationSelect({
  resource,
  value = [],
  onChange,
  label,
  placeholder = 'ابحث…',
  renderLabel = (row) => row.name,
  params,
}) {
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [chosen, setChosen] = useState({}) // uuid → row
  const search = useDebounce(query, 300)

  useEffect(() => {
    if (!open) return undefined
    let active = true
    setLoading(true)
    resource
      .list({ search, page_size: 20, ...(params ?? {}) })
      .then((data) => {
        if (active) setRows(data.results ?? [])
      })
      .catch(() => {
        if (active) setRows([])
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, open, resource.path, JSON.stringify(params ?? {})])

  const add = (row) => {
    setChosen((current) => ({ ...current, [row.uuid]: row }))
    onChange([...value, row.uuid])
    setQuery('')
  }
  const remove = (uuid) => onChange(value.filter((item) => item !== uuid))

  const available = rows.filter((row) => !value.includes(row.uuid))

  return (
    <Field label={label}>
      {(props) => (
        <div className="relation multi">
          {value.length > 0 && (
            <ul className="multi__chips">
              {value.map((uuid) => (
                <li key={uuid}>
                  <button
                    type="button"
                    className="multi__chip"
                    onClick={() => remove(uuid)}
                    aria-label={`إزالة ${chosen[uuid] ? renderLabel(chosen[uuid]) : ''}`}
                  >
                    {chosen[uuid] ? renderLabel(chosen[uuid]) : '…'}
                    <span aria-hidden="true"> ×</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <Input
            {...props}
            type="search"
            autoComplete="off"
            value={query}
            placeholder={placeholder}
            onFocus={() => setOpen(true)}
            onChange={(event) => {
              setQuery(event.target.value)
              setOpen(true)
            }}
            // A blur that fires before the click on an option would close the
            // list and swallow the choice.
            onBlur={() => setTimeout(() => setOpen(false), 150)}
          />
          {open && (
            <div className="relation__list" role="listbox" aria-multiselectable="true">
              {loading && (
                <div className="relation__status">
                  <Spinner /> جارٍ البحث…
                </div>
              )}
              {!loading && available.length === 0 && (
                <div className="relation__status">لا توجد نتائج</div>
              )}
              {available.map((row) => (
                <button
                  type="button"
                  key={row.uuid}
                  role="option"
                  aria-selected="false"
                  className="relation__option"
                  // mousedown, not click: the input's blur would otherwise
                  // close the list first and the choice would never land.
                  onMouseDown={(event) => {
                    event.preventDefault()
                    add(row)
                  }}
                >
                  <span>{renderLabel(row)}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </Field>
  )
}
