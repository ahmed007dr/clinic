/**
 * A REST resource, as five functions.
 *
 * Every endpoint in this API has the same shape, so writing the same five
 * methods twenty times would be twenty chances to get one of them subtly
 * wrong. Each resource module below is a line or two; anything genuinely
 * particular to one resource is added there explicitly, where it is visible.
 */

import { http } from '@/lib/http'

export function createResource(path) {
  const base = `/${path}/`
  const one = (uuid) => `${base}${uuid}/`

  return {
    path: base,
    list: (params, options) => http.get(base, params, options),
    get: (uuid, options) => http.get(one(uuid), undefined, options),
    create: (body) => http.post(base, body),
    update: (uuid, body) => http.patch(one(uuid), body),
    replace: (uuid, body) => http.put(one(uuid), body),
    remove: (uuid) => http.delete(one(uuid)),
    /** For the `@action` endpoints DRF exposes under a record. */
    action: (uuid, name, body, method = 'POST') =>
      http[method.toLowerCase()](`${one(uuid)}${name}/`, body),
    /** For `@action(detail=False)` endpoints on the collection. */
    collectionAction: (name, params) => http.get(`${base}${name}/`, params),
  }
}
