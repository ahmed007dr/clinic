import { useEffect, useState } from 'react'

import { usePortal } from './PortalContext'

/**
 * The clinic's social and contact links under every portal page — only the
 * ones it filled in (Print design screen). A signed-in patient sees their own
 * clinic's; before sign-in, each clinic of the group that has links.
 */
export function PortalFooter() {
  const { api, me } = usePortal()
  const [publicClinics, setPublicClinics] = useState([])

  useEffect(() => {
    if (me) return
    let active = true
    api
      .links()
      .then((data) => {
        if (active) setPublicClinics(data.clinics ?? [])
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [api, me])

  const clinics = me ? (me.links?.length ? [{ name: null, links: me.links }] : []) : publicClinics
  if (clinics.length === 0) return null

  return (
    <footer className="portal-footer">
      {clinics.map((clinic) => (
        <div key={clinic.name ?? 'mine'} className="portal-footer__row">
          {clinic.name && clinics.length > 1 && <strong>{clinic.name}</strong>}
          {clinic.links.map((link) => (
            <a key={link.kind} href={link.url} target="_blank" rel="noopener noreferrer">
              {link.label}
            </a>
          ))}
        </div>
      ))}
    </footer>
  )
}
