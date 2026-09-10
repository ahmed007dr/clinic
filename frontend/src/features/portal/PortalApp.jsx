import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router-dom'

import { Loading, Toasts } from '@/components/ui'

import { portalApi } from './portalApi'
import { PortalContext } from './PortalContext'
import { PortalHomePage } from './PortalHomePage'
import { PortalInvitePage } from './PortalInvitePage'
import { PortalLoginPage } from './PortalLoginPage'
import { PortalRegisterPage } from './PortalRegisterPage'
import './portal.css'

/**
 * The patient portal — a separate world inside the same app.
 *
 * Its own session state, kept apart from the staff `AuthProvider`: a patient is
 * never a staff user, and nothing here reads or sets the staff session.
 */
export function PortalApp() {
  const { slug } = useParams()
  const api = useMemo(() => portalApi(slug), [slug])
  const [me, setMe] = useState(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      setMe(await api.me())
    } catch {
      setMe(null)
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    refresh()
  }, [refresh])

  const value = useMemo(() => ({ slug, api, me, setMe, refresh }), [slug, api, me, refresh])

  return (
    <PortalContext.Provider value={value}>
      <Routes>
        <Route path="login" element={<PortalLoginPage />} />
        <Route path="invite" element={<PortalInvitePage />} />
        <Route path="register" element={<PortalRegisterPage />} />
        <Route
          index
          element={loading ? <Loading /> : me ? <PortalHomePage /> : <Navigate to="login" replace />}
        />
        <Route path="*" element={<Navigate to="." replace />} />
      </Routes>
      <Toasts />
    </PortalContext.Provider>
  )
}
