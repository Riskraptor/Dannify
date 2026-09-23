import { ref, computed } from 'vue'
import { desktop } from '/src/desktop/bridge'

// Theme preference: 'system' follows Windows' app mode live; 'dark' and
// 'light' pin it. Persisted so the app opens the way the user left it.

const STORAGE_KEY = 'dn.theme'
const THEMES = { dark: 'dannify-dark', light: 'dannify-light' }

const media = window.matchMedia('(prefers-color-scheme: dark)')

function loadPreference() {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'dark' || v === 'light' || v === 'system') return v
  } catch {
    // ignore
  }
  return 'system'
}

const preference = ref(loadPreference())
const systemTheme = ref(media.matches ? 'dark' : 'light')
media.addEventListener('change', (e) => {
  systemTheme.value = e.matches ? 'dark' : 'light'
  apply()
})

const currentTheme = computed(() =>
  preference.value === 'system' ? systemTheme.value : preference.value
)

function apply() {
  const theme = currentTheme.value
  document.documentElement.setAttribute('data-theme', THEMES[theme])
  document.documentElement.style.colorScheme = theme
  desktop.setTheme(theme)
}

function setPreference(value) {
  if (!['system', 'dark', 'light'].includes(value)) return
  preference.value = value
  try {
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    // ignore
  }
  apply()
}

function toggleTheme() {
  setPreference(currentTheme.value === 'dark' ? 'light' : 'dark')
}

apply()

export function useTheme() {
  return { preference, currentTheme, setPreference, toggleTheme }
}
