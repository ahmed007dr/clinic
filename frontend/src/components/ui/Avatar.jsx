import { initials } from '@/lib/format'

/** A photo when there is one, initials when there is not. */
export function Avatar({ name, src, size, className = '' }) {
  return (
    <span
      className={`ui-avatar ${size === 'lg' ? 'ui-avatar--lg' : ''} ${className}`}
      aria-hidden="true"
      title={name || undefined}
    >
      {src ? <img src={src} alt="" loading="lazy" /> : initials(name)}
    </span>
  )
}
