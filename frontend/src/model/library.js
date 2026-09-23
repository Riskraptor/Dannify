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

let inflight = null
async function refresh() {
  if (inflight) return inflight
  loading.value = true
  inflight = Promise.all([API.getLibrary(), API.getArtists()])
    .then(([lib, art]) => {
      tracks.value = (lib.data && lib.data.tracks) || []
      artists.value = Array.isArray(art.data) ? art.data : []
      loaded.value = true
      error.value = false
    })
    .catch(() => {
      error.value = true
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
