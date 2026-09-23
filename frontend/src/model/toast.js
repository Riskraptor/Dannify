import { ref } from 'vue'

// Lightweight, app-wide notifications ("Added to queue", "Download
// finished", …). Rendered by components/ui/ToastHost.vue above the player bar.

const toasts = ref([])
let seq = 0
const MAX_VISIBLE = 3

/**
 * Show a toast.
 * @param {string} message
 * @param {{icon?: string, tone?: 'default'|'success'|'error', timeout?: number,
 *          action?: {label: string, run: Function}}} [opts]
 */
export function toast(message, opts = {}) {
  const id = ++seq
  const item = {
    id,
    message,
    icon: opts.icon || null,
    tone: opts.tone || 'default',
    action: opts.action || null,
    timeout: opts.timeout ?? (opts.action ? 5000 : 3200),
  }
  toasts.value = [...toasts.value, item].slice(-MAX_VISIBLE)
  if (item.timeout > 0) setTimeout(() => dismissToast(id), item.timeout)
  return id
}

export function dismissToast(id) {
  toasts.value = toasts.value.filter((t) => t.id !== id)
}

export function useToasts() {
  return { toasts, toast, dismissToast }
}
