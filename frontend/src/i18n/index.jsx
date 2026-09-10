/**
 * Language and direction.
 *
 * Words live in `ar.json` and `en.json`, keyed by meaning (`intake.steps.personal`),
 * never in components. Choosing a language sets `<html lang dir>`, so every
 * stylesheet written with logical properties (`margin-inline`, `inset-inline`)
 * flips on its own.
 *
 * Choice values arrive from the server as codes (`/api/meta/choices/`) and are
 * shown through `choices.<group>.<code>`; the screens keep no copy of any list.
 * `api/tests/test_translations.py` fails if a code or a key used in a screen
 * has no word in either language.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { setFormatLocale } from '@/lib/format'

import ar from './ar.json'
import en from './en.json'

const DICTIONARIES = { ar, en }

export const LANGUAGES = [
  { code: 'ar', label: 'العربية', dir: 'rtl' },
  { code: 'en', label: 'English', dir: 'ltr' },
]

const KEY = 'clinic-lang'

// localStorage throws, rather than returning null, where site data is
// blocked; a language preference must never take the app down.
function stored() {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

function persist(value) {
  try {
    localStorage.setItem(KEY, value)
  } catch {
    /* the choice still applies for this session */
  }
}

const I18nContext = createContext(null)

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(() => (DICTIONARIES[stored()] ? stored() : 'ar'))
  const dir = LANGUAGES.find((language) => language.code === lang)?.dir ?? 'rtl'

  // Applied during render as well as in the effect, so the first paint is
  // already in the right direction.
  setFormatLocale(lang)

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = dir
    persist(lang)
  }, [lang, dir])

  const t = useCallback(
    (key, vars) => {
      let text = DICTIONARIES[lang][key] ?? DICTIONARIES.ar[key] ?? key
      if (vars) {
        Object.entries(vars).forEach(([name, value]) => {
          text = text.split(`{${name}}`).join(String(value))
        })
      }
      return text
    },
    [lang],
  )

  const value = useMemo(() => ({ lang, dir, setLang, t }), [lang, dir, t])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useT() {
  const context = useContext(I18nContext)
  if (!context) throw new Error('useT must be used inside <LanguageProvider>')
  return context
}

/** `[{ value, label }]` for a select, from server codes. */
export function choiceOptions(t, group, codes = []) {
  return codes.map((code) => ({ value: code, label: t(`choices.${group}.${code}`) }))
}
