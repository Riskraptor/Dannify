import { ref, computed, watch } from 'vue'

// Global shell/UI state. Module-scoped so it survives navigation and is
// shared by the title bar, sidebar, player bar and side panel. Anything the
// user would expect a desktop app to remember is persisted to localStorage.

function load(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw === null ? fallback : JSON.parse(raw)
  } catch {
    return fallback
  }
}

function persist(key, source) {
  watch(
    source,
    (value) => {
      try {
        localStorage.setItem(key, JSON.stringify(value))
      } catch {
        // storage full / blocked: not fatal
      }
    },
    { deep: true }
  )
}

// --- Viewport (drives the responsive shell) ---------------------------------
const viewport = ref({ w: window.innerWidth, h: window.innerHeight })
let resizeRaf = 0
window.addEventListener('resize', () => {
  cancelAnimationFrame(resizeRaf)
  resizeRaf = requestAnimationFrame(() => {
    viewport.value = { w: window.innerWidth, h: window.innerHeight }
  })
})

// Phone-sized browsers on the LAN get a drawer instead of a sidebar.
const isCompact = computed(() => viewport.value.w < 700)
// Narrow windows fall back to the icon rail automatically.
const forceRail = computed(() => !isCompact.value && viewport.value.w < 1000)

// --- Sidebar ------------------------------------------------------------------
const sidebarCollapsedPref = ref(load('dn.sidebarCollapsed', false))
persist('dn.sidebarCollapsed', sidebarCollapsedPref)
const sidebarCollapsed = computed(
  () => forceRail.value || sidebarCollapsedPref.value
)
const drawerOpen = ref(false)

function toggleSidebar() {
  if (isCompact.value) {
    drawerOpen.value = !drawerOpen.value
    return
  }
  if (forceRail.value) return
  sidebarCollapsedPref.value = !sidebarCollapsedPref.value
}

// --- Right side panel (queue / lyrics) --------------------------------------
const panel = ref(load('dn.panel', null)) // 'queue' | 'lyrics' | 'about' | null
persist('dn.panel', panel)
const panelWidth = ref(load('dn.panelWidth', 340))
persist('dn.panelWidth', panelWidth)
// Dock the panel beside the content when there's room, float it otherwise.
const panelFloating = computed(() => viewport.value.w < 1100)

export const PANEL_MIN = 300
export const PANEL_MAX = 560

function setPanel(name) {
  panel.value = panel.value === name ? null : name
}
function openPanel(name) {
  panel.value = name
}
function closePanel() {
  panel.value = null
}
function setPanelWidth(px) {
  panelWidth.value = Math.round(Math.max(PANEL_MIN, Math.min(PANEL_MAX, px)))
}

// Open lyrics automatically the first time something plays in a session.
const autoOpenLyrics = ref(load('dn.autoOpenLyrics', true))
persist('dn.autoOpenLyrics', autoOpenLyrics)

// Whether the lyric sync-nudge bar is open (header control ↔ lyrics panel).
const lyricsSyncOpen = ref(false)

// Title-bar search box: views can ask for focus (Ctrl+K, "Search" nav).
const searchFocusTick = ref(0)
function focusSearch() {
  searchFocusTick.value++
}

// Keyboard-shortcut cheat sheet (Ctrl+/).
const shortcutsOpen = ref(false)

export function useUi() {
  return {
    viewport,
    isCompact,
    forceRail,
    sidebarCollapsed,
    sidebarCollapsedPref,
    drawerOpen,
    toggleSidebar,
    panel,
    panelWidth,
    panelFloating,
    setPanel,
    openPanel,
    closePanel,
    setPanelWidth,
    autoOpenLyrics,
    lyricsSyncOpen,
    searchFocusTick,
    focusSearch,
    shortcutsOpen,
  }
}
