import { computed } from 'vue'
import {
  REPEAT_KEY,
  SHUFFLE_KEY,
  currentIndex,
  playlist,
  repeatMode,
  shuffle,
  shuffleOrder,
} from '/src/model/player/state'

// The play order: what comes next and what came before, in order or
// shuffled, and what repeat does at either end. The shuffled order is kept
// in step with every queue edit rather than dealt again.

function shuffled(indices) {
  for (let i = indices.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[indices[i], indices[j]] = [indices[j], indices[i]]
  }
  return indices
}

// A fresh shuffle, for a new queue or shuffle just switched on: *first* (the
// track playing, or about to) leads and everything else follows in random
// order. It used to be shuffled in with the rest, which only worked because
// the order never ended: whatever landed ahead of it played on the way round.
// Now that repeat off ends the order, that would never have played at all.
export function buildShuffleOrder(first = currentIndex.value) {
  const n = playlist.value.length
  const rest = []
  for (let i = 0; i < n; i++) if (i !== first) rest.push(i)
  shuffled(rest)
  shuffleOrder.value = first >= 0 && first < n ? [first, ...rest] : rest
}

// Every queue edit keeps the order in step itself. This only catches a
// queue that changed some other way, and it has to run before the edit.
export function ensureShuffleOrder() {
  if (shuffleOrder.value.length !== playlist.value.length) buildShuffleOrder()
}

// Where the playing track sits in the shuffled order; -1 with nothing
// loaded, which leaves the whole order still to come.
export function shufflePosition() {
  return currentIndex.value >= 0 ? shuffleOrder.value.indexOf(currentIndex.value) : -1
}

// Queue edits under shuffle. Each of these used to throw the order away and
// deal a new one: "Play next" landed anywhere, a track that had already
// played could come round again, and Previous went somewhere random. They now
// change only what the edit touches.
//
// *count* tracks were inserted into the queue at *at*: shift the indices at
// and after it, and put the new ones straight after the playing track
// ("Play next") or at the end of the order ("Add to queue"), or, for a batch
// the listener did not pick one by one (a radio station), at the end in
// random order. Returns the new indices in the order they will play.
export function addToShuffleOrder(at, count, { next = false, mix = false } = {}) {
  ensureShuffleOrder()
  const added = []
  for (let k = 0; k < count; k++) added.push(at + k)
  if (mix) shuffled(added)
  const order = shuffleOrder.value.map((i) => (i >= at ? i + count : i))
  const where = next ? shufflePosition() + 1 : order.length
  // Not splice(where, 0, ...added): that passes every index as an argument
  // and runs out of stack when a whole big library is queued.
  shuffleOrder.value = [...order.slice(0, where), ...added, ...order.slice(where)]
  return added
}

// The track at *index* is leaving the queue.
export function dropFromShuffleOrder(index) {
  ensureShuffleOrder()
  shuffleOrder.value = shuffleOrder.value
    .filter((i) => i !== index)
    .map((i) => (i > index ? i - 1 : i))
}

// Under shuffle the shuffled order ends the way the list does. It used to
// wrap round whatever the repeat setting, so with repeat off a shuffled queue
// never ended, and autoplay radio never got its turn.
export function nextIndex() {
  if (playlist.value.length === 0) return -1
  if (shuffle.value) {
    ensureShuffleOrder()
    const order = shuffleOrder.value
    const nextPos = shufflePosition() + 1
    if (nextPos >= order.length) {
      return repeatMode.value === 'all' ? order[0] : -1
    }
    return order[nextPos]
  }
  const i = currentIndex.value + 1
  if (i >= playlist.value.length) {
    return repeatMode.value === 'all' ? 0 : -1
  }
  return i
}

// Whether anything follows the current track in the play order, not counting
// a wrap-around. A track that will not play moves on only while this holds;
// it used to ask whether a row followed it, which under shuffle is a
// different question.
export function hasNextInOrder() {
  if (shuffle.value) {
    ensureShuffleOrder()
    return shufflePosition() < shuffleOrder.value.length - 1
  }
  return currentIndex.value < playlist.value.length - 1
}

export function prevIndex() {
  if (playlist.value.length === 0) return -1
  if (shuffle.value) {
    ensureShuffleOrder()
    const order = shuffleOrder.value
    const prevPos = shufflePosition() - 1
    if (prevPos < 0) {
      return repeatMode.value === 'all' ? order[order.length - 1] : order[0]
    }
    return order[prevPos]
  }
  const i = currentIndex.value - 1
  if (i < 0) {
    return repeatMode.value === 'all' ? playlist.value.length - 1 : 0
  }
  return i
}

export function setRepeat(mode) {
  if (!['off', 'all', 'one'].includes(mode)) return
  repeatMode.value = mode
  try {
    localStorage.setItem(REPEAT_KEY, mode)
  } catch {
    // The choice just will not survive a restart.
  }
}

export function cycleRepeat() {
  const order = ['off', 'all', 'one']
  const i = order.indexOf(repeatMode.value)
  setRepeat(order[(i + 1) % order.length])
}

export function setShuffle(v) {
  const was = shuffle.value
  shuffle.value = !!v
  // Only switching it on deals a new order; saying "on" again keeps the one
  // in play.
  if (shuffle.value && !was) buildShuffleOrder()
  try {
    localStorage.setItem(SHUFFLE_KEY, shuffle.value ? '1' : '0')
  } catch {
    // As above.
  }
}

export function toggleShuffle() {
  setShuffle(!shuffle.value)
}

// The queue indices still to play after the current track, in the order they
// will play: the rest of the shuffled order under shuffle, the rows below
// otherwise. "Up next" used to list the rows below even with shuffle on, so
// the panel showed one thing and the player then played another.
export const upcoming = computed(() => {
  const list = playlist.value
  const cur = currentIndex.value
  if (shuffle.value) {
    const order = shuffleOrder.value
    // Out of step only until the next move rebuilds it; the rows are the
    // best guess until then.
    if (order.length === list.length) {
      return order.slice((cur >= 0 ? order.indexOf(cur) : -1) + 1)
    }
  }
  const out = []
  for (let i = Math.max(0, cur + 1); i < list.length; i++) out.push(i)
  return out
})
