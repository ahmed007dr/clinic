import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { Toasts } from '@/components/ui'

import { Header } from './Header'
import { Sidebar } from './Sidebar'
import './layout.css'

/**
 * The frame every signed-in screen sits in.
 *
 * The sidebar is permanent on a wide screen and a drawer on a narrow one. It
 * is one component in both cases rather than two, because a clinic's front
 * desk and the doctor's phone must show the same navigation — two versions
 * drift, and the phone gets the older one.
 */
export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()

  // Navigating from the drawer must close it, or the new screen opens behind
  // the menu that was used to reach it.
  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!drawerOpen) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setDrawerOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [drawerOpen])

  return (
    <div className={`shell ${drawerOpen ? 'shell--drawer-open' : ''}`}>
      <a className="shell__skip" href="#main">
        تخطي إلى المحتوى
      </a>

      <Sidebar onNavigate={() => setDrawerOpen(false)} />

      {drawerOpen && (
        <div
          className="shell__scrim"
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
        />
      )}

      <div className="shell__main">
        <Header onToggleMenu={() => setDrawerOpen((open) => !open)} menuOpen={drawerOpen} />
        <main className="shell__content" id="main">
          <Outlet />
        </main>
      </div>

      <Toasts />
    </div>
  )
}
