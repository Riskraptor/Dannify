import { ref } from 'vue'

// A walk round Dannify: a spotlight on one thing at a time, an arrow to it,
// a few words, and now and then a "try it" that waits for the person to do
// it. The whole tour once, after the first-run setup; a short one of what is
// new after a big update; and either again from Settings, General or the
// command palette. The tour itself (components/tour/) is fetched only when it
// starts.

const DONE_KEY = 'dn.tourDone'
const NEW_KEY = 'dn.tourNewSeen'

/** The tour showing: { name: 'welcome' | 'new' }, or null. */
export const tour = ref(null)

function read(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function write(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // shown again next time, which is harmless
  }
}

export function startTour(name = 'welcome') {
  tour.value = { name, at: Date.now() }
}

/** Finished or put aside: either way, not offered again by itself. */
export function endTour() {
  const name = tour.value && tour.value.name
  tour.value = null
  if (name === 'welcome') write(DONE_KEY, '1')
  if (name === 'new') write(NEW_KEY, __APP_VERSION__)
}

/** After the first-run setup: the whole tour, a moment later, once. */
export function tourAfterSetup() {
  if (read(DONE_KEY)) return
  setTimeout(() => {
    if (!tour.value) startTour('welcome')
  }, 1200)
}

/** Whether this version's "what is new" tour has been seen. */
export function newTourSeen() {
  return read(NEW_KEY) === __APP_VERSION__
}
