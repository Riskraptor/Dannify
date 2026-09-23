import API from '/src/model/api'
import { useLibraryIndex } from '/src/model/libraryIndex'

// Resolving a YouTube stream costs about nine seconds: a couple of round
// trips plus solving the player's JavaScript challenge. None of that can be
// made fast, so the job here is to have it already done by the time anyone
// clicks. Hovering a row for a third of a second is a strong enough signal
// to start, and the backend caches the result for hours.

const YT_ID = /^[A-Za-z0-9_-]{11}$/
const requested = new Set()
const MAX_IN_FLIGHT = 3
let inFlight = 0
const queue = []
let hoverTimer = null

function videoIdOf(song) {
  if (!song) return ''
  for (const key of ['video_id', 'song_id']) {
    const value = song[key]
    if (typeof value === 'string' && YT_ID.test(value)) return value
  }
  return ''
}

function pump() {
  while (inFlight < MAX_IN_FLIGHT && queue.length) {
    const id = queue.shift()
    inFlight += 1
    API.prefetchStream(id)
      .catch(() => requested.delete(id)) // let a failure be retried later
      .finally(() => {
        inFlight -= 1
        pump()
      })
  }
}

/** Start resolving this song's stream now, at most once per session. */
export function warmStream(song) {
  const id = videoIdOf(song)
  if (!id || requested.has(id)) return
  try {
    // Already on disk: it will play from the local file, nothing to warm.
    if (useLibraryIndex().localFileFor(song)) return
  } catch {
    /* index not ready yet; warming anyway is harmless */
  }
  requested.add(id)
  queue.push(id)
  pump()
}

export function warmAll(songs, limit = 4) {
  let n = 0
  for (const song of songs || []) {
    if (n >= limit) return
    const before = requested.size
    warmStream(song)
    if (requested.size !== before) n += 1
  }
}

/** Hovering a row. Waits a beat so sweeping the mouse costs nothing. */
export function warmOnHover(song) {
  clearTimeout(hoverTimer)
  const id = videoIdOf(song)
  if (!id || requested.has(id)) return
  hoverTimer = setTimeout(() => warmStream(song), 320)
}

export function cancelHoverWarm() {
  clearTimeout(hoverTimer)
}
