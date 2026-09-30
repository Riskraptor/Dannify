import { ref } from 'vue'

// Lightweight, app-wide notifications ("Added to queue", "Download
// finished", …). Rendered by components/ui/ToastHost.vue above the player bar.
//
// A few rules keep them from turning into noise:
//
// * The same message twice does not stack. Pressing the heart on three songs
//   while signed out, or a setting that failed to save on every nudge of a
//   slider, used to pile identical toasts on top of each other until they
//   filled the stack. Now the one already showing is refreshed instead: its
//   countdown starts again and it counts how many times it has been said.
//   The newest call's button wins, because it is about the newest thing.
// * At most three at once. When another arrives, the oldest *plain* one makes
//   way. An error, or a toast with a button on it, is the one you might still
//   need, so it only goes when nothing else can. It used to be simply the
//   oldest, which meant "Downloads finished. 2 failed" with its View button
//   could be pushed off by "Added to queue".
// * Every toast can be closed, and none runs out while the pointer is on it:
//   the button you were reaching for no longer vanishes under the cursor.
// * Errors stay up longer than confirmations, and a long message stays long
//   enough to read. A timeout passed by the caller is always respected.

const toasts = ref([])
let seq = 0
const MAX_VISIBLE = 3

// Countdowns, by toast id: the timer handle, the time left, and when the
// current run started (so a pause knows how much is left).
const timers = new Map()
// What is holding the countdowns: toast id -> how many things (the pointer,
// keyboard focus) are on it. Kept per toast so that closing a toast also
// lets go of it. A toast removed from under the pointer never gets its
// mouseleave, and a plain counter would then have paused every toast after
// it for good.
const holds = new Map()

const BASE_TIMEOUT = 3200
const ACTION_TIMEOUT = 5000
const ERROR_TIMEOUT = 6000
const ERROR_ACTION_TIMEOUT = 8000
const MAX_DEFAULT_TIMEOUT = 10000

/** How long a toast stays when the caller did not say. */
export function defaultTimeout(message, tone = 'default', hasAction = false) {
  const base =
    tone === 'error'
      ? hasAction
        ? ERROR_ACTION_TIMEOUT
        : ERROR_TIMEOUT
      : hasAction
        ? ACTION_TIMEOUT
        : BASE_TIMEOUT
  // About the pace people read at, plus a second to notice it arrived.
  const reading = 1000 + String(message || '').length * 50
  return Math.min(MAX_DEFAULT_TIMEOUT, Math.max(base, reading))
}

function stopTimer(id) {
  const timer = timers.get(id)
  if (timer && timer.handle) clearTimeout(timer.handle)
  timers.delete(id)
}

function runTimer(id, timer) {
  timer.since = Date.now()
  timer.handle = setTimeout(() => dismissToast(id), timer.left)
}

function startTimer(item) {
  stopTimer(item.id)
  if (!(item.timeout > 0)) return // 0 means stay until closed
  const timer = { handle: null, left: item.timeout, since: 0 }
  timers.set(item.id, timer)
  if (!holds.size) runTimer(item.id, timer)
}

function pauseAll() {
  const now = Date.now()
  for (const timer of timers.values()) {
    if (!timer.handle) continue
    clearTimeout(timer.handle)
    timer.handle = null
    timer.left = Math.max(0, timer.left - (now - timer.since))
  }
}

function resumeAll() {
  for (const [id, timer] of timers) {
    // Whatever was left, but never less than a moment: a toast should not
    // vanish the instant the pointer leaves it.
    if (!timer.handle) {
      timer.left = Math.max(timer.left, 1200)
      runTimer(id, timer)
    }
  }
}

// A toast that has gone cannot be holding anything any more.
function letGo(id) {
  if (holds.delete(id) && !holds.size) resumeAll()
}

// Worth keeping over a plain confirmation when the stack is full.
function important(item) {
  return item.tone === 'error' || !!item.action
}

function makeRoom(list) {
  while (list.length > MAX_VISIBLE) {
    // Never the newest: that is the one somebody just caused.
    const older = list.slice(0, -1)
    let index = older.findIndex((item) => !important(item))
    if (index === -1) index = 0
    const [gone] = list.splice(index, 1)
    stopTimer(gone.id)
    letGo(gone.id)
  }
  return list
}

/**
 * Show a toast.
 * @param {string} message
 * @param {{icon?: string, tone?: 'default'|'success'|'error', timeout?: number,
 *          action?: {label: string, run: Function}}} [opts]
 *   `timeout` is in milliseconds; 0 keeps the toast until it is closed.
 * @returns {number} the toast's id (the existing one's, when it was a repeat)
 */
export function toast(message, opts = {}) {
  const text = String(message ?? '')
  const tone = opts.tone || 'default'
  const action = opts.action || null
  const timeout = opts.timeout ?? defaultTimeout(text, tone, !!action)

  const same = toasts.value.find((item) => item.message === text && item.tone === tone)
  if (same) {
    const refreshed = {
      ...same,
      icon: opts.icon || same.icon,
      action: action || same.action,
      timeout,
      count: same.count + 1,
    }
    toasts.value = toasts.value.map((item) => (item.id === same.id ? refreshed : item))
    startTimer(refreshed)
    return same.id
  }

  const item = {
    id: ++seq,
    message: text,
    icon: opts.icon || null,
    tone,
    action,
    timeout,
    count: 1,
  }
  toasts.value = makeRoom([...toasts.value, item])
  startTimer(item)
  return item.id
}

export function dismissToast(id) {
  stopTimer(id)
  toasts.value = toasts.value.filter((item) => item.id !== id)
  letGo(id)
}

/**
 * Pause every countdown while toast `id` has the pointer or keyboard focus
 * on it, so the whole stack can be read and its buttons reached.
 */
export function holdToasts(id) {
  const wasHeld = holds.size > 0
  holds.set(id, (holds.get(id) || 0) + 1)
  if (!wasHeld) pauseAll()
}

/** Toast `id` let go: the countdowns carry on from where they stopped. */
export function releaseToasts(id) {
  const count = holds.get(id) || 0
  if (!count) return
  if (count > 1) {
    holds.set(id, count - 1)
    return
  }
  letGo(id)
}

export function useToasts() {
  return { toasts, toast, dismissToast, holdToasts, releaseToasts }
}
