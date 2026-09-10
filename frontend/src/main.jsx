import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { applyStoredTheme } from '@/components/layout/ThemeToggle'

import App from './App'
import './styles/global.css'

// Before the first render, so a user who chose dark does not get a white
// flash on every page load.
applyStoredTheme()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
