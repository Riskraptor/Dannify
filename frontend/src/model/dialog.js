import { ref } from 'vue'
import { rememberFocus } from '/src/model/focusTrap'

// In-app modal dialogs. Replaces window.confirm()/alert(), which in the
// desktop shell pop a browser-style "127.0.0.1 says…" box.

const queue = ref([])
let giveBack = null

function open(kind, opts) {
  if (!queue.value.length) giveBack = rememberFocus()
  return new Promise((resolve) => {
    queue.value = [
      ...queue.value,
      {
        kind,
        title: opts.title || '',
        message: opts.message || '',
        detail: opts.detail || '',
        confirmText: opts.confirmText || '',
        cancelText: opts.cancelText || '',
        danger: !!opts.danger,
        icon: opts.icon || null,
        label: opts.label || '',
        value: opts.value || '',
        maxLength: opts.maxLength || 120,
        resolve,
      },
    ]
  })
}

/** Resolve true when the user confirms, false otherwise. */
export function confirmDialog(opts = {}) {
  return open('confirm', opts)
}

export function alertDialog(opts = {}) {
  return open('alert', opts)
}

/**
 * Ask for a line of text (a playlist's name). Resolves to what was typed,
 * trimmed, or null when cancelled. An empty answer counts as cancelled.
 */
export async function promptDialog(opts = {}) {
  const value = await open('prompt', opts)
  if (typeof value !== 'string') return null
  const text = value.trim()
  return text || null
}

export function settleDialog(value) {
  const [current, ...rest] = queue.value
  queue.value = rest
  if (current) current.resolve(value)
  if (!rest.length && giveBack) {
    const back = giveBack
    giveBack = null
    // After the dialog has gone, so its own focus handling is finished.
    setTimeout(() => {
      const now = document.activeElement
      if (!now || now === document.body) back()
    }, 0)
  }
}

export function useDialogs() {
  return { queue, settleDialog }
}
