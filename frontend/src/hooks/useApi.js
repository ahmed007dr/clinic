/**
 * Fetching, in three hooks.
 *
 * Not a data-fetching library. This application needs loading and error state,
 * cancellation on unmount, and an explicit refresh after a write — and it does
 * not need a cache, because a clinic screen showing yesterday's queue is worse
 * than one that takes another 80ms. Adding a caching layer here would be
 * adding a class of stale-data bug that the app currently cannot have.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ApiError } from '@/lib/http'

/**
 * One request, re-run whenever `deps` change.
 *
 * `fetcher` receives an AbortSignal — pass it through, or a user typing in a
 * search box gets whichever response happens to land last rather than the
 * response to what they actually typed.
 */
export function useAsync(fetcher, deps = [], { skip = false } = {}) {
  const [state, setState] = useState({
    data: null,
    error: null,
    loading: !skip,
  })
  // Kept in a ref so `reload` is stable and does not itself retrigger effects.
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const [nonce, setNonce] = useState(0)
  const reload = useCallback(() => setNonce((value) => value + 1), [])

  useEffect(() => {
    if (skip) {
      setState({ data: null, error: null, loading: false })
      return undefined
    }
    const controller = new AbortController()
    let active = true

    setState((previous) => ({ ...previous, loading: true, error: null }))

    Promise.resolve(fetcherRef.current(controller.signal))
      .then((data) => {
        if (active) setState({ data, error: null, loading: false })
      })
      .catch((error) => {
        // An abort is the expected outcome of navigating away mid-request, not
        // something to show the user.
        if (error?.name === 'AbortError' || !active) return
        setState({ data: null, error, loading: false })
      })

    return () => {
      active = false
      controller.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, skip])

  return { ...state, reload, setData: (data) => setState((s) => ({ ...s, data })) }
}

/**
 * A paginated list.
 *
 * Returns the rows plus the paging numbers the table renders, and re-fetches
 * when the filters change. `params` is compared by value, so callers can pass
 * an object literal without causing an infinite loop — the single most common
 * way a hook like this goes wrong.
 */
export function useList(resource, params = {}, options = {}) {
  const key = JSON.stringify(params)
  const stableParams = useMemo(() => params, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  const { data, error, loading, reload } = useAsync(
    (signal) => resource.list(stableParams, { signal }),
    [resource.path, key],
    options,
  )

  return {
    rows: data?.results ?? [],
    count: data?.count ?? 0,
    page: data?.page ?? 1,
    pages: data?.pages ?? 1,
    pageSize: data?.page_size ?? 25,
    error,
    loading,
    reload,
    isEmpty: !loading && !error && (data?.results?.length ?? 0) === 0,
  }
}

/** One record by UUID. Skipped entirely when `uuid` is absent — which is what
 *  a "create" screen passes, and it must not fire a request for `undefined`. */
export function useRecord(resource, uuid, options = {}) {
  const { data, error, loading, reload, setData } = useAsync(
    (signal) => resource.get(uuid, { signal }),
    [resource.path, uuid],
    { skip: !uuid, ...options },
  )
  return { record: data, error, loading, reload, setRecord: setData }
}

/**
 * A write.
 *
 * Exposes `submitting` and `fieldErrors` because that is what a form needs:
 * a disabled button while in flight, and the server's own messages placed
 * against the inputs that caused them.
 */
export function useMutation(action) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const actionRef = useRef(action)
  actionRef.current = action

  const run = useCallback(async (...args) => {
    setSubmitting(true)
    setError(null)
    try {
      return await actionRef.current(...args)
    } catch (caught) {
      setError(caught)
      throw caught
    } finally {
      setSubmitting(false)
    }
  }, [])

  const fieldErrors = useMemo(() => {
    if (!(error instanceof ApiError)) return {}
    const fields = {}
    Object.entries(error.fields || {}).forEach(([name, messages]) => {
      if (name === 'non_field_errors' || name === 'detail') return
      fields[name] = Array.isArray(messages) ? messages.join(' ') : String(messages)
    })
    return fields
  }, [error])

  const formError = useMemo(() => {
    if (!error) return null
    if (!(error instanceof ApiError)) return error.message
    const nonField = error.fields?.non_field_errors
    if (nonField) return Array.isArray(nonField) ? nonField.join(' ') : nonField
    // A message that belongs to a field is shown at that field, not twice.
    return Object.keys(fieldErrors).length ? null : error.message
  }, [error, fieldErrors])

  return { run, submitting, error, fieldErrors, formError, reset: () => setError(null) }
}
