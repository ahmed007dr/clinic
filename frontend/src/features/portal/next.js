/**
 * Where to go after signing in: the page the person was on, when it is one of
 * this clinic's own portal pages — never an arbitrary address. A `next` that
 * does not start with this clinic's portal path (or that tries `//host`) is
 * ignored, so a crafted sign-in link cannot send someone off-site.
 */
export function safeNext(search, slug) {
  const next = new URLSearchParams(search).get('next')
  if (!next || !next.startsWith(`/portal/${slug}/`) || next.startsWith('//')) return null
  return next
}

/** A sign-in / sign-up link that comes back to `path` afterwards. */
export function withNext(base, path) {
  return `${base}?next=${encodeURIComponent(path)}`
}
