import { useCallback, useMemo, useState } from 'react'

/**
 * Where the customer is, for "the nearest clinic first" (docs/16).
 *
 * Two ways, the better first: the browser's location (asked for only when the
 * customer presses «استخدم موقعي»), or a governorate they choose. The point lives
 * in memory for this page only — it is sent to the server as query parameters to
 * order a list and is never stored, there or here. The governorate is a remembered
 * convenience (localStorage, guarded: it can throw in a private window).
 */
const KEY = 'clinic-portal-governorate'

function remembered() {
  try {
    return localStorage.getItem(KEY) || ''
  } catch {
    return ''
  }
}

export function usePlace() {
  const [governorate, setGovernorate] = useState(remembered)
  const [point, setPoint] = useState(null)
  const [locating, setLocating] = useState(false)
  const [problem, setProblem] = useState('')

  const chooseGovernorate = useCallback((name) => {
    setGovernorate(name)
    try {
      localStorage.setItem(KEY, name)
    } catch {
      /* the choice still works for this visit */
    }
  }, [])

  const locate = useCallback(() => {
    setProblem('')
    if (!navigator.geolocation) {
      setProblem('متصفحك لا يدعم تحديد الموقع. اختر محافظتك.')
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setPoint({ lat: position.coords.latitude, lng: position.coords.longitude })
        setLocating(false)
      },
      () => {
        setLocating(false)
        setProblem('لم نتمكن من تحديد موقعك. اسمح للموقع بالوصول أو اختر محافظتك.')
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 5 * 60 * 1000 },
    )
  }, [])

  const forget = useCallback(() => setPoint(null), [])

  // A stable object, so a request re-runs only when the customer's place changes.
  const query = useMemo(() => {
    const params = {}
    if (point) {
      params.lat = point.lat.toFixed(4)
      params.lng = point.lng.toFixed(4)
    }
    if (governorate) params.governorate = governorate
    return params
  }, [point, governorate])

  return { governorate, chooseGovernorate, hasPoint: Boolean(point), locate, locating, forget, problem, query }
}
