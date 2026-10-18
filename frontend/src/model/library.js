import { ref, shallowRef } from 'vue'
import API from '/src/model/api'

// Shared cache of the on-disk library (/api/library + /api/artists) for the
// sidebar, Home and Library views. Refreshes itself (debounced) whenever the
// server reports a change or the user deletes something.

// Shallow: the lists are only ever replaced whole, never edited in place, so
// there is nothing for Vue to watch inside them. Deep refs wrapped every song
// and artist in a proxy of its own, which is most of the memory a library of
// a hundred thousand took.
const tracks = shallowRef([])
const artists = shallowRef([])
// The albums there are songs from (see library._album_list), without their
// songs: those are in `tracks`, and an album's page asks for its own.
const albums = shallowRef([])
const loaded = ref(false)
const loading = ref(false)
const error = ref(false)
// Goes up every time the library is read again. A picture of a saved song
// that could not be shown (the song would not open) tries again when it
// changes: the usual reason is that the song has just been repaired.
export const libraryEpoch = ref(0)

let inflight = null
let again = null
function refresh() {
  // A change that lands while a read is on its way may not be in what that
  // read brings back. It used to be dropped: the finished download was
  // announced while the list was still being read from its half-made state,
  // and the sidebar kept that picture (no artwork, no album) until the app
  // was restarted. One more read goes out after this one instead.
  if (inflight) {
    if (!again) {
      again = inflight.then(() => {
        again = null
        return refresh()
      })
    }
    return again
  }
  loading.value = true
  inflight = Promise.all([
    API.getLibrary(),
    API.getArtists(),
    // Not worth failing the whole library over: without them there is no
    // Albums page, and every song still plays.
    API.getAlbums().catch(() => null),
  ])
    .then(([lib, art, alb]) => {
      tracks.value = (lib.data && lib.data.tracks) || []
      artists.value = Array.isArray(art.data) ? art.data : []
      if (alb) albums.value = Array.isArray(alb.data) ? alb.data : []
      loaded.value = true
      error.value = false
      libraryEpoch.value++
    })
    .catch(() => {
      error.value = true
      // Finished, badly, but finished. Leaving this false held the view on
      // its skeleton rows for ever: nothing reads the error, and every
      // retry path only asks whether it had loaded.
      loaded.value = true
    })
    .finally(() => {
      loading.value = false
      inflight = null
    })
  return inflight
}

function ensureLoaded() {
  if (!loaded.value && !inflight) refresh()
  return inflight || Promise.resolve()
}

let timer = null
function scheduleRefresh(delay = 1200) {
  clearTimeout(timer)
  timer = setTimeout(refresh, delay)
}

window.addEventListener('dannify:library-changed', (e) => {
  const removed = e.detail && e.detail.removed
  if (Array.isArray(removed) && removed.length) {
    // Optimistic: drop deleted files right away, then re-sync.
    const gone = new Set(removed)
    tracks.value = tracks.value.filter((tr) => !gone.has(tr.file))
  }
  scheduleRefresh(removed ? 400 : 1200)
})

// Coming back to the window is the moment the list is most likely to be
// wrong: the usual reason someone alt-tabbed away was to go and move or
// delete files. The backend watcher catches this too, but only while the app
// is running, and this costs one request.
let lastFocusCheck = 0
if (typeof window !== 'undefined') {
  window.addEventListener('focus', () => {
    if (!loaded.value) return
    const now = Date.now()
    if (now - lastFocusCheck < 3000) return // alt-tabbing back and forth
    lastFocusCheck = now
    refresh()
  })
}

/**
 * The library's album a song is on, or null: by the song's album and the
 * artist page it is on, the way the albums were made.
 */
export function albumOf(tr) {
  if (!tr || !tr.album) return null
  const name = foldName(tr.album)
  const who = foldName(tr.group || tr.artist)
  return albums.value.find((a) => foldName(a.name) === name && foldName(a.artist) === who) || null
}

// The way the server compares names (library.fold): case, accents and
// punctuation do not make two albums.
function foldName(text) {
  return String(text || '')
    .normalize('NFKD')
    .replace(/\p{M}+/gu, '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
}

/** An album's saved songs, in album order. */
export function albumTracks(album) {
  if (!album) return []
  const name = foldName(album.name)
  const who = foldName(album.artist)
  return tracks.value
    .filter((tr) => foldName(tr.album) === name && foldName(tr.group || tr.artist) === who)
    .sort(
      (a, b) =>
        (a.track_number || 999) - (b.track_number || 999) ||
        String(a.title || '').localeCompare(String(b.title || ''))
    )
}

/** Where an album's page is: by its artist and its name. */
export function albumRoute(album) {
  return { name: 'Album', params: { artist: album.artist, name: album.name } }
}

export function useLibrary() {
  return { tracks, artists, albums, loaded, loading, error, refresh, ensureLoaded }
}
