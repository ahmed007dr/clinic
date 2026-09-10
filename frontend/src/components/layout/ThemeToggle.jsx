import { useEffect, useState } from 'react'

import { Button } from '@/components/ui'

const KEY = 'clinic-theme'

/**
 * Light / dark / follow the system.
 *
 * Three states, not two: most people never touch this and should get whatever
 * their machine is set to. An explicit choice stamps `data-theme` on the root
 * element, which the token stylesheet gives precedence over the media query.
 *
 * Reading `localStorage` is wrapped because it *throws* — not returns null —
 * in a browser configured to block site data, and an exception here would
 * take the whole application down before it rendered.
 */
function stored() {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

function persist(value) {
  try {
    if (value) localStorage.setItem(KEY, value)
    else localStorage.removeItem(KEY)
  } catch {
    /* A preference that cannot be saved still applies for this session. */
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState(() => stored())

  useEffect(() => {
    const root = document.documentElement
    if (theme) root.setAttribute('data-theme', theme)
    else root.removeAttribute('data-theme')
    persist(theme)
  }, [theme])

  const next = theme === 'dark' ? null : theme === 'light' ? 'dark' : 'light'
  const label =
    theme === 'dark' ? 'داكن' : theme === 'light' ? 'فاتح' : 'حسب النظام'

  return (
    <Button
      variant="ghost"
      icon
      onClick={() => setTheme(next)}
      aria-label={`المظهر: ${label}`}
      title={`المظهر: ${label}`}
    >
      <span aria-hidden="true">{theme === 'dark' ? '☾' : theme === 'light' ? '☀' : '◐'}</span>
    </Button>
  )
}

/** Applies the saved theme before React renders, so there is no flash. */
export function applyStoredTheme() {
  const theme = stored()
  if (theme) document.documentElement.setAttribute('data-theme', theme)
}
