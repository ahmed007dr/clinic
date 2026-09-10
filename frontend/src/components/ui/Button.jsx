import { forwardRef } from 'react'

import { Spinner } from './Spinner'

/**
 * @param {'primary'|'secondary'|'ghost'|'danger'} [variant]
 * @param {boolean} [loading]  Shows a spinner and disables the button, so a
 *                             slow save cannot be submitted twice.
 */
export const Button = forwardRef(function Button(
  {
    variant = 'secondary',
    size,
    icon = false,
    block = false,
    loading = false,
    disabled = false,
    className = '',
    children,
    type = 'button',
    ...rest
  },
  ref,
) {
  const classes = [
    'ui-btn',
    `ui-btn--${variant}`,
    size === 'sm' && 'ui-btn--sm',
    icon && 'ui-btn--icon',
    block && 'ui-btn--block',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      ref={ref}
      type={type}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <Spinner />}
      {children}
    </button>
  )
})
