import { useEffect, useMemo, useState } from 'react'

import { Field, Input, Select, Spinner } from '@/components/ui'
import { useDebounce } from '@/hooks/useDebounce'

/**
 * Pick a related record by UUID.
 *
 * Two behaviours in one component, chosen by how many rows there are:
 *
 * - A **plain select** for short, stable lists — branches, services, payment
 *   methods. Everything is loaded once and the browser's own select is used,
 *   which is faster to operate and works on a phone.
 * - A **search box** (`searchable`) for lists that are unbounded — patients
 *   above all. Loading every patient into a dropdown is how a clinic's second
 *   year makes the booking form unusable.
 *
 * Either way the value sent is a UUID, and the choices come from the server
 * already scoped to the caller's clinic and branch — so this component never
 * has to know anything about who is allowed to see what.
 */
export function RelationSelect({
  resource,
  value,
  onChange,
  label,
  error,
  required,
  placeholder = '— اختر —',
  searchable = false,
  labelKey = 'name',
  params,
  hint,
  disabled,
}) {
  if (searchable) {
    return (
      <SearchableRelation
        resource={resource}
        value={value}
        onChange={onChange}
        label={label}
        error={error}
        required={required}
        placeholder={placeholder}
        labelKey={labelKey}
        params={params}
        hint={hint}
        disabled={disabled}
      />
    )
  }
  return (
    <SimpleRelation
      resource={resource}
      value={value}
      onChange={onChange}
      label={label}
      error={error}
      required={required}
      placeholder={placeholder}
      labelKey={labelKey}
      params={params}
      hint={hint}
      disabled={disabled}
    />
  )
}

function SimpleRelation({
  resource,
  value,
  onChange,
  label,
  error,
  required,
  placeholder,
  labelKey,
  params,
  hint,
  disabled,
}) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const key = JSON.stringify(params ?? {})

  useEffect(() => {
    let active = true
    setLoading(true)
    // A generous page size, because this form is unusable if the option the
    // user needs happens to be on page two of a dropdown.
    resource
      .list({ page_size: 200, ...(params ?? {}) })
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
  }, [resource.path, key])

  const options = useMemo(
    () => rows.map((row) => ({ value: row.uuid, label: row[labelKey] ?? row.name })),
    [rows, labelKey],
  )

  return (
    <Select
      label={label}
      error={error}
      hint={hint}
      required={required}
      placeholder={loading ? 'جارٍ التحميل…' : placeholder}
      options={options}
      value={value ?? ''}
      disabled={disabled || loading}
      onChange={(event) => onChange(event.target.value || null)}
    />
  )
}

function SearchableRelation({
  resource,
  value,
  onChange,
  label,
  error,
  required,
  placeholder,
  labelKey,
  params,
  hint,
  disabled,
}) {
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState(null)
  const [open, setOpen] = useState(false)
  const search = useDebounce(query, 300)

  // A form opened for editing arrives with a UUID and no label, so the chosen
  // record has to be fetched before it can be named.
  useEffect(() => {
    let active = true
    if (!value) {
      setSelected(null)
      return undefined
    }
    if (selected?.uuid === value) return undefined
    resource
      .get(value)
      .then((row) => {
        if (active) setSelected(row)
      })
      .catch(() => {
        if (active) setSelected(null)
      })
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, resource.path])

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

  const choose = (row) => {
    setSelected(row)
    onChange(row.uuid)
    setOpen(false)
    setQuery('')
  }

  return (
    <Field label={label} error={error} required={required} hint={hint}>
      {(props) => (
        <div className="relation">
          {selected && !open ? (
            <div className="relation__chosen">
              <span className="relation__name">
                {selected[labelKey] ?? selected.name}
                {selected.serial_number && (
                  <span className="ui-muted"> · {selected.serial_number}</span>
                )}
              </span>
              {!disabled && (
                <button
                  type="button"
                  className="relation__change"
                  onClick={() => {
                    setOpen(true)
                    setSelected(null)
                    onChange(null)
                  }}
                >
                  تغيير
                </button>
              )}
            </div>
          ) : (
            <>
              <Input
                {...props}
                type="search"
                autoComplete="off"
                value={query}
                disabled={disabled}
                placeholder={placeholder}
                onFocus={() => setOpen(true)}
                onChange={(event) => {
                  setQuery(event.target.value)
                  setOpen(true)
                }}
                // A blur that fires before the click on an option would close
                // the list and swallow the choice.
                onBlur={() => setTimeout(() => setOpen(false), 150)}
              />
              {open && (
                <div className="relation__list" role="listbox">
                  {loading && (
                    <div className="relation__status">
                      <Spinner /> جارٍ البحث…
                    </div>
                  )}
                  {!loading && rows.length === 0 && (
                    <div className="relation__status">لا توجد نتائج</div>
                  )}
                  {rows.map((row) => (
                    <button
                      type="button"
                      key={row.uuid}
                      role="option"
                      aria-selected={row.uuid === value}
                      className="relation__option"
                      onClick={() => choose(row)}
                    >
                      <span>{row[labelKey] ?? row.name}</span>
                      {row.serial_number && (
                        <span className="ui-muted">{row.serial_number}</span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </Field>
  )
}
