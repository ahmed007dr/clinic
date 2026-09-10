import { useId } from 'react'

/**
 * A label, a control, and the error the server gave for it.
 *
 * Every form control in the application is wrapped in one of these, so an
 * error is always announced next to the input that caused it — `aria-invalid`
 * and `aria-describedby` are wired here once rather than remembered per form.
 */
export function Field({ label, error, hint, required, htmlFor, children }) {
  const generatedId = useId()
  const id = htmlFor || generatedId
  const errorId = `${id}-error`
  const hintId = `${id}-hint`

  const describedBy = [error && errorId, hint && hintId].filter(Boolean).join(' ')

  return (
    <div className="ui-field">
      {label && (
        <label className="ui-field__label" htmlFor={id}>
          {label}
          {required && (
            <span className="ui-field__required" aria-hidden="true">
              *
            </span>
          )}
        </label>
      )}
      {typeof children === 'function'
        ? children({
            id,
            'aria-invalid': error ? true : undefined,
            'aria-describedby': describedBy || undefined,
            invalid: Boolean(error),
          })
        : children}
      {hint && !error && (
        <span className="ui-field__hint" id={hintId}>
          {hint}
        </span>
      )}
      {error && (
        <span className="ui-field__error" id={errorId} role="alert">
          {error}
        </span>
      )}
    </div>
  )
}
