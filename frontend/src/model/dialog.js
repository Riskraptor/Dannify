import { ref } from 'vue'

// In-app modal dialogs. Replaces window.confirm()/alert(), which in the
// desktop shell pop a browser-style "127.0.0.1 says…" box.

const queue = ref([])

function open(kind, opts) {
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

export function settleDialog(value) {
  const [current, ...rest] = queue.value
  queue.value = rest
  if (current) current.resolve(value)
}

export function useDialogs() {
  return { queue, settleDialog }
}
