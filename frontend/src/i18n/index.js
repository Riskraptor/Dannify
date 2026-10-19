import { ref, shallowRef } from 'vue'
import en from './locales/en.js'

// Registry of available locales. To add a new language:
//   1. Create ./locales/<code>.js exporting the same key shape as en.js
//   2. Add an entry below: `code` is the value stored in localStorage,
//      `name` is the label shown in the language picker, and `load` imports
//      the file. Written out in full, so the bundler makes it a file of its
//      own, fetched only by whoever picks that language.
//
// English is built in: it is the default, and what any missing text falls
// back to. Every other language used to be built in as well, so everybody
// downloaded and read every translation at every start.
export const AVAILABLE_LOCALES = [
  { code: 'en', name: 'English', load: () => Promise.resolve({ default: en }) },
  { code: 'fr', name: 'Français', load: () => import('./locales/fr.js') },
]

// The languages read so far. Replaced, not changed in place, so the page
// redraws in a language the moment it arrives.
const loaded = shallowRef({ en })
const loading = new Map()

function loadLocale(code) {
  if (loaded.value[code]) return Promise.resolve(true)
  const entry = AVAILABLE_LOCALES.find((l) => l.code === code)
  if (!entry) return Promise.resolve(false)
  if (!loading.has(code)) {
    loading.set(
      code,
      entry
        .load()
        .then((mod) => {
          loaded.value = { ...loaded.value, [code]: mod.default }
          return true
        })
        .catch(() => {
          loading.delete(code)
          return false
        })
    )
  }
  return loading.get(code)
}

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

function messagesOf(code) {
  return loaded.value[code] || loaded.value[DEFAULT_LOCALE]
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
  // Not read yet: English until it is.
  if (!loaded.value[code]) code = DEFAULT_LOCALE
  let msg = lookup(messagesOf(code), key)
  if (msg === undefined && code !== DEFAULT_LOCALE) {
    msg = lookup(messagesOf(DEFAULT_LOCALE), key)
    code = DEFAULT_LOCALE
  }
  if (msg === undefined) return format(key, params)
  return format(pluralize(msg, params, code), params)
}

export async function setLocale(code) {
  if (!AVAILABLE_LOCALES.find((l) => l.code === code)) return
  // Switched once the words are here, so nothing is drawn half and half.
  if (!(await loadLocale(code))) return
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

/** Resolves once the language the app starts in can be drawn. */
export const localeReady = loadLocale(currentLocale.value)
