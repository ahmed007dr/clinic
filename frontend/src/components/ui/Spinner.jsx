/**
 * Its own file, and not part of `State.jsx`, because `Button` needs it for the
 * in-flight state while `State` needs `Button` for its retry action. Together
 * in one module those two form an import cycle.
 */
export function Spinner({ size, className = '' }) {
  return (
    <span
      className={`ui-spinner ${size === 'lg' ? 'ui-spinner--lg' : ''} ${className}`}
      role="status"
      aria-label="جارٍ التحميل"
    />
  )
}
