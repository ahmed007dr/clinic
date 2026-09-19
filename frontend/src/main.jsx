import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'

import { applyStoredTheme } from '@/components/layout/ThemeToggle'

import { LanguageProvider } from '@/i18n'

import App from './App'
import './styles/global.css'

// The bare domain — no path at all — is the public directory of clinics: a page
// with no router and no sign-in, served by Django at `/` (api/spa.py). Every
// other address is the application, which lives under `/app`.
const Directory = lazy(() =>
  import('@/features/directory/DirectoryPage').then((module) => ({ default: module.DirectoryPage })),
)
const atTheBareDomain = window.location.pathname === '/'

// Before the first render, so a user who chose dark does not get a white
// flash on every page load.
applyStoredTheme()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <LanguageProvider>
      {atTheBareDomain ? (
        <Suspense fallback={null}>
          <Directory />
        </Suspense>
      ) : (
        <App />
      )}
    </LanguageProvider>
  </StrictMode>,
)
