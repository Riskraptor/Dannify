import router from '/src/router'
import { useUi } from '/src/model/ui'
import { desktop } from '/src/desktop/bridge'
import { openContextMenu } from '/src/model/contextMenu'
import { copyText, readText } from '/src/model/clipboard'
import { useOnboarding } from '/src/model/onboarding'
import { t } from '/src/i18n'
import { ensureFullWindow } from '/src/desktop/fullWindow'

// App-wide keyboard shortcuts and right-click behaviour. Playback keys
// (Space, arrows, M/N/P/S/R) live in model/player.js.

function isTyping(el) {
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}

// Interface size. This used to be Ctrl with plus, minus and zero, exactly as
// a browser does it, and Ctrl with the scroll wheel on top of that. That is
// the single most website-like thing an app can do: nobody expects a desktop
// program to reflow because they scrolled with a finger on Ctrl. The keys and
// the wheel are gone. It is a setting now, under Appearance.
export const ZOOM_KEY = 'dn.zoom'
// Kept deliberately short. The window can be as narrow as 760 physical
// pixels, and zooming divides that: at 150 per cent the interface saw 507
// pixels of room, dropped into the narrow layout meant for a phone browser,
// and started overlapping itself. The shell widens the window minimum to
// match whatever is picked here, so none of these can collapse the layout.
export const ZOOM_STEPS = [0.9, 1, 1.1, 1.25]

export function currentZoom() {
  let v = 1
  try {
    v = parseFloat(localStorage.getItem(ZOOM_KEY) || '1')
  } catch {
    // Storage that throws (a private window): the default size.
  }
  return ZOOM_STEPS.includes(v) ? v : 1
}

export function setZoom(v) {
  try {
    localStorage.setItem(ZOOM_KEY, String(v))
  } catch {
    // ignore
  }
  desktop.setZoom(v)
}

function onKeyDown(e) {
  if (e.defaultPrevented) return
  const ui = useUi()
  const ctrl = e.ctrlKey || e.metaKey
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key
  const typing = isTyping(e.target)

  // The first-run welcome covers the app; nothing should act on it unseen.
  if (useOnboarding().show.value && key !== 'F11') return

  // --- Global, even while typing ---
  if (ctrl && !e.altKey && (key === 'k' || (key === 'f' && !e.shiftKey))) {
    e.preventDefault()
    ui.focusSearch()
    return
  }
  if (ctrl && key === ',') {
    e.preventDefault()
    router.push({ name: 'Settings' })
    return
  }
  if (e.altKey && !ctrl && key === 'ArrowLeft') {
    e.preventDefault()
    router.back()
    return
  }
  if (e.altKey && !ctrl && key === 'ArrowRight') {
    e.preventDefault()
    router.forward()
    return
  }
  if (key === 'F11' && desktop.isDesktop) {
    e.preventDefault()
    desktop.toggleFullscreen()
    return
  }
  if (desktop.isDesktop && (key === 'F5' || (ctrl && key === 'r'))) {
    // Refresh the current view's data: never reload the whole app.
    e.preventDefault()
    window.dispatchEvent(new CustomEvent('dannify:refresh'))
    return
  }

  // --- App shortcuts. Modifier combos (and F-keys) work while typing too;
  // an input that wants a key for itself calls preventDefault first. ---
  if (ctrl && !e.shiftKey && key === 'b') {
    e.preventDefault()
    ui.toggleSidebar()
  } else if (ctrl && !e.shiftKey && key === 'l') {
    e.preventDefault()
    ui.setPanel('lyrics')
  } else if (ctrl && !e.shiftKey && key === 'q') {
    e.preventDefault()
    ui.setPanel('queue')
  } else if (ctrl && !e.shiftKey && key === 'e') {
    e.preventDefault()
    if (router.currentRoute.value.name === 'NowPlaying') router.back()
    else router.push({ name: 'NowPlaying' })
  } else if (ctrl && e.shiftKey && key === 'm' && desktop.isDesktop) {
    e.preventDefault()
    desktop.setMini(!desktop.state.mini)
  } else if ((ctrl && key === '/') || key === 'F1') {
    e.preventDefault()
    ensureFullWindow().then(() => {
      ui.shortcutsOpen.value = true
    })
  } else if (key === 'Escape' && !typing) {
    if (desktop.state.fullscreen) {
      e.preventDefault()
      desktop.toggleFullscreen()
    } else if (router.currentRoute.value.name === 'NowPlaying') {
      e.preventDefault()
      router.back()
    } else if (ui.panel.value && ui.panelFloating.value) {
      e.preventDefault()
      ui.closePanel()
    } else if (ui.drawerOpen.value) {
      e.preventDefault()
      ui.drawerOpen.value = false
    }
  }
}

// Right-click: our own menus everywhere. Text fields get a native-style
// Cut/Copy/Paste menu; nothing ever shows the browser's page menu.
function onContextMenu(e) {
  if (e.defaultPrevented) return
  const field = e.target.closest && e.target.closest('input, textarea, [contenteditable="true"]')
  if (field) {
    if (!desktop.isDesktop) return // browsers already offer a proper text menu
    openTextFieldMenu(e, field)
    return
  }
  const selection = window.getSelection ? String(window.getSelection() || '') : ''
  if (selection.trim()) {
    openContextMenu(e, [
      { label: t('actions.copy'), icon: 'ph:copy', shortcut: 'Ctrl+C', action: () => copyText(selection) },
    ])
    return
  }
  e.preventDefault()
}

function openTextFieldMenu(e, field) {
  const isInput = field.tagName === 'INPUT' || field.tagName === 'TEXTAREA'
  const start = isInput ? field.selectionStart : null
  const end = isInput ? field.selectionEnd : null
  const hasSelection = isInput ? start !== end : String(window.getSelection() || '').length > 0
  const readOnly = field.readOnly || field.disabled
  const restore = () => {
    field.focus({ preventScroll: true })
    if (isInput && start !== null) field.setSelectionRange(start, end)
  }
  const exec = (cmd) => () => {
    restore()
    document.execCommand(cmd)
  }
  openContextMenu(e, [
    { label: t('actions.undo'), icon: 'ph:arrow-counter-clockwise', shortcut: 'Ctrl+Z', disabled: readOnly, action: exec('undo') },
    { divider: true },
    { label: t('actions.cut'), icon: 'ph:scissors', shortcut: 'Ctrl+X', disabled: !hasSelection || readOnly, action: exec('cut') },
    { label: t('actions.copy'), icon: 'ph:copy', shortcut: 'Ctrl+C', disabled: !hasSelection, action: exec('copy') },
    {
      label: t('actions.paste'),
      icon: 'ph:clipboard-text',
      shortcut: 'Ctrl+V',
      disabled: readOnly,
      action: async () => {
        const text = await readText()
        restore()
        if (text) document.execCommand('insertText', false, text)
      },
    },
    { divider: true },
    {
      label: t('actions.selectAll'),
      icon: 'ph:selection-all',
      shortcut: 'Ctrl+A',
      action: () => {
        field.focus({ preventScroll: true })
        if (isInput) field.select()
        else document.execCommand('selectAll')
      },
    },
  ])
}

let installed = false
export function installShortcuts() {
  if (installed) return
  installed = true
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('contextmenu', onContextMenu)
  // Files dropped from Explorer would otherwise navigate the webview away.
  window.addEventListener('dragover', (e) => e.preventDefault())
  window.addEventListener('drop', (e) => e.preventDefault())
  if (desktop.isDesktop) {
    const z = currentZoom()
    if (z !== 1) desktop.whenReady().then(() => desktop.setZoom(z))
  }
}
