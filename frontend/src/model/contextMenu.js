import { ref } from 'vue'
import { rememberFocus } from '/src/model/focusTrap'

// Custom right-click menus. Builders return arrays of items; falsy entries are
// dropped so callers can write `cond && {...}`.
//
// Item shape:
//   { label, icon?, shortcut?, action?, danger?, disabled?, checked? }
//   { divider: true }
//   { header: 'Section title' }

const menu = ref(null)
let seq = 0
let giveBack = null
// Where the last menu opened. A menu item that leads to a second menu
// ("Add to playlist") opens it in the same place.
let lastPoint = { x: 0, y: 0, alignRight: false }

function normalize(items) {
  const out = []
  for (const it of items || []) {
    if (!it) continue
    if (it.divider) {
      // No leading / doubled dividers.
      if (out.length && !out[out.length - 1].divider) out.push({ divider: true })
      continue
    }
    out.push(it)
  }
  while (out.length && out[out.length - 1].divider) out.pop()
  return out
}

/**
 * Open a menu at the pointer (mouse event) or under an anchor element
 * (e.g. a "⋯" button: pass the click event and set `anchor: true`).
 */
export function openContextMenu(event, items, { anchor = false } = {}) {
  if (event) {
    event.preventDefault?.()
    event.stopPropagation?.()
  }
  const list = normalize(items)
  if (!list.length) return
  let x = 0
  let y = 0
  // Where an anchored menu goes when there is no room under its button: above
  // the button, not over it. Flipping by its own height from the bottom edge
  // put the "⋯" menu on the play bar right on top of the button that opened it.
  let above = null
  const target = event && (event.currentTarget || event.target)
  if (anchor && target && target.getBoundingClientRect) {
    const r = target.getBoundingClientRect()
    x = r.right
    y = r.bottom + 4
    above = r.top - 4
  } else if (event && typeof event.clientX === 'number' && (event.clientX || event.clientY)) {
    x = event.clientX
    y = event.clientY
  } else if (target && target.getBoundingClientRect) {
    // Keyboard invocation (Menu key / Shift+F10): open beside the element.
    const r = target.getBoundingClientRect()
    x = r.left + 24
    y = r.top + r.height / 2
  }
  if (!menu.value) giveBack = rememberFocus()
  lastPoint = { x, y, alignRight: anchor, above }
  menu.value = { id: ++seq, x, y, items: list, alignRight: anchor, above }
}

export function lastMenuPoint() {
  return { ...lastPoint }
}

/** Open a menu at a point: where an earlier one was (see lastMenuPoint). */
export function openMenuAt(point, items) {
  const list = normalize(items)
  if (!list.length) return
  const p = point || lastPoint
  if (!menu.value) giveBack = rememberFocus()
  const above = typeof p.above === 'number' ? p.above : null
  lastPoint = { x: p.x, y: p.y, alignRight: !!p.alignRight, above }
  menu.value = { id: ++seq, x: p.x, y: p.y, items: list, alignRight: !!p.alignRight, above }
}

export function closeContextMenu() {
  if (!menu.value) return
  menu.value = null
  const back = giveBack
  giveBack = null
  // Only if nothing else has taken focus meanwhile (an action that opens
  // a dialog focuses its own button, and that must win).
  const now = document.activeElement
  if (back && (!now || now === document.body || now.closest?.('.cm'))) back()
}

export function useContextMenu() {
  return { menu, openContextMenu, closeContextMenu }
}
