/**
 * A state, shown as a shape as well as a word.
 *
 * `tone` is semantic and separate from the brand colour on purpose: emphasis
 * and status must not look like the same thing, or "important" and "abnormal"
 * become indistinguishable at a glance.
 */
export function Badge({ tone = 'neutral', children, className = '', ...rest }) {
  return (
    <span className={`ui-badge ui-badge--${tone} ${className}`} {...rest}>
      {children}
    </span>
  )
}

/** Appointment status → tone. One mapping, used by every screen that shows one. */
export const APPOINTMENT_TONES = {
  waiting: 'warn',
  entered: 'ok',
  called: 'info',
  quick: 'neutral',
  // From the patient portal, waiting for reception to confirm.
  requested: 'primary',
  completed: 'ok',
  cancelled: 'neutral',
  // Someone who did not turn up needs chasing.
  no_show: 'urgent',
}

/** Lab flags. `normal` is deliberately quiet — only the rest should draw an eye,
 *  and `critical` is separate from `abnormal` because it means "act now". */
export const LAB_TONES = {
  normal: 'ok',
  abnormal: 'warn',
  critical: 'urgent',
}

/* The keys below are the model's own `TextChoices` values, read from
   medical/models.py rather than guessed — a tone map with an invented key
   silently falls back to grey, which looks like a working screen. */

export const PLAN_TONES = {
  draft: 'neutral',
  active: 'primary',
  completed: 'ok',
  cancelled: 'neutral',
}

export const SESSION_TONES = {
  scheduled: 'info',
  completed: 'ok',
  cancelled: 'neutral',
  // Someone who did not turn up needs chasing, so it is not merely "not done".
  no_show: 'urgent',
}

export const PROCEDURE_TONES = {
  planned: 'info',
  completed: 'ok',
  aborted: 'urgent',
  cancelled: 'neutral',
}

export const LAB_STATUS_TONES = {
  ordered: 'info',
  resulted: 'ok',
  cancelled: 'neutral',
}
