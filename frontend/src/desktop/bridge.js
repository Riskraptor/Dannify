import { reactive, readonly } from 'vue'

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
  minimizeToTray: false,
})

// Python pushes window-state changes through this global (evaluate_js).
window.__dannifyWindowState = (patch) => {
  if (patch && typeof patch === 'object') Object.assign(state, patch)
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
    const s = await call('win_state')
    if (s) Object.assign(state, s)
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
const setOnTop = (on) => call('win_set_on_top', !!on)
const setZoom = (factor) => call('win_set_zoom', Number(factor) || 1)
const setNativeFrame = (on) => call('win_set_native_frame', !!on)
const showSystemMenu = () => call('win_system_menu')
const setTray = (options) => call('tray_set', options)
const setTrayLabels = (labels) => call('tray_labels', labels)
const quit = () => call('app_quit')
const restart = () => call('app_restart')
const installUpdate = (path) => call('app_install_update', String(path || ''))
// Hand the shell a downloaded installer to apply when the app next closes.
const stageUpdate = (path) => call('app_stage_update', String(path || ''))

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
    if (!systemMenu || state.nativeFrame || e.target.closest(INTERACTIVE)) return
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

/** Begin a native resize from one of the invisible edge handles. */
export function beginResize(e, edge) {
  if (!isDesktop || e.button !== 0) return
  e.preventDefault()
  trackGesture(e, () => call('win_start_resize', edge))
}

export const desktop = {
  isDesktop,
  state: readonly(state),
  whenReady,
  minimize,
  toggleMaximize,
  close,
  toggleFullscreen,
  setMini,
  setOnTop,
  setZoom,
  setNativeFrame,
  showSystemMenu,
  setTray,
  setTrayLabels,
  quit,
  restart,
  installUpdate,
  stageUpdate,
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
