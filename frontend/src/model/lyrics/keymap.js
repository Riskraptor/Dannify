// The sync editor's keyboard, as data: which command a key press means.
//
// Kept apart from the handler so the rules about what the editor may take
// (and what it must leave to a focused button, a slider or the system) are
// written down once and tested.

// Keys a focused slider needs for itself.
const SLIDER_KEYS = new Set(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown'])
// What activates a focused control. Enter on a button has to press that
// button: it used to add a line instead, so a keyboard user could not reach
// a single toolbar action.
const PRESSABLE = new Set(['BUTTON', 'A', 'SUMMARY', 'SELECT'])

/**
 * @param {{code: string, key?: string, ctrlKey?: boolean, metaKey?: boolean,
 *          altKey?: boolean, shiftKey?: boolean}} e a keydown event
 * @param {{tag?: string, role?: string}} [target] what has the focus
 * @returns {string|null} the command, or null to let the key through
 */
export function syncCommand(e, target = {}) {
  const tag = String(target.tag || '').toUpperCase()
  const role = String(target.role || '').toLowerCase()
  if (tag === 'INPUT' || tag === 'TEXTAREA') return null
  const mod = e.ctrlKey || e.metaKey
  if (e.altKey) return null
  // The editor's own undo history; every other shortcut with Ctrl (copy,
  // paste, the app's own) passes straight through.
  if (mod) {
    if (e.code === 'KeyZ') return e.shiftKey ? 'redo' : 'undo'
    if (e.code === 'KeyY') return 'redo'
    return null
  }
  if (role === 'slider' && SLIDER_KEYS.has(e.code)) return null

  switch (e.code) {
    case 'Space':
      return e.shiftKey ? 'stamp-stay' : 'stamp'
    case 'Enter':
    case 'NumpadEnter':
      return PRESSABLE.has(tag) ? null : 'insert'
    case 'ArrowDown':
    case 'KeyJ':
      return 'next'
    case 'ArrowUp':
    case 'KeyK':
      return 'prev'
    case 'Home':
      return 'first'
    case 'End':
      return 'last'
    case 'ArrowLeft':
      return 'nudge-back'
    case 'ArrowRight':
      return 'nudge-forward'
    case 'KeyZ':
      return 'clear-last'
    case 'KeyL':
      return 'loop'
    case 'KeyP':
      return 'play'
    case 'KeyE':
    case 'F2':
      return 'edit'
    case 'Comma':
      return 'slower'
    case 'Period':
      return 'faster'
    case 'Delete':
    case 'Backspace':
      return e.shiftKey ? 'delete' : null
    default:
      return null
  }
}
