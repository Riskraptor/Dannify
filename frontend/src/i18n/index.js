import { ref } from 'vue'
import en from './locales/en.js'
import fr from './locales/fr.js'

// Registry of available locales. To add a new language:
//   1. Create ./locales/<code>.js exporting the same key shape as en.js
//   2. Import it above
//   3. Add an entry below: `code` is the value stored in localStorage,
//      `name` is the label shown in the language picker.
export const AVAILABLE_LOCALES = [
  { code: 'en', name: 'English', messages: en },
  { code: 'fr', name: 'Français', messages: fr },
]

const DEFAULT_LOCALE = 'en'
const STORAGE_KEY = 'dannify-locale'

const stored = (() => {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
})()

const initial = AVAILABLE_LOCALES.find((l) => l.code === stored)
  ? stored
  : DEFAULT_LOCALE

export const currentLocale = ref(initial)

function localeData(code) {
  return (
    AVAILABLE_LOCALES.find((l) => l.code === code) ||
    AVAILABLE_LOCALES.find((l) => l.code === DEFAULT_LOCALE)
  )
}

function lookup(messages, key) {
  if (!messages) return undefined
  const parts = key.split('.')
  let cur = messages
  for (const p of parts) {
    if (cur == null || typeof cur !== 'object') return undefined
    cur = cur[p]
  }
  return typeof cur === 'string' ? cur : undefined
}

function format(template, params) {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (_, name) =>
    params[name] !== undefined && params[name] !== null
      ? String(params[name])
      : `{${name}}`
  )
}

// "{count} song | {count} songs" → picks the form for params.count.
// French treats 0 and 1 as singular; English only 1.
function pluralize(msg, params, code) {
  if (!params || typeof params.count !== 'number' || !msg.includes(' | ')) {
    return msg
  }
  const [one, other] = msg.split(' | ')
  const n = Math.abs(params.count)
  const singular = code === 'fr' ? n < 2 : n === 1
  return singular ? one : other ?? one
}

export function t(key, params) {
  let code = currentLocale.value
  let msg = lookup(localeData(code).messages, key)
  if (msg === undefined && code !== DEFAULT_LOCALE) {
    msg = lookup(localeData(DEFAULT_LOCALE).messages, key)
    code = DEFAULT_LOCALE
  }
  if (msg === undefined) return format(key, params)
  return format(pluralize(msg, params, code), params)
}

export function setLocale(code) {
  if (!AVAILABLE_LOCALES.find((l) => l.code === code)) return
  currentLocale.value = code
  try {
    localStorage.setItem(STORAGE_KEY, code)
  } catch {
    // ignore storage errors (private mode, etc.)
  }
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('lang', code)
  }
}

export function useI18n() {
  return {
    t,
    locale: currentLocale,
    setLocale,
    locales: AVAILABLE_LOCALES,
  }
}

// Apply on initial load
if (typeof document !== 'undefined') {
  document.documentElement.setAttribute('lang', currentLocale.value)
}
