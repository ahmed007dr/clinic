import { forwardRef } from 'react'

import { Field } from './Field'

/**
 * The three text controls, each in two forms: a bare control, and the same
 * control wrapped in a `Field` when `label` is given. Screens use the wrapped
 * form almost always; the bare one exists for toolbars and table filters,
 * where a label above the box would be noise.
 */

export const Input = forwardRef(function Input(
  { label, error, hint, required, invalid, className = '', ...rest },
  ref,
) {
  const control = (props = {}) => (
    <input
      ref={ref}
      className={`ui-input ${invalid || error ? 'ui-input--invalid' : ''} ${className}`}
      required={required}
      {...props}
      {...rest}
    />
  )

  if (!label) return control()
  return (
    <Field label={label} error={error} hint={hint} required={required}>
      {(props) => control(props)}
    </Field>
  )
})

export const Textarea = forwardRef(function Textarea(
  { label, error, hint, required, invalid, rows = 3, className = '', ...rest },
  ref,
) {
  const control = (props = {}) => (
    <textarea
      ref={ref}
      rows={rows}
      className={`ui-textarea ${invalid || error ? 'ui-textarea--invalid' : ''} ${className}`}
      required={required}
      {...props}
      {...rest}
    />
  )

  if (!label) return control()
  return (
    <Field label={label} error={error} hint={hint} required={required}>
      {(props) => control(props)}
    </Field>
  )
})

/**
 * `options` is `[{ value, label }]`. `placeholder` becomes an empty first
 * option — which is how an optional foreign key is cleared, and without it a
 * select silently keeps whatever it happened to load with.
 */
export const Select = forwardRef(function Select(
  {
    label,
    error,
    hint,
    required,
    invalid,
    options = [],
    placeholder,
    className = '',
    children,
    ...rest
  },
  ref,
) {
  const control = (props = {}) => (
    <select
      ref={ref}
      className={`ui-select ${invalid || error ? 'ui-select--invalid' : ''} ${className}`}
      required={required}
      {...props}
      {...rest}
    >
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
      {children}
    </select>
  )

  if (!label) return control()
  return (
    <Field label={label} error={error} hint={hint} required={required}>
      {(props) => control(props)}
    </Field>
  )
})

export const Checkbox = forwardRef(function Checkbox(
  { label, className = '', ...rest },
  ref,
) {
  return (
    // A long label wraps beside the box; without `flexShrink: 0` a narrow
    // phone screen squeezes the box itself to nothing.
    <label className={`ui-row ${className}`} style={{ cursor: 'pointer', alignItems: 'flex-start' }}>
      <input ref={ref} type="checkbox" style={{ flexShrink: 0, marginBlockStart: '0.3em' }} {...rest} />
      <span>{label}</span>
    </label>
  )
})
