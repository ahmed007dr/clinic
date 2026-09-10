import { createContext, useContext } from 'react'

/** Its own file so panels can read it without importing PortalApp (a cycle). */
export const PortalContext = createContext(null)

export function usePortal() {
  const context = useContext(PortalContext)
  if (!context) throw new Error('usePortal must be used inside <PortalApp>')
  return context
}
