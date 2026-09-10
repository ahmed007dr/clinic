import { useToast } from '@/hooks/useToast'

/** Renders whatever `useToast()` is holding. Mounted once, in `App`. */
export function Toasts() {
  const { toasts, dismiss } = useToast()
  if (toasts.length === 0) return null

  return (
    <div className="ui-toasts">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`ui-toast ui-toast--${toast.tone}`}
          // Errors interrupt; confirmations wait their turn. Announcing a
          // successful save assertively talks over whatever the user is
          // reading.
          role={toast.tone === 'urgent' ? 'alert' : 'status'}
        >
          <span className="ui-toast__message">{toast.message}</span>
          <button
            type="button"
            className="ui-search__clear"
            style={{ position: 'static' }}
            onClick={() => dismiss(toast.id)}
            aria-label="إغلاق"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
