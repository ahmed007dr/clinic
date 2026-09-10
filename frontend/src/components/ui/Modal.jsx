import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

import { Button } from './Button'

/**
 * A dialog that behaves like one: Escape closes it, a backdrop click closes
 * it, focus moves inside and is kept there, and the page behind does not
 * scroll. Rendered through a portal so a modal opened from deep inside a table
 * is not clipped by that table's `overflow`.
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  size,
  closeOnBackdrop = true,
}) {
  const panelRef = useRef(null)
  const previouslyFocused = useRef(null)

  useEffect(() => {
    if (!open) return undefined

    previouslyFocused.current = document.activeElement
    const { overflow } = document.body.style
    document.body.style.overflow = 'hidden'

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        onClose?.()
        return
      }
      if (event.key !== 'Tab') return

      // Keep Tab inside the dialog. Without this, tabbing walks into the page
      // behind, where a keyboard user cannot see what they are focused on.
      const focusable = panelRef.current?.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )
      if (!focusable || focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    // Focus the panel itself rather than the first control: focusing an input
    // pops the keyboard on mobile before the user has read the title.
    const timer = setTimeout(() => panelRef.current?.focus(), 0)

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = overflow
      clearTimeout(timer)
      previouslyFocused.current?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null

  const sizeClass =
    size === 'wide' ? 'ui-modal--wide' : size === 'narrow' ? 'ui-modal--narrow' : ''

  return createPortal(
    <div
      className="ui-modal__backdrop"
      onMouseDown={(event) => {
        // mousedown, not click: a click that *starts* inside the dialog and
        // ends on the backdrop (selecting text, then releasing) would
        // otherwise close it and discard what was typed.
        if (closeOnBackdrop && event.target === event.currentTarget) onClose?.()
      }}
    >
      <div
        ref={panelRef}
        className={`ui-modal ${sizeClass}`}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        tabIndex={-1}
      >
        <div className="ui-modal__header">
          <h2 className="ui-modal__title">{title}</h2>
          <Button variant="ghost" icon onClick={onClose} aria-label="إغلاق">
            ✕
          </Button>
        </div>
        <div className="ui-modal__body">{children}</div>
        {footer && <div className="ui-modal__footer">{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}

/**
 * A yes/no question. Destructive by default, because that is what confirmation
 * exists for — and the confirm button carries the specific verb rather than
 * "OK", so the answer is unambiguous when read quickly.
 */
export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title = 'تأكيد',
  message,
  confirmLabel = 'تأكيد',
  cancelLabel = 'إلغاء',
  tone = 'danger',
  loading = false,
}) {
  return (
    <Modal
      open={open}
      onClose={loading ? undefined : onClose}
      title={title}
      size="narrow"
      closeOnBackdrop={!loading}
      footer={
        <>
          <Button variant={tone} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {cancelLabel}
          </Button>
        </>
      }
    >
      <p>{message}</p>
    </Modal>
  )
}
