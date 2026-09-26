// Keyboard focus for anything that sits on top of the app: dialogs, the
// lyrics editor, menus.
//
// Two rules. Tab never leaves what is on top: it used to walk out into the
// sidebar and the title bar hidden behind the scrim. And closing it hands
// focus back to whatever had it before, so arrow keys keep working in the
// list you were in instead of focus being dropped on the page.

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'textarea:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function visible(el) {
  return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
}

/** Call from a keydown handler: keeps Tab and Shift+Tab inside `container`. */
export function trapTab(e, container) {
  if (e.key !== 'Tab' || !container) return
  const items = [...container.querySelectorAll(FOCUSABLE)].filter(visible)
  if (!items.length) {
    e.preventDefault()
    container.focus?.()
    return
  }
  const first = items[0]
  const last = items[items.length - 1]
  const active = document.activeElement
  if (!container.contains(active)) {
    e.preventDefault()
    ;(e.shiftKey ? last : first).focus()
  } else if (e.shiftKey && (active === first || active === container)) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && active === last) {
    e.preventDefault()
    first.focus()
  }
}

/** Note what has focus now; the returned function gives it back. */
export function rememberFocus() {
  const el = typeof document !== 'undefined' ? document.activeElement : null
  return () => {
    if (!el || el === document.body || typeof el.focus !== 'function') return
    if (!document.contains(el)) return
    try {
      el.focus({ preventScroll: true })
    } catch {
      // It went away between opening and closing: nothing to go back to.
    }
  }
}
