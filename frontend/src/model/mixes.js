import { computed, shallowRef, watch } from 'vue'
import API from '/src/model/api'
import { useLibrary } from '/src/model/library'
import { listensEpoch } from '/src/model/listens'
import { entryRow } from '/src/model/playlists'
import { localRow } from '/src/model/tracks'
import { MIXES, MIX_ORDER, mixCovers, recentlyAdded } from '/src/model/mixRules'

export { MIXES, MIX_ORDER, mixCovers, recentlyAdded }

// Mixes: playlists that make themselves. Three come from what has been
// listened to (Backend listens.mixes); Recently Added is the library's
// newest songs. Each is played, shuffled and saved like any playlist, and
// keeps up with the listening on its own.

// Fewer songs than this and a mix is not offered.
const MIN = 4

const fromListening = shallowRef({})
let loadedFor = -1
let loading = null

async function load(force = false) {
  if (!force && loadedFor === listensEpoch.value) return
  if (loading) return loading
  const epoch = listensEpoch.value
  loading = API.getMixes()
    .then((res) => {
      const found = {}
      for (const mix of (res && res.data && res.data.mixes) || []) {
        if (MIXES[mix.id] && Array.isArray(mix.songs)) found[mix.id] = mix.songs
      }
      fromListening.value = found
      loadedFor = epoch
    })
    .catch(() => {
      // Offline or older app: the mixes made from the library still show.
    })
    .finally(() => {
      loading = null
    })
  return loading
}

if (typeof window !== 'undefined') watch(listensEpoch, () => load())

export function useMixes() {
  const lib = useLibrary()
  load()

  /** Every mix there is enough for, as `{ id, rows }`, in shelf order. */
  const mixes = computed(() => {
    // Made again when the library is read: a song saved since plays from disk.
    void lib.tracks.value
    const out = []
    for (const id of MIX_ORDER) {
      let rows
      if (id === 'recent') rows = recentlyAdded(lib.tracks.value).map(localRow)
      else rows = (fromListening.value[id] || []).map(entryRow)
      if (rows.length >= MIN) out.push({ id, rows })
    }
    return out
  })

  function mixOf(id) {
    return computed(() => mixes.value.find((m) => m.id === id) || null)
  }

  return { mixes, mixOf, refresh: () => load(true) }
}
