import { useState } from 'react'

import { Button, Card, CardBody, Checkbox, Input, Select } from '@/components/ui'
import { RelationSelect } from '@/components/data/RelationSelect'

import './data.css'

/**
 * The criteria of a list that shows nothing until "بحث" is pressed.
 *
 * Patients, payments, expenses and staff grow without bound, and a screen
 * that loads all of them on open is a slow page and — for money and medical
 * files — everyone's data on the wall. So these lists start empty: the user
 * states what they are looking for, presses search, and only then does the
 * request go out. `onSearch` receives the filled-in criteria only; `validate`
 * may refuse a search that is too broad, and its message is shown here.
 *
 * A field is `{ name, label, type, ... }`:
 *   text (default) · date · money · select (options) · relation (resource) · checkbox
 * The free-text box is always first and is named `q`.
 */
export function SearchPanel({
  fields,
  queryLabel = 'بحث',
  queryPlaceholder,
  initial = {},
  validate,
  onSearch,
  onReset,
}) {
  const blank = () => ({ q: '', ...Object.fromEntries(fields.map((f) => [f.name, f.type === 'checkbox' ? false : ''])) })
  const [values, setValues] = useState(() => ({ ...blank(), ...initial }))
  const [problem, setProblem] = useState('')

  const set = (name, value) => {
    setValues((current) => ({ ...current, [name]: value }))
    setProblem('')
  }

  const submit = (event) => {
    event.preventDefault()
    const message = validate?.(values)
    if (message) {
      setProblem(message)
      return
    }
    const criteria = {}
    Object.entries(values).forEach(([name, value]) => {
      const trimmed = typeof value === 'string' ? value.trim() : value
      if (trimmed !== '' && trimmed !== false) criteria[name] = trimmed
    })
    onSearch(criteria)
  }

  const reset = () => {
    setValues(blank())
    setProblem('')
    onReset?.()
  }

  return (
    <Card className="search-panel">
      <CardBody>
        <form onSubmit={submit} noValidate>
          <div className="search-panel__grid">
            <div className="search-panel__wide">
              <Input
                label={queryLabel}
                type="search"
                value={values.q}
                placeholder={queryPlaceholder}
                onChange={(event) => set('q', event.target.value)}
              />
            </div>
            {fields.map((field) => (
              <Control key={field.name} field={field} value={values[field.name]} onChange={(v) => set(field.name, v)} />
            ))}
          </div>
          <div className="search-panel__actions">
            <Button type="submit" variant="primary">
              بحث
            </Button>
            <Button type="button" variant="ghost" onClick={reset}>
              مسح
            </Button>
            {problem && (
              <span className="search-panel__error" role="alert">
                {problem}
              </span>
            )}
          </div>
        </form>
      </CardBody>
    </Card>
  )
}

function Control({ field, value, onChange }) {
  const { label, type = 'text' } = field
  switch (type) {
    case 'select':
      return (
        <Select
          label={label}
          placeholder="الكل"
          options={field.options}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      )
    case 'relation':
      return (
        <RelationSelect
          label={label}
          resource={field.resource}
          searchable={field.searchable}
          placeholder="الكل"
          value={value}
          onChange={onChange}
        />
      )
    case 'checkbox':
      return <Checkbox label={label} checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
    case 'money':
      return (
        <Input
          label={label}
          type="number"
          min="0"
          step="0.01"
          inputMode="decimal"
          dir="ltr"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      )
    default:
      return <Input label={label} type={type} value={value} onChange={(event) => onChange(event.target.value)} />
  }
}

/** True when at least one criterion other than a bare checkbox is filled in. */
export function hasCriteria(values, ignore = []) {
  return Object.entries(values).some(
    ([name, value]) => !ignore.includes(name) && value !== '' && value !== false && value != null,
  )
}
