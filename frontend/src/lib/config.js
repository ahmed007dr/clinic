/**
 * Every address the application talks to is derived from here, and from
 * nothing else. The one input is `VITE_BASE_URL` (see `frontend/.env.example`):
 * where the Django server lives.
 *
 * `SERVER_URL` is what the browser actually uses. It is empty — same origin —
 * whenever Django serves the page itself (production) or Vite proxies to it
 * (development; vite.config.js forwards to `VITE_BASE_URL`). Same origin is
 * what keeps the session cookie and the CSRF token working without CORS.
 */

export const SERVER_URL = (import.meta.env.VITE_SERVER_URL || '').replace(/\/+$/, '')

/** The DRF API. `lib/http.js` prefixes every request with it. */
export const API_URL = `${SERVER_URL}/api`

/**
 * Where the router is mounted (`api/spa.py` serves the app there). Every
 * `navigate()` and `<Link>` is relative to it.
 */
export const APP_BASENAME = (import.meta.env.VITE_APP_BASENAME || '/app').replace(/\/+$/, '')

/**
 * A server-rendered Django page — the PDF/Excel exporters, the prescription
 * print view — which the SPA links to rather than reimplements.
 */
export function serverUrl(path) {
  return `${SERVER_URL}${path.startsWith('/') ? path : `/${path}`}`
}
