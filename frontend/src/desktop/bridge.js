import { computed, reactive, readonly, watch } from 'vue'

// ---------------------------------------------------------------------------
// Bridge to the native desktop shell (Backend/desktop.py → pywebview js_api).
//
// The same frontend is also served to plain browsers on the LAN, so every
// call here degrades to a no-op when we're not inside the desktop window.
// ---------------------------------------------------------------------------

const SHELL_KEY = 'dannify-shell'

function detectDesktop() {
  try {
    const params = new URLSearchParams(window.location.search)
    if (params.get('shell') === 'desktop') {
      sessionStorage.setItem(SHELL_KEY, 'desktop')
      // Drop the markers from the address so the router never sees them,
      // and so the session key never sits in the visible URL. The server
      // has already traded it for a cookie by now.
      params.delete('shell')
      params.delete('k')
      const qs = params.toString()
      window.history.replaceState(
        window.history.state,
        '',
        window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash
      )
      return true
    }
    if (sessionStorage.getItem(SHELL_KEY) === 'desktop') return true
  } catch {
    // storage blocked: fall through
  }
  return !!window.pywebview
}

export const isDesktop = detectDesktop()

const PLATFORMS = ['windows', 'macos', 'linux']

/**
 * Which system this is: 'windows', 'macos' or 'linux'. The shell says for
 * certain (the `platform` in win_state); until it has, and in a plain
 * browser on the LAN, the browser's own report is the best guess. The newer report
 * (userAgentData) is asked first, the old ones after it.
 */
export function detectPlatform(nav = typeof navigator !== 'undefined' ? navigator : null) {
  if (!nav) return 'windows'
  const reports = [nav.userAgentData && nav.userAgentData.platform, nav.platform, nav.userAgent]
  for (const report of reports) {
    const r = String(report || '').toLowerCase()
    if (!r) continue
    if (/mac|darwin|iphone|ipad/.test(r)) return 'macos'
    if (/win/.test(r)) return 'windows'
    if (/linux|x11|cros|bsd/.test(r)) return 'linux'
  }
  return 'windows'
}

if (isDesktop) document.documentElement.classList.add('is-desktop')

const state = reactive({
  ready: false, // js_api reachable
  maximized: false,
  minimized: false,
  fullscreen: false,
  focused: true,
  mini: false,
  onTop: false,
  // True when Windows draws its own title bar (user preference, or the
  // custom frame couldn't be installed): we then hide our caption buttons.
  nativeFrame: false,
  nativeFramePref: false, // saved preference (applies on next launch)
  closeToTray: false,
  globalHotkeys: false,
  hotkeysTaken: [],
  autostart: { available: false, on: false },
  // Windows takes the mouse over the maximize button so it can offer the
  // snap layouts, which means the button never gets :hover. It tells us
  // instead; see bindMaxButton below.
  maxHover: false,
  platform: detectPlatform(),
})

// What the shell reports, minus a platform it has no business naming.
function applyState(patch) {
  if (!patch || typeof patch !== 'object') return
  const next = { ...patch }
  if ('platform' in next && !PLATFORMS.includes(next.platform)) delete next.platform
  Object.assign(state, next)
}

// Python pushes window-state changes through this global (evaluate_js).
window.__dannifyWindowState = applyState

// Styles that differ by system (the caption buttons, the title bar) key off
// this rather than asking the browser again.
watch(
  () => state.platform,
  (p) => {
    if (typeof document !== 'undefined') document.documentElement.dataset.platform = p
  },
  { immediate: true }
)

window.__dannifyMaxHover = (on) => {
  state.maxHover = !!on
}

let readyPromise = null
function apiReady() {
  const api = window.pywebview && window.pywebview.api
  return !!(api && typeof api.win_state === 'function')
}

export function whenReady() {
  if (!isDesktop) return Promise.resolve(false)
  if (state.ready) return Promise.resolve(true)
  if (!readyPromise) {
    readyPromise = new Promise((resolve) => {
      const done = () => {
        if (state.ready) return
        state.ready = true
        resolve(true)
      }
      if (apiReady()) return done()
      window.addEventListener('pywebviewready', done, { once: true })
      // Belt and braces: poll in case the event fired before we listened.
      const poll = setInterval(() => {
        if (apiReady()) {
          clearInterval(poll)
          done()
        }
      }, 100)
      setTimeout(() => clearInterval(poll), 30000)
    })
  }
  return readyPromise
}

// Stop talking to the native shell while the page is going away: the window
// may already be destroyed on the other side.
let shuttingDown = false
if (isDesktop) {
  window.addEventListener('beforeunload', () => (shuttingDown = true))
  window.addEventListener('pagehide', () => (shuttingDown = true))
}

async function call(name, ...args) {
  if (!isDesktop || shuttingDown) return undefined
  await whenReady()
  const fn = window.pywebview && window.pywebview.api && window.pywebview.api[name]
  if (typeof fn !== 'function') return undefined
  try {
    return await fn(...args)
  } catch (err) {
    console.warn(`[desktop] ${name} failed`, err)
    return undefined
  }
}

if (isDesktop) {
  whenReady().then(async () => {
    applyState(await call('win_state'))
  })
  window.addEventListener('focus', () => (state.focused = true))
  window.addEventListener('blur', () => (state.focused = false))
}

// --- Window commands ------------------------------------------------------
const minimize = () => call('win_minimize')
const toggleMaximize = () => call('win_toggle_maximize')
const close = () => call('win_close')
const toggleFullscreen = () => call('win_toggle_fullscreen')
const setMini = (on) => call('win_set_mini', !!on)
// Height of the compact player, in CSS pixels: it unfolds when the
// lyrics or the queue are shown inside it.
const setMiniSize = (height) => call('win_set_mini_size', Number(height) || 0)
const setOnTop = (on) => call('win_set_on_top', !!on)
const setZoom = (factor) => call('win_set_zoom', Number(factor) || 1)
const setNativeFrame = (on) => call('win_set_native_frame', !!on)
const showSystemMenu = () => call('win_system_menu')
const setMaxButton = (rect) => call('win_set_max_button', rect || null)
const setTray = (options) => call('tray_set', options)
const setGlobalHotkeys = (on) => call('app_set_global_hotkeys', !!on)
const setAutostart = (on) => call('app_set_autostart', !!on)
const openSoundSettings = () => call('shell_open_sound_settings')
const setTrayLabels = (labels) => call('tray_labels', labels)
const quit = () => call('app_quit')
const restart = () => call('app_restart')
const installUpdate = (path) => call('app_install_update', String(path || ''))
// Hand the shell a downloaded installer to apply when the app next closes.
// Only a copy that cannot update in place uses this; an installed one gets
// its updates ready beside itself and the launcher swaps them in.
const stageUpdate = (path) => call('app_stage_update', String(path || ''))
const clearStagedUpdate = () => call('app_clear_staged_update')

// --- YouTube Music account --------------------------------------------------
// The sign-in itself happens in a real Google window opened by the shell;
// this only starts it and waits for the result.
const accountSignIn = () => call('account_sign_in')
const accountClearSession = () => call('account_clear_session')

// --- Shell integration ------------------------------------------------------
const revealInFolder = (file) => call('shell_reveal', String(file || ''))
const openLibraryFolder = () => call('shell_open_library')
const openExternal = (url) => {
  if (!isDesktop) {
    window.open(url, '_blank', 'noopener')
    return Promise.resolve()
  }
  return call('shell_open_external', String(url || ''))
}
const setTheme = (theme) => call('app_set_theme', theme)
const readClipboard = () => call('clipboard_read')
const setTaskbarProgress = (value, mode = 'normal') =>
  call('taskbar_progress', Number(value) || 0, mode)
const setPlaybackState = (payload) => call('taskbar_playback', payload)

// --- Native drag / resize ---------------------------------------------------
// We never move the window from JS. Once the pointer has travelled a couple
// of pixels we hand the gesture to Windows' own move/size loop, which gives
// Aero Snap, drag-to-restore and native resize cursors for free.
const INTERACTIVE =
  'button, a, input, textarea, select, label, [role="button"], [role="slider"], [data-no-drag]'
const THRESHOLD = 3

function trackGesture(e, onStart) {
  const sx = e.screenX
  const sy = e.screenY
  function move(ev) {
    if ((ev.buttons & 1) === 0) return stop()
    if (Math.abs(ev.screenX - sx) >= THRESHOLD || Math.abs(ev.screenY - sy) >= THRESHOLD) {
      stop()
      onStart()
    }
  }
  function stop() {
    window.removeEventListener('mousemove', move, true)
    window.removeEventListener('mouseup', stop, true)
  }
  window.addEventListener('mousemove', move, true)
  window.addEventListener('mouseup', stop, true)
}

/** Make `el` behave like a native title bar. Returns a cleanup function. */
export function bindWindowDrag(el, { systemMenu = true } = {}) {
  if (!isDesktop || !el) return () => {}
  function onDown(e) {
    if (e.button !== 0 || e.target.closest(INTERACTIVE)) return
    if (state.fullscreen) return
    if (e.detail === 2) {
      toggleMaximize()
      return
    }
    trackGesture(e, () => call('win_start_drag'))
  }
  // Right-click on empty title-bar space → the real Windows system menu.
  function onMenu(e) {
    // Only Windows has a system menu to show; elsewhere the click is ignored.
    if (!systemMenu || state.nativeFrame || state.platform !== 'windows' || e.target.closest(INTERACTIVE)) return
    e.preventDefault()
    e.stopPropagation()
    showSystemMenu()
  }
  el.addEventListener('mousedown', onDown)
  el.addEventListener('contextmenu', onMenu)
  return () => {
    el.removeEventListener('mousedown', onDown)
    el.removeEventListener('contextmenu', onMenu)
  }
}

/**
 * Tell Windows where the maximize button is, so hovering it opens the snap
 * layout flyout like every other Windows 11 window.
 *
 * The button is ours, drawn in the page, so the shell would otherwise have
 * no idea it exists. Reporting its rectangle is the whole handshake: from
 * then on Windows treats that patch as part of the frame, and the hover and
 * the click come back to us through the bridge.
 */
export function bindMaxButton(el) {
  if (!isDesktop || !el) return () => {}
  let last = ''
  let frame = 0

  const report = () => {
    frame = 0
    const box = el.getBoundingClientRect()
    if (!box.width || !box.height || state.fullscreen || state.mini || state.nativeFrame) {
      if (last !== 'none') {
        last = 'none'
        setMaxButton(null)
      }
      return
    }
    // Device pixels: devicePixelRatio already carries both the monitor's
    // scaling and whatever zoom the user picked.
    const dpr = window.devicePixelRatio || 1
    const rect = {
      left: Math.round(box.left * dpr),
      top: Math.round(box.top * dpr),
      right: Math.round(box.right * dpr),
      bottom: Math.round(box.bottom * dpr),
    }
    const key = `${rect.left},${rect.top},${rect.right},${rect.bottom}`
    if (key === last) return
    last = key
    setMaxButton(rect)
  }

  const schedule = () => {
    if (!frame) frame = requestAnimationFrame(report)
  }

  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(schedule) : null
  if (observer) observer.observe(el)
  window.addEventListener('resize', schedule)
  const stopWatch = watch(
    () => [state.maximized, state.fullscreen, state.mini, state.nativeFrame],
    schedule
  )
  schedule()

  return () => {
    if (frame) cancelAnimationFrame(frame)
    if (observer) observer.disconnect()
    window.removeEventListener('resize', schedule)
    stopWatch()
    setMaxButton(null)
  }
}

/** Begin a native resize from one of the invisible edge handles. */
export function beginResize(e, edge) {
  if (!isDesktop || e.button !== 0) return
  e.preventDefault()
  trackGesture(e, () => call('win_start_resize', edge))
}

/** The system this runs on, as a ref: 'windows', 'macos' or 'linux'. */
export const platform = computed(() => state.platform)

export function usePlatform() {
  return platform
}

export const desktop = {
  isDesktop,
  platform,
  state: readonly(state),
  whenReady,
  minimize,
  toggleMaximize,
  close,
  toggleFullscreen,
  setMini,
  setMiniSize,
  setOnTop,
  setZoom,
  setNativeFrame,
  showSystemMenu,
  setMaxButton,
  setTray,
  setTrayLabels,
  setGlobalHotkeys,
  setAutostart,
  openSoundSettings,
  quit,
  restart,
  installUpdate,
  stageUpdate,
  clearStagedUpdate,
  accountSignIn,
  accountClearSession,
  revealInFolder,
  openLibraryFolder,
  openExternal,
  setTheme,
  readClipboard,
  setTaskbarProgress,
  setPlaybackState,
}

export function useDesktop() {
  return desktop
}
