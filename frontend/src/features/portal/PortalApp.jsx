import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router-dom'

import { Loading, Toasts } from '@/components/ui'

import { portalApi } from './portalApi'
import { PortalContext } from './PortalContext'
import { PortalAboutPage } from './PortalAboutPage'
import { PortalCartPage } from './PortalCartPage'
import { PortalCatalogPage } from './PortalCatalogPage'
import { PortalFooter } from './PortalFooter'
import { PortalHomePage } from './PortalHomePage'
import { PortalInvitePage } from './PortalInvitePage'
import { PortalLandingPage } from './PortalLandingPage'
import { PortalLoginPage } from './PortalLoginPage'
import { PortalRegisterPage } from './PortalRegisterPage'
import { PortalSignupPage } from './PortalSignupPage'
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

  const value = useMemo(() => ({ slug, api, me, setMe, refresh, loading }), [slug, api, me, refresh, loading])

  return (
    <PortalContext.Provider value={value}>
      <Routes>
        <Route path="login" element={<PortalLoginPage />} />
        <Route path="invite" element={<PortalInvitePage />} />
        <Route path="register" element={<PortalRegisterPage />} />
        <Route path="signup" element={<PortalSignupPage />} />
        <Route path="services" element={<PortalCatalogPage />} />
        <Route path="services/:service" element={<PortalCatalogPage />} />
        <Route path="services/:service/:branch" element={<PortalCatalogPage />} />
        {/* The doctor-and-time path, for a customer who wants a particular doctor and time. */}
        <Route path="services/:service/:branch/doctors" element={<PortalCatalogPage doctors />} />
        <Route path="services/:service/:branch/:doctor" element={<PortalCatalogPage />} />
        <Route path="cart" element={<PortalCartPage />} />
        <Route path="about" element={<PortalAboutPage />} />
        <Route
          index
          element={loading ? <Loading /> : me ? <PortalHomePage /> : <PortalLandingPage />}
        />
        <Route path="*" element={<Navigate to="." replace />} />
      </Routes>
      <PortalFooter />
      <Toasts />
    </PortalContext.Provider>
  )
}
