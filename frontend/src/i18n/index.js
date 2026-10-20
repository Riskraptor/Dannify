import { ref, shallowRef } from 'vue'
import en from './locales/en.js'
import { restyle } from '/src/model/smoothChange'

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
  { code: 'de', name: 'Deutsch', load: () => import('./locales/de.js') },
  { code: 'es', name: 'Español', load: () => import('./locales/es.js') },
  { code: 'fr', name: 'Français', load: () => import('./locales/fr.js') },
  { code: 'sw', name: 'Kiswahili', load: () => import('./locales/sw.js') },
  { code: 'pt', name: 'Português', load: () => import('./locales/pt.js') },
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
const AUTO = 'auto'

const known = (code) => AVAILABLE_LOCALES.some((l) => l.code === code)

/** The first of this computer's languages Dannify speaks: "pt-BR" is pt. */
export function systemLocale() {
  let wanted = []
  try {
    wanted = navigator.languages?.length ? navigator.languages : [navigator.language]
  } catch {
    // no navigator: English
  }
  for (const tag of wanted) {
    const code = String(tag || '').toLowerCase().split(/[-_]/)[0]
    if (known(code)) return code
  }
  return DEFAULT_LOCALE
}

const stored = (() => {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
})()

// "auto", or a language picked by hand. Nothing picked is automatic: someone
// whose computer is in Kiswahili gets Kiswahili at the first start, without
// looking for it.
export const languageChoice = ref(known(stored) ? stored : AUTO)

const resolve = (choice) => (choice === AUTO ? systemLocale() : choice)

export const currentLocale = ref(resolve(languageChoice.value))

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

// "{count} song | {count} songs" → picks the form for params.count, by each
// language's own rule: French and Portuguese say 0 in the singular, English,
// German, Spanish and Kiswahili only 1.
const rules = new Map()
function isSingular(n, code) {
  if (!rules.has(code)) {
    let rule = null
    try {
      rule = new Intl.PluralRules(code)
    } catch {
      // an engine without it: 1 alone
    }
    rules.set(code, rule)
  }
  const rule = rules.get(code)
  return rule ? rule.select(n) === 'one' : n === 1
}

function pluralize(msg, params, code) {
  if (!params || typeof params.count !== 'number' || !msg.includes(' | ')) {
    return msg
  }
  const [one, other] = msg.split(' | ')
  return isSingular(Math.abs(params.count), code) ? one : other ?? one
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

function remember(choice) {
  try {
    if (choice === AUTO) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, choice)
  } catch {
    // ignore storage errors (private mode, etc.)
  }
}

function applyLang(code) {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('lang', code)
  }
}

let switching = 0

/**
 * Switch to *choice*: a language's code, or "auto" to follow the computer.
 * The words are read first and the page then cross-fades into them, the way
 * a palette changes, so nothing is ever drawn half in one language and half
 * in the other.
 */
export async function setLocale(choice) {
  if (choice !== AUTO && !known(choice)) return
  const code = resolve(choice)
  const ticket = ++switching
  if (!(await loadLocale(code))) return
  // Two picks in a row: the last one wins, whichever file arrived first.
  if (ticket !== switching) return
  languageChoice.value = choice
  remember(choice)
  if (code === currentLocale.value) return
  await restyle(() => {
    currentLocale.value = code
    applyLang(code)
  })
}

// Following the computer: when its language is changed while Dannify is open,
// Dannify changes with it.
if (typeof window !== 'undefined') {
  window.addEventListener('languagechange', () => {
    if (languageChoice.value === AUTO) setLocale(AUTO)
  })
}

export function useI18n() {
  return {
    t,
    locale: currentLocale,
    choice: languageChoice,
    setLocale,
    locales: AVAILABLE_LOCALES,
    systemLocale,
  }
}

// Apply on initial load
applyLang(currentLocale.value)

/** Resolves once the language the app starts in can be drawn. */
export const localeReady = loadLocale(currentLocale.value).then((ok) => {
  // A language file that cannot be read: English, rather than English words
  // in a page that says it is something else.
  if (!ok && currentLocale.value !== DEFAULT_LOCALE) {
    currentLocale.value = DEFAULT_LOCALE
    applyLang(DEFAULT_LOCALE)
  }
  return ok
})
