import { ref, computed } from 'vue'
import { desktop } from '/src/desktop/bridge'

// Theme preference.
//
// Two axes, deliberately kept apart:
//
//   mode  - 'system' | 'dark' | 'light'. Whether the app is dark or light,
//           with 'system' following Windows live.
//   theme - which palette to use within that mode.
//
// Keeping them separate is what makes "follow Windows" still work once
// there is more than one dark palette: the app switches between the dark
// and light palette the user picked, rather than dropping back to a default.

const MODE_KEY = 'dn.theme'
const DARK_KEY = 'dn.theme.dark'
const LIGHT_KEY = 'dn.theme.light'

// `id` is the [data-theme] value minus the prefix; `swatch` is what the
// picker paints, taken straight from the palette so the two cannot drift.
export const THEMES = [
  { id: 'dark', mode: 'dark', name: 'theme.midnight', bg: '#121215', accent: '#1AD05C' },
  { id: 'graphite', mode: 'dark', name: 'theme.graphite', bg: '#16191E', accent: '#58A6FF' },
  { id: 'deepsea', mode: 'dark', name: 'theme.deepsea', bg: '#0E1821', accent: '#2DD4BF' },
  { id: 'orchid', mode: 'dark', name: 'theme.orchid', bg: '#18121F', accent: '#D674FF' },
  { id: 'ember', mode: 'dark', name: 'theme.ember', bg: '#1C1512', accent: '#FF963C' },
  { id: 'aurora', mode: 'dark', name: 'theme.aurora', bg: '#111324', accent: '#818CF8' },
  { id: 'rose', mode: 'dark', name: 'theme.rose', bg: '#1B1216', accent: '#FB7196' },
  { id: 'forest', mode: 'dark', name: 'theme.forest', bg: '#0F1813', accent: '#84CC16' },
  { id: 'light', mode: 'light', name: 'theme.paper', bg: '#FFFFFF', accent: '#0E7935' },
  { id: 'sand', mode: 'light', name: 'theme.sand', bg: '#FDFAF5', accent: '#A04C10' },
  { id: 'sky', mode: 'light', name: 'theme.sky', bg: '#FAFCFF', accent: '#1D64D6' },
]

const DARK_IDS = THEMES.filter((t) => t.mode === 'dark').map((t) => t.id)
const LIGHT_IDS = THEMES.filter((t) => t.mode === 'light').map((t) => t.id)

const media = window.matchMedia('(prefers-color-scheme: dark)')

function read(key, allowed, fallback) {
  try {
    const v = localStorage.getItem(key)
    if (v && allowed.includes(v)) return v
  } catch {
    // Blocked storage: the default is fine.
  }
  return fallback
}

function write(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Not worth surfacing: the choice just will not survive a restart.
  }
}

const preference = ref(read(MODE_KEY, ['system', 'dark', 'light'], 'system'))
const darkTheme = ref(read(DARK_KEY, DARK_IDS, 'dark'))
const lightTheme = ref(read(LIGHT_KEY, LIGHT_IDS, 'light'))
const systemMode = ref(media.matches ? 'dark' : 'light')

media.addEventListener('change', (e) => {
  systemMode.value = e.matches ? 'dark' : 'light'
  apply()
})

// Dark or light, once 'system' has been resolved.
const currentMode = computed(() =>
  preference.value === 'system' ? systemMode.value : preference.value
)
// The palette actually on screen.
const currentTheme = computed(() =>
  currentMode.value === 'dark' ? darkTheme.value : lightTheme.value
)

function apply() {
  document.documentElement.setAttribute('data-theme', `dannify-${currentTheme.value}`)
  // Light or dark, whichever palette: what light-mode styling keys on, so a
  // second light palette (Sand) is not left wearing dark-mode colours.
  document.documentElement.setAttribute('data-mode', currentMode.value)
  document.documentElement.style.colorScheme = currentMode.value
  // The native frame follows, so the title bar and the page never disagree.
  desktop.setTheme(currentMode.value)
}

function setPreference(value) {
  if (!['system', 'dark', 'light'].includes(value)) return
  preference.value = value
  write(MODE_KEY, value)
  apply()
}

/** Pick a palette. Also switches mode to match, so choosing a light theme
 *  from a dark one does what the user obviously meant. */
function setTheme(id) {
  const theme = THEMES.find((t) => t.id === id)
  if (!theme) return
  if (theme.mode === 'dark') {
    darkTheme.value = id
    write(DARK_KEY, id)
  } else {
    lightTheme.value = id
    write(LIGHT_KEY, id)
  }
  if (preference.value !== 'system' || systemMode.value !== theme.mode) {
    setPreference(theme.mode)
  } else {
    apply()
  }
}

function toggleTheme() {
  setPreference(currentMode.value === 'dark' ? 'light' : 'dark')
}

apply()

export function useTheme() {
  return {
    preference,
    currentMode,
    currentTheme,
    darkTheme,
    lightTheme,
    themes: THEMES,
    setPreference,
    setTheme,
    toggleTheme,
  }
}
