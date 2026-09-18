/**
 * PDF / Excel export, served by the existing Django exporters — of the search
 * on screen, and only for those the server lets export (management).
 *
 * Plain links rather than a fetch: the exporters already render Arabic
 * correctly (FE-016) and scope to the caller's branch, the session cookie
 * authenticates them, and a real link lets the browser handle the download
 * itself. Reimplementing them in JavaScript would be a second exporter that
 * gets the shaping wrong.
 */
import { serverUrl } from '@/lib/config'

export function ExportButtons({ path, params = {} }) {
  // The current search travels with the link, so the file holds what is on
  // screen and not the whole table.
  const link = (format) => {
    const query = new URLSearchParams()
    Object.entries({ ...params, export: format }).forEach(([name, value]) => {
      if (value !== undefined && value !== null && value !== '') query.set(name, value)
    })
    return serverUrl(`${path}?${query}`)
  }
  return (
    <div className="ui-row">
      <a className="ui-btn ui-btn--secondary ui-btn--sm" href={link('pdf')}>
        PDF
      </a>
      <a className="ui-btn ui-btn--secondary ui-btn--sm" href={link('excel')}>
        Excel
      </a>
    </div>
  )
}
