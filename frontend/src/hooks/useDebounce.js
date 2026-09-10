import { useEffect, useRef, useState } from 'react'

/**
 * Delay a fast-changing value.
 *
 * Used by every search box: without it, each keystroke is a request, and
 * "أحمد" is four requests whose responses can arrive out of order.
 */
export function useDebounce(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}

/** Runs an effect on every change *except* the first render. */
export function useUpdateEffect(effect, deps) {
  const mounted = useRef(false)
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true
      return undefined
    }
    return effect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}

/** Reflects a value in `document.title`. */
export function useDocumentTitle(title) {
  useEffect(() => {
    const previous = document.title
    document.title = title ? `${title} — نظام إدارة العيادة` : 'نظام إدارة العيادة'
    return () => {
      document.title = previous
    }
  }, [title])
}
