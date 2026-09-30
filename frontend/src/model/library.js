import { ref } from 'vue'
import API from '/src/model/api'

// Shared cache of the on-disk library (/api/library + /api/artists) for the
// sidebar, Home and Library views. Refreshes itself (debounced) whenever the
// server reports a change or the user deletes something.

const tracks = ref([])
const artists = ref([])
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
  inflight = Promise.all([API.getLibrary(), API.getArtists()])
    .then(([lib, art]) => {
      tracks.value = (lib.data && lib.data.tracks) || []
      artists.value = Array.isArray(art.data) ? art.data : []
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

export function useLibrary() {
  return { tracks, artists, loaded, loading, error, refresh, ensureLoaded }
}
