/**
 * The only place in the application that calls `fetch`.
 *
 * Everything above this module talks to `api/*` resources; everything about
 * transport — CSRF, credentials, error shape, file uploads — is decided here
 * once. The point is not tidiness: a second place that calls `fetch` is a
 * second place that can forget the CSRF header, and that failure looks like a
 * broken form rather than a security control doing its job.
 */

const BASE = '/api'

/** Django's CSRF cookie. Readable by design — the token is not the secret. */
function csrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : null
}

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

/**
 * An error that carries the server's field errors, so a form can show them
 * against the right input instead of dumping a paragraph at the top.
 */
export class ApiError extends Error {
  constructor(status, payload) {
    const detail =
      payload?.detail ||
      (typeof payload === 'string' ? payload : null) ||
      DEFAULT_MESSAGES[status] ||
      'حدث خطأ غير متوقع.'
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
    /** Field name → array of messages. Empty when the error is not a form error. */
    this.fields =
      payload && typeof payload === 'object' && !payload.detail ? payload : {}
  }

  get isAuth() {
    return this.status === 401 || this.status === 403
  }

  get isNotFound() {
    return this.status === 404
  }
}

const DEFAULT_MESSAGES = {
  400: 'البيانات المُرسلة غير صحيحة.',
  401: 'يجب تسجيل الدخول.',
  403: 'ليس لديك صلاحية لهذا الإجراء.',
  404: 'السجل غير موجود.',
  429: 'محاولات كثيرة. حاول بعد قليل.',
  500: 'خطأ في الخادم.',
  502: 'الخادم غير متاح حالياً.',
  503: 'الخادم غير متاح حالياً.',
}

/** Listeners notified when the server says the session is gone. */
const sessionListeners = new Set()

export function onSessionLost(listener) {
  sessionListeners.add(listener)
  return () => sessionListeners.delete(listener)
}

function buildQuery(params) {
  if (!params) return ''
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    // An empty filter is an absent filter. Sending `?status=` makes the server
    // filter on the empty string and quietly return nothing.
    if (value === undefined || value === null || value === '') return
    if (Array.isArray(value)) value.forEach((item) => search.append(key, item))
    else search.append(key, value)
  })
  const query = search.toString()
  return query ? `?${query}` : ''
}

async function parse(response) {
  if (response.status === 204) return null
  const type = response.headers.get('content-type') || ''
  if (type.includes('application/json')) {
    try {
      return await response.json()
    } catch {
      return null
    }
  }
  return await response.text()
}

/**
 * @param {string} path      Path under /api, e.g. `/patients/`
 * @param {object} [options]
 * @param {string} [options.method]
 * @param {object} [options.params]  Query string values; blanks are dropped.
 * @param {object|FormData} [options.body]
 * @param {AbortSignal} [options.signal]
 */
export async function request(path, options = {}) {
  const { method = 'GET', params, body, signal, raw = false } = options

  const headers = { Accept: 'application/json' }
  let payload

  if (body instanceof FormData) {
    // Deliberately no Content-Type: the browser must set the multipart
    // boundary itself, and setting it by hand produces an upload the server
    // cannot parse.
    payload = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  if (UNSAFE.has(method)) {
    const token = csrfToken()
    if (token) headers['X-CSRFToken'] = token
  }

  const response = await fetch(`${BASE}${path}${buildQuery(params)}`, {
    method,
    headers,
    body: payload,
    signal,
    // The session cookie is the credential. Same-origin in production and,
    // thanks to the dev proxy, same-origin in development too.
    credentials: 'same-origin',
    // Never follow a redirect to the login page: the catch-all in
    // project/urls.py turns an unauthenticated API call into a 302 to an HTML
    // form, and following it yields a 200 full of markup that the app would
    // try to read as JSON.
    redirect: 'manual',
  })

  if (raw) return response

  if (response.type === 'opaqueredirect' || response.status === 302) {
    sessionListeners.forEach((listener) => listener())
    throw new ApiError(401, { detail: 'انتهت الجلسة. يرجى تسجيل الدخول.' })
  }

  const data = await parse(response)

  if (!response.ok) {
    const error = new ApiError(response.status, data)
    // 403 is also what an insufficient *role* returns, and signing the user
    // out because they opened a page they are not allowed to see would be
    // maddening. Only a genuinely absent session is treated as lost.
    if (response.status === 401) {
      sessionListeners.forEach((listener) => listener())
    }
    throw error
  }

  return data
}

export const http = {
  get: (path, params, options) => request(path, { ...options, params }),
  post: (path, body, options) => request(path, { ...options, method: 'POST', body }),
  put: (path, body, options) => request(path, { ...options, method: 'PUT', body }),
  patch: (path, body, options) => request(path, { ...options, method: 'PATCH', body }),
  delete: (path, options) => request(path, { ...options, method: 'DELETE' }),
  /** Streams a private file and hands the browser a download. */
  download: async (path, filename) => {
    const response = await request(path, { raw: true })
    if (!response.ok) throw new ApiError(response.status, await parse(response))
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename || 'file'
    document.body.appendChild(link)
    link.click()
    link.remove()
    // Revoked on the next tick: revoking synchronously races the download in
    // Safari and produces an empty file.
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}
