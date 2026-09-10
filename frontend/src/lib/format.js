/**
 * Formatting, in one module so a date looks the same on every screen.
 *
 * All of it is Arabic (`ar-EG`) with **Latin digits**. That combination is
 * deliberate: Egyptian clinics read prices, phone numbers and record numbers
 * in Latin digits, and `Intl` defaults to Arabic-Indic ones for this locale,
 * which turns a familiar receipt into something staff have to decode.
 */

const LOCALE = 'ar-EG-u-nu-latn'

const dateFormatter = new Intl.DateTimeFormat(LOCALE, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
})

const dateTimeFormatter = new Intl.DateTimeFormat(LOCALE, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

const timeFormatter = new Intl.DateTimeFormat(LOCALE, {
  hour: '2-digit',
  minute: '2-digit',
})

const moneyFormatter = new Intl.NumberFormat(LOCALE, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

function toDate(value) {
  if (!value) return null
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDate(value, fallback = '—') {
  const date = toDate(value)
  return date ? dateFormatter.format(date) : fallback
}

export function formatDateTime(value, fallback = '—') {
  const date = toDate(value)
  return date ? dateTimeFormatter.format(date) : fallback
}

export function formatTime(value, fallback = '—') {
  const date = toDate(value)
  return date ? timeFormatter.format(date) : fallback
}

/** Money. The currency word is appended rather than formatted by `Intl`,
 *  which places "ج.م." unpredictably in RTL and breaks column alignment. */
export function formatMoney(value, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback
  const number = Number(value)
  if (Number.isNaN(number)) return fallback
  return `${moneyFormatter.format(number)} ج.م`
}

export function formatNumber(value, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback
  const number = Number(value)
  if (Number.isNaN(number)) return fallback
  return new Intl.NumberFormat(LOCALE).format(number)
}

/** "منذ ٣ أيام" — for timelines, where the gap matters more than the date. */
export function formatRelative(value) {
  const date = toDate(value)
  if (!date) return '—'
  const seconds = Math.round((date.getTime() - Date.now()) / 1000)
  const relative = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' })
  const units = [
    ['year', 31536000],
    ['month', 2592000],
    ['week', 604800],
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ]
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) {
      return relative.format(Math.round(seconds / size), unit)
    }
  }
  return relative.format(seconds, 'second')
}

/** `YYYY-MM-DD`, which is what `<input type="date">` and the API both want. */
export function toDateInput(value) {
  const date = toDate(value)
  if (!date) return ''
  const pad = (part) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** `YYYY-MM-DDTHH:mm` for `<input type="datetime-local">`. */
export function toDateTimeInput(value) {
  const date = toDate(value)
  if (!date) return ''
  const pad = (part) => String(part).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

export function today() {
  return toDateInput(new Date())
}

export function startOfMonth() {
  const now = new Date()
  return toDateInput(new Date(now.getFullYear(), now.getMonth(), 1))
}

export function fileSize(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} بايت`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} ك.ب`
  return `${(bytes / (1024 * 1024)).toFixed(1)} م.ب`
}

/** First letters of a name, for an avatar. Handles the Arabic "عبد الله". */
export function initials(name) {
  if (!name) return '؟'
  const parts = String(name).trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '؟'
  if (parts.length === 1) return parts[0].slice(0, 1)
  return parts[0].slice(0, 1) + parts[parts.length - 1].slice(0, 1)
}
