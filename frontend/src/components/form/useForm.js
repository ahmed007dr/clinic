import { useCallback, useEffect, useState } from 'react'

/**
 * Form state, small on purpose.
 *
 * Controlled inputs, one change handler, and the server's field errors merged
 * in. No schema and no client-side validation rules beyond `required` on the
 * inputs themselves — because the server validates anyway, and a second set of
 * rules in the client is a second set that can disagree with the first. The
 * client's job is to show the server's answer next to the right input.
 */
export function useForm(initialValues = {}, { serverErrors = {} } = {}) {
  const [values, setValues] = useState(initialValues)
  const [touched, setTouched] = useState({})
  const [dirty, setDirty] = useState(false)

  // Re-seed when the record arrives — an edit form is mounted before its
  // fetch resolves, and without this it stays stuck on empty defaults.
  useEffect(() => {
    setValues(initialValues)
    setDirty(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(initialValues)])

  const setValue = useCallback((name, value) => {
    setValues((current) => ({ ...current, [name]: value }))
    setTouched((current) => ({ ...current, [name]: true }))
    setDirty(true)
  }, [])

  /** Wire straight onto an input: `{...field('name')}`. */
  const field = useCallback(
    (name, { type = 'text' } = {}) => ({
      name,
      value: values[name] ?? '',
      onChange: (event) => {
        const target = event?.target ?? {}
        let next
        if (type === 'checkbox') next = target.checked
        else if (type === 'file') next = target.files?.[0] ?? null
        else next = target.value
        setValue(name, next)
      },
      // Shown only once the user has moved on, or once the server has spoken —
      // flagging a field as invalid while it is still being typed into is
      // the most irritating form behaviour there is.
      error: serverErrors[name],
    }),
    [values, serverErrors, setValue],
  )

  const reset = useCallback((next = initialValues) => {
    setValues(next)
    setTouched({})
    setDirty(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /**
   * The values, ready to send.
   *
   * Empty strings become `null` for the fields listed in `nullable`: DRF
   * rejects `""` for an optional foreign key or date, and a blank select is
   * how a user clears one.
   */
  const payload = useCallback(
    (nullable = []) => {
      const body = { ...values }
      nullable.forEach((name) => {
        if (body[name] === '') body[name] = null
      })
      return body
    },
    [values],
  )

  /** Multipart, for the one form that uploads a file. */
  const formData = useCallback(() => {
    const data = new FormData()
    Object.entries(values).forEach(([name, value]) => {
      if (value === null || value === undefined || value === '') return
      data.append(name, value)
    })
    return data
  }, [values])

  return { values, setValues, setValue, field, reset, dirty, touched, payload, formData }
}

/**
 * Warn before leaving a form with unsaved changes.
 *
 * Only guards a real page unload. In-app navigation is not blocked: React
 * Router's own blocker fights the browser back button in ways that strand
 * users, and losing a half-typed visit note is better than a screen that will
 * not let go.
 */
export function useUnsavedWarning(dirty) {
  useEffect(() => {
    if (!dirty) return undefined
    const handler = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])
}
