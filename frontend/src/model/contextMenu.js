import { ref } from 'vue'

// Custom right-click menus. Builders return arrays of items; falsy entries are
// dropped so callers can write `cond && {...}`.
//
// Item shape:
//   { label, icon?, shortcut?, action?, danger?, disabled?, checked? }
//   { divider: true }
//   { header: 'Section title' }

const menu = ref(null)
let seq = 0

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
  const target = event && (event.currentTarget || event.target)
  if (anchor && target && target.getBoundingClientRect) {
    const r = target.getBoundingClientRect()
    x = r.right
    y = r.bottom + 4
  } else if (event && typeof event.clientX === 'number' && (event.clientX || event.clientY)) {
    x = event.clientX
    y = event.clientY
  } else if (target && target.getBoundingClientRect) {
    // Keyboard invocation (Menu key / Shift+F10): open beside the element.
    const r = target.getBoundingClientRect()
    x = r.left + 24
    y = r.top + r.height / 2
  }
  menu.value = { id: ++seq, x, y, items: list, alignRight: anchor }
}

export function closeContextMenu() {
  menu.value = null
}

export function useContextMenu() {
  return { menu, openContextMenu, closeContextMenu }
}
