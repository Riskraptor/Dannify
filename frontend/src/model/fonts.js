import { ref } from 'vue'

// Interface font.
//
// The app used to take whatever Windows offered. That is a safe default and
// it stays the default, but a music player is something people look at for
// hours, and the right typeface is the difference between "an app" and
// "their app". Two are bundled rather than loaded from a CDN, because this
// has to look the same with no network.
//
// The choice is applied by swapping a CSS variable that every rule already
// reads, so nothing else has to know about it.

const STORAGE_KEY = 'dn.font'

const SYSTEM_STACK =
  '"Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system, ' +
  'BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif'
const SYSTEM_DISPLAY =
  '"Segoe UI Variable Display", "Segoe UI", system-ui, -apple-system, ' +
  'BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif'

export const FONTS = [
  {
    id: 'system',
    name: 'fonts.system',
    note: 'fonts.systemNote',
    body: SYSTEM_STACK,
    display: SYSTEM_DISPLAY,
    // A shade tighter than the bundled faces, which are drawn with more
    // generous sidebearings.
    tracking: '0em',
  },
  {
    id: 'inter',
    name: 'fonts.inter',
    note: 'fonts.interNote',
    body: `Inter, ${SYSTEM_STACK}`,
    display: `Inter, ${SYSTEM_DISPLAY}`,
    tracking: '-0.011em',
  },
  {
    id: 'jakarta',
    name: 'fonts.jakarta',
    note: 'fonts.jakartaNote',
    body: `"Plus Jakarta Sans", ${SYSTEM_STACK}`,
    display: `"Plus Jakarta Sans", ${SYSTEM_DISPLAY}`,
    tracking: '-0.014em',
  },
]

const IDS = FONTS.map((f) => f.id)

function load() {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    if (value && IDS.includes(value)) return value
  } catch {
    // Blocked storage: the default is fine.
  }
  return 'system'
}

const current = ref(load())

function apply() {
  const font = FONTS.find((f) => f.id === current.value) || FONTS[0]
  const root = document.documentElement.style
  root.setProperty('--font-body', font.body)
  root.setProperty('--font-display', font.display)
  // Bundled faces are drawn a touch wider than Segoe; without this the
  // difference reads as "the text got bigger" rather than "nicer".
  root.setProperty('--font-tracking', font.tracking)
}

function setFont(id) {
  if (!IDS.includes(id)) return
  current.value = id
  try {
    localStorage.setItem(STORAGE_KEY, id)
  } catch {
    // The choice just will not survive a restart.
  }
  apply()
}

apply()

export function useFonts() {
  return { current, fonts: FONTS, setFont }
}
