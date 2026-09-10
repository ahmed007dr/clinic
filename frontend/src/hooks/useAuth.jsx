/**
 * Who is signed in, for the whole application.
 *
 * The `permissions` object this exposes decides what the interface *draws*. It
 * is never what decides what the user may *do* — every call is re-authorised
 * by the server, and a user who edits these flags in devtools gets a 403, not
 * access. Hiding a button is a courtesy; the API is the boundary.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'

import { api } from '@/api'
import { onSessionLost } from '@/lib/http'

const AuthContext = createContext(null)

const NO_PERMISSIONS = {
  is_admin: false,
  view_clinical: false,
  manage_billing: false,
  manage_staff: false,
  manage_settings: false,
  all_branches: false,
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // `loading` starts true so the router never flashes the login screen at
  // someone who is already signed in.
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const data = await api.auth.session()
      setUser(data.authenticated ? data.user : null)
      return data.user ?? null
    } catch {
      setUser(null)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  // A session that expires server-side must not leave the app rendering a
  // shell full of failing requests.
  useEffect(() => onSessionLost(() => setUser(null)), [])

  const login = useCallback(async (email, password) => {
    const data = await api.auth.login(email, password)
    setUser(data.user)
    return data.user
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.auth.logout()
    } finally {
      // Cleared even if the call fails: the user asked to be signed out, and
      // leaving them apparently signed in is the worse of the two outcomes.
      setUser(null)
    }
  }, [])

  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      logout,
      refresh,
      isAuthenticated: Boolean(user),
      permissions: user?.permissions ?? NO_PERMISSIONS,
      branch: user?.branch ?? null,
      role: user?.role ?? null,
    }),
    [user, loading, login, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside <AuthProvider>')
  }
  return context
}

/** `const can = usePermissions(); can.view_clinical` */
export function usePermissions() {
  return useAuth().permissions
}
