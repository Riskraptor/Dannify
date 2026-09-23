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

// --- Artist, album and playlist pages -------------------------------------
//
// Opening an artist costs two sequential round trips to YouTube: the artist
// itself, then its songs, albums and singles (those three now run together,
// but they cannot start until the first one answers). About two seconds,
// and no amount of work on our side removes a round trip we do not control.
//
// So the same trick as streams: start it when the pointer settles on a card.
// The backend caches the result, and by the time the click lands the page is
// usually already sitting there.

const pages = new Set()
let pageTimer = null
const PAGE_MAX_IN_FLIGHT = 2
let pagesInFlight = 0
const pageQueue = []

const PAGE_FETCH = {
  artist: (id) => API.exploreArtist(id),
  album: (id) => API.exploreAlbum(id),
  playlist: (id) => API.explorePlaylist(id),
}

function pumpPages() {
  while (pagesInFlight < PAGE_MAX_IN_FLIGHT && pageQueue.length) {
    const { kind, id, key } = pageQueue.shift()
    const fetch = PAGE_FETCH[kind]
    if (!fetch) continue
    pagesInFlight += 1
    fetch(id)
      .catch(() => pages.delete(key)) // a failure should be retryable
      .finally(() => {
        pagesInFlight -= 1
        pumpPages()
      })
  }
}

/** Start loading a browse page now, at most once per session. */
export function warmPage(kind, id) {
  if (!id || typeof id !== 'string' || !PAGE_FETCH[kind]) return
  const key = kind + ':' + id
  if (pages.has(key)) return
  pages.add(key)
  pageQueue.push({ kind, id, key })
  pumpPages()
}

/** Hovering a card. Longer than the row delay: opening a page is a heavier
 *  request than warming a stream, and cards sit closer together. */
export function warmPageOnHover(kind, id) {
  clearTimeout(pageTimer)
  const key = kind + ':' + id
  if (!id || pages.has(key)) return
  pageTimer = setTimeout(() => warmPage(kind, id), 420)
}

export function cancelPageWarm() {
  clearTimeout(pageTimer)
}
