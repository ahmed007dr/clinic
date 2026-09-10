/**
 * Formatting, in one module so a date looks the same on every screen.
 *
 * Arabic uses `ar-EG` with **Latin digits**: Egyptian clinics read prices,
 * phone numbers and record numbers in Latin digits, and `Intl` defaults to
 * Arabic-Indic ones for this locale. English uses `en-GB` (day before month,
 * as dates are read in Egypt). The language is set by `i18n/index.jsx`.
 */

const LOCALES = { ar: 'ar-EG-u-nu-latn', en: 'en-GB' }
const CURRENCY = { ar: 'ج.م', en: 'EGP' }
const SIZES = { ar: ['بايت', 'ك.ب', 'م.ب'], en: ['B', 'KB', 'MB'] }

let current = 'ar'
const cache = {}

export function setFormatLocale(lang) {
  if (LOCALES[lang]) current = lang
}

function formatter(kind) {
  const key = `${current}:${kind}`
  if (!cache[key]) {
    const locale = LOCALES[current]
    const options = {
      date: { year: 'numeric', month: 'short', day: 'numeric' },
      datetime: { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' },
      time: { hour: '2-digit', minute: '2-digit' },
    }[kind]
    cache[key] =
      kind === 'money'
        ? new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
        : kind === 'number'
          ? new Intl.NumberFormat(locale)
          : new Intl.DateTimeFormat(locale, options)
  }
  return cache[key]
}

function toDate(value) {
  if (!value) return null
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDate(value, fallback = '—') {
  const date = toDate(value)
  return date ? formatter('date').format(date) : fallback
}

export function formatDateTime(value, fallback = '—') {
  const date = toDate(value)
  return date ? formatter('datetime').format(date) : fallback
}

export function formatTime(value, fallback = '—') {
  const date = toDate(value)
  return date ? formatter('time').format(date) : fallback
}

/** Money. The currency word is appended rather than formatted by `Intl`,
 *  which places it unpredictably in RTL and breaks column alignment. */
export function formatMoney(value, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback
  const number = Number(value)
  if (Number.isNaN(number)) return fallback
  return `${formatter('money').format(number)} ${CURRENCY[current]}`
}

export function formatNumber(value, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback
  const number = Number(value)
  if (Number.isNaN(number)) return fallback
  return formatter('number').format(number)
}

/** "منذ ٣ أيام" / "3 days ago" — for timelines, where the gap matters. */
export function formatRelative(value) {
  const date = toDate(value)
  if (!date) return '—'
  const seconds = Math.round((date.getTime() - Date.now()) / 1000)
  const relative = new Intl.RelativeTimeFormat(LOCALES[current], { numeric: 'auto' })
  const units = [
    ['year', 31536000],
    ['month', 2592000],
    ['week', 604800],
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ]
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit)
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
  const [b, kb, mb] = SIZES[current]
  if (bytes < 1024) return `${bytes} ${b}`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} ${kb}`
  return `${(bytes / (1024 * 1024)).toFixed(1)} ${mb}`
}

/** Completed years between a birth date and today. */
export function ageFrom(value) {
  const born = toDate(value)
  if (!born) return null
  const now = new Date()
  let age = now.getFullYear() - born.getFullYear()
  const beforeBirthday =
    now.getMonth() < born.getMonth() ||
    (now.getMonth() === born.getMonth() && now.getDate() < born.getDate())
  if (beforeBirthday) age -= 1
  return age >= 0 ? age : null
}

/** First letters of a name, for an avatar. Handles the Arabic "عبد الله". */
export function initials(name) {
  if (!name) return '؟'
  const parts = String(name).trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '؟'
  if (parts.length === 1) return parts[0].slice(0, 1)
  return parts[0].slice(0, 1) + parts[parts.length - 1].slice(0, 1)
}
