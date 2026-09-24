import { ref, shallowRef } from 'vue'
import API from '/src/model/api'

// The YouTube Music home feed.
//
// The feed is a two second round trip to YouTube, and Home is the first thing
// the app shows. Waiting on it means the first screen is a grid of grey
// rectangles, which reads as a broken app rather than a loading one. So the
// last feed we saw is kept on disk and painted immediately on the next
// launch, while a fresh copy is fetched behind it. The user sees real music
// straight away and the shelves quietly update underneath.

const sections = shallowRef([]) // [{ title, items: [card] }]. Never mutated in place
const signedIn = ref(false)
const loading = ref(false)
const loaded = ref(false)
const error = ref('')
let inflight = null

// How long a loaded feed is considered current. Past this, revisiting Home
// shows what we have instantly and quietly fetches a fresh copy, so the page
// is never both stale and unchanging.
const SOFT_AGE_MS = 60_000
let fetchedAt = 0

// How long a feed restored from disk is still worth showing while the fresh
// one loads. A day-old shelf of songs is a better first frame than no first
// frame; past that the titles start to feel wrong ("Good evening" over
// yesterday's picks) and an empty page is more honest.
const STORED_TTL_MS = 24 * 60 * 60 * 1000
const STORE_KEY = 'dannify.home.v1'
// A feed this size is already more than one screen. The cap keeps a runaway
// response from filling the browser's storage quota.
const MAX_STORED_SECTIONS = 8
const MAX_STORED_ITEMS = 14

function readStored() {
  try {
    const raw = localStorage.getItem(STORE_KEY)
    if (!raw) return null
    const blob = JSON.parse(raw)
    if (!blob || !Array.isArray(blob.sections) || !blob.sections.length) return null
    if (Date.now() - (blob.ts || 0) > STORED_TTL_MS) return null
    return blob
  } catch {
    return null // private mode, blocked storage, corrupt entry: all the same
  }
}

function writeStored(list, isSignedIn) {
  try {
    const trimmed = list.slice(0, MAX_STORED_SECTIONS).map((section) => ({
      ...section,
      items: (section.items || []).slice(0, MAX_STORED_ITEMS),
    }))
    localStorage.setItem(
      STORE_KEY,
      JSON.stringify({ sections: trimmed, signedIn: isSignedIn, ts: Date.now() }),
    )
  } catch {
    // Quota or blocked storage. The feed still works, it just will not be
    // warm next launch.
  }
}

function clearStored() {
  try {
    localStorage.removeItem(STORE_KEY)
  } catch {
    // Nothing to do: the TTL will age it out anyway.
  }
}

// Paint the last known feed before anything is asked of the network.
const stored = readStored()
if (stored) {
  sections.value = stored.sections
  signedIn.value = !!stored.signedIn
  loaded.value = true
  // Deliberately left at 0 so the first load() call revalidates at once.
  fetchedAt = 0
}

async function load(force = false) {
  if (inflight) return inflight
  if (loaded.value && !force) {
    if (Date.now() - fetchedAt > SOFT_AGE_MS) load(true) // revalidate
    return Promise.resolve(sections.value)
  }
  // Only show the skeleton on a genuinely empty first load.
  loading.value = !loaded.value
  error.value = ''
  inflight = API.getHomeFeed()
    .then((res) => {
      const next = (res.data && res.data.sections) || []
      const isSignedIn = !!(res.data && res.data.signed_in)
      // An empty answer is usually YouTube being unreachable rather than a
      // genuinely empty feed. Keep what we are already showing.
      if (next.length || !sections.value.length) {
        sections.value = next
        if (next.length) writeStored(next, isSignedIn)
        else clearStored()
      }
      signedIn.value = isSignedIn
      loaded.value = true
      fetchedAt = Date.now()
      return sections.value
    })
    .catch((e) => {
      error.value = (e.response && e.response.data && e.response.data.detail) || 'offline'
      // Offline with a restored feed is not an error the user needs to see:
      // the shelves on screen are still playable.
      if (sections.value.length) error.value = ''
      // Say it is done either way, or the page sits on a greeting and
      // nothing else with no way to ask again.
      loaded.value = true
      return sections.value
    })
    .finally(() => {
      loading.value = false
      inflight = null
    })
  return inflight
}

// Signing in or out changes what the feed contains, so the stored copy from
// the other state must not survive it.
if (typeof window !== 'undefined') {
  window.addEventListener('dannify:account-changed', () => {
    clearStored()
    load(true)
  })
}

export function useHomeFeed() {
  return { sections, signedIn, loading, loaded, error, load }
}
