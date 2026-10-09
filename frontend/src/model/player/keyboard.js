import { mediaCommand } from '/src/model/player/mediaSession'
import { cycleRepeat, toggleShuffle } from '/src/model/player/order'
import { currentTime, noAutoAdvance, playlist, volume } from '/src/model/player/state'
import { next, prev, seek, setVolume, toggle, toggleMute } from '/src/model/player/transport'

// --- Global keyboard shortcuts (installed once) ---
let keyboardInstalled = false
function isTypingTarget(el) {
  if (!el) return false
  const tag = el.tagName
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    el.isContentEditable
  )
}

// Space is how a keyboard presses whatever has focus: a button, a link, a
// checkbox, a switch. Taking it for play/pause whenever there was a queue
// meant none of those could be pressed from the keyboard.
const SPACE_TAGS = new Set(['BUTTON', 'A', 'SUMMARY', 'AUDIO', 'VIDEO'])
const SPACE_ROLES = new Set([
  'button',
  'link',
  'checkbox',
  'switch',
  'radio',
  'tab',
  'option',
  'menuitem',
  'menuitemcheckbox',
  'menuitemradio',
  'slider',
  'spinbutton',
  'combobox',
  'textbox',
  'searchbox',
  'treeitem',
])
function ownsSpace(el) {
  if (!el) return false
  if (isTypingTarget(el) || SPACE_TAGS.has(el.tagName)) return true
  const role = typeof el.getAttribute === 'function' ? el.getAttribute('role') : null
  return !!role && SPACE_ROLES.has(role.trim().split(/\s+/)[0].toLowerCase())
}

export function installKeyboardShortcuts() {
  if (keyboardInstalled || typeof window === 'undefined') return
  keyboardInstalled = true
  window.addEventListener('keydown', (e) => {
    // A focused widget (track list, menu, dialog, slider) already handled it.
    if (e.defaultPrevented) return
    // Never hijack typing in inputs/textareas or with modifier combos.
    if (isTypingTarget(e.target) || e.metaKey || e.ctrlKey || e.altKey) return
    // While the lyrics-sync editor is open the global Space/Arrow
    // shortcuts compete with the editor's own keyboard contract
    // (Space = stamp, ↑/↓ = move active line). The noAutoAdvance flag
    // is a perfectly good proxy for "editor is open" so we use that
    // here to defer to the editor.
    if (noAutoAdvance.value) return
    if (playlist.value.length === 0 && e.code !== 'Space') return

    switch (e.code) {
      case 'Space':
        if (playlist.value.length === 0 || ownsSpace(e.target)) return
        e.preventDefault()
        toggle()
        break
      case 'ArrowRight':
        // Shift = next track, plain = seek +10s
        if (e.shiftKey) {
          e.preventDefault()
          next()
        } else {
          e.preventDefault()
          seek((currentTime.value || 0) + 10)
        }
        break
      case 'ArrowLeft':
        if (e.shiftKey) {
          e.preventDefault()
          prev()
        } else {
          e.preventDefault()
          seek((currentTime.value || 0) - 10)
        }
        break
      case 'MediaTrackNext':
        e.preventDefault()
        mediaCommand('next')
        break
      case 'MediaTrackPrevious':
        e.preventDefault()
        mediaCommand('prev')
        break
      case 'MediaPlayPause':
        e.preventDefault()
        mediaCommand('toggle')
        break
      case 'ArrowUp':
        e.preventDefault()
        setVolume(Math.min(1, volume.value + 0.05))
        break
      case 'ArrowDown':
        e.preventDefault()
        setVolume(Math.max(0, volume.value - 0.05))
        break
      case 'KeyM':
        e.preventDefault()
        toggleMute()
        break
      case 'KeyN':
        e.preventDefault()
        next()
        break
      case 'KeyP':
        e.preventDefault()
        prev()
        break
      case 'KeyS':
        e.preventDefault()
        toggleShuffle()
        break
      case 'KeyR':
        e.preventDefault()
        cycleRepeat()
        break
      default:
        break
    }
  })
}

