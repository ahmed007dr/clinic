/**
 * PDF / Excel export, served by the existing Django exporters.
 *
 * Plain links rather than a fetch: the exporters already render Arabic
 * correctly (FE-016) and scope to the caller's branch, the session cookie
 * authenticates them, and a real link lets the browser handle the download
 * itself. Reimplementing them in JavaScript would be a second exporter that
 * gets the shaping wrong.
 */
import { serverUrl } from '@/lib/config'

export function ExportButtons({ path }) {
  return (
    <div className="ui-row">
      <a className="ui-btn ui-btn--secondary ui-btn--sm" href={serverUrl(`${path}?export=pdf`)}>
        PDF
      </a>
      <a className="ui-btn ui-btn--secondary ui-btn--sm" href={serverUrl(`${path}?export=excel`)}>
        Excel
      </a>
    </div>
  )
}
