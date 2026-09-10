import { Input, Select, Textarea } from '@/components/ui'
import { RelationSelect } from '@/components/data/RelationSelect'

import './form.css'

/**
 * Render a form from a field description.
 *
 * A field is `{ name, label, type, required, ... }`. The types map onto the
 * controls this application actually uses — there is no attempt at a general
 * form library, because the moment a screen needs something these do not
 * cover it should write that screen's markup by hand rather than grow another
 * option here.
 *
 *   text · textarea · number · money · date · datetime · select · relation ·
 *   checkbox · file · email · tel
 */
export function FormFields({ fields, form, errors = {}, disabled }) {
  return (
    <div className="form-grid">
      {fields.map((field) => {
        if (field.hide) return null
        const error = errors[field.name]
        const span = field.span ?? (field.type === 'textarea' ? 2 : 1)

        return (
          <div
            key={field.name}
            className="form-grid__cell"
            style={{ gridColumn: `span ${span}` }}
          >
            <FormControl
              field={field}
              form={form}
              error={error}
              disabled={disabled || field.disabled}
            />
          </div>
        )
      })}
    </div>
  )
}

function FormControl({ field, form, error, disabled }) {
  const { name, label, type = 'text', required, hint, placeholder } = field
  const common = { label, error, hint, required, disabled }

  switch (type) {
    case 'textarea':
      return (
        <Textarea
          {...common}
          rows={field.rows ?? 3}
          placeholder={placeholder}
          {...form.field(name)}
        />
      )

    case 'select':
      return (
        <Select
          {...common}
          placeholder={field.placeholder ?? '— اختر —'}
          options={field.options ?? []}
          {...form.field(name)}
        />
      )

    case 'relation':
      return (
        <RelationSelect
          {...common}
          resource={field.resource}
          searchable={field.searchable}
          labelKey={field.labelKey}
          // A function lets one field narrow another — the visit picker lists
          // only the chosen patient's visits.
          params={typeof field.params === 'function' ? field.params(form.values) : field.params}
          value={form.values[name] ?? ''}
          onChange={(value) => form.setValue(name, value)}
        />
      )

    case 'checkbox':
      return (
        <label className="form-check">
          <input
            type="checkbox"
            checked={Boolean(form.values[name])}
            disabled={disabled}
            onChange={(event) => form.setValue(name, event.target.checked)}
          />
          <span>{label}</span>
        </label>
      )

    case 'file':
      return (
        <Input
          {...common}
          type="file"
          accept={field.accept}
          // A file input is never controlled: React cannot set its value, and
          // trying to produces a warning and an input that will not clear.
          onChange={(event) => form.setValue(name, event.target.files?.[0] ?? null)}
        />
      )

    case 'money':
      return (
        <Input
          {...common}
          type="number"
          step="0.01"
          min="0"
          inputMode="decimal"
          placeholder={placeholder ?? '0.00'}
          {...form.field(name)}
        />
      )

    case 'number':
      return (
        <Input
          {...common}
          type="number"
          min={field.min ?? 0}
          step={field.step ?? 1}
          inputMode="numeric"
          {...form.field(name)}
        />
      )

    case 'date':
      return <Input {...common} type="date" {...form.field(name)} />

    case 'datetime':
      return <Input {...common} type="datetime-local" {...form.field(name)} />

    case 'tel':
      // `tel` rather than `text`: it brings up the number pad, and Egyptian
      // mobile numbers are entered dozens of times a day at a front desk.
      return (
        <Input {...common} type="tel" inputMode="tel" dir="ltr" {...form.field(name)} />
      )

    case 'email':
      return <Input {...common} type="email" dir="ltr" {...form.field(name)} />

    case 'password':
      return (
        <Input
          {...common}
          type="password"
          autoComplete="new-password"
          {...form.field(name)}
        />
      )

    default:
      return <Input {...common} placeholder={placeholder} {...form.field(name)} />
  }
}

/** Field names whose empty string must be sent as `null`. */
export function nullableNames(fields) {
  return fields
    .filter(
      (field) =>
        !field.required &&
        ['relation', 'date', 'datetime', 'select', 'number', 'money'].includes(
          field.type,
        ),
    )
    .map((field) => field.name)
}
