/** Transient confirmations. Replaces Django's `messages` for the SPA. */

import { createContext, useCallback, useContext, useMemo, useState } from 'react'

const ToastContext = createContext(null)

let nextId = 1

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const show = useCallback(
    (message, tone = 'ok', ttl = 4000) => {
      const id = nextId++
      setToasts((current) => [...current, { id, message, tone }])
      // Errors stay until dismissed: the one message a user most needs to
      // read is the one most likely to vanish while they are looking away.
      if (tone !== 'urgent' && ttl) setTimeout(() => dismiss(id), ttl)
      return id
    },
    [dismiss],
  )

  const value = useMemo(
    () => ({
      toasts,
      dismiss,
      show,
      success: (message) => show(message, 'ok'),
      error: (message) => show(message, 'urgent', 0),
      warn: (message) => show(message, 'warn'),
      info: (message) => show(message, 'info'),
    }),
    [toasts, dismiss, show],
  )

  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside <ToastProvider>')
  return context
}
