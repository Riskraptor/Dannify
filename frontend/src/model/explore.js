import { ref } from 'vue'
import API from '/src/model/api'
import router from '/src/router'

// --- Persistent search/explore state (module-level → survives navigation) ---
// So pressing the Search icon (or Back) restores your last query, results,
// active tab and scroll position instead of clearing everything.
const searchState = ref({
  query: '',
  data: { songs: [], artists: [], albums: [], playlists: [] },
  activeTab: 'all',
  // Set while a search is in flight. The title-bar spinner reads this; it
  // used to read a `loading` key that nothing ever wrote.
  searching: false,
  loaded: false,
})

export function useSearchState() {
  return searchState
}

// Shared helpers for the online explorer: navigation + play/download actions
// that work on the YouTube-Music song dicts the explorer endpoints return.
export function useExplore() {
  function openArtist(id) {
    if (id) router.push({ name: 'ExploreArtist', params: { id } })
  }
  function openAlbum(id) {
    if (id) router.push({ name: 'ExploreAlbum', params: { id } })
  }
  function openPlaylist(id) {
    if (id) router.push({ name: 'ExplorePlaylist', params: { id } })
  }
  // Five more helpers used to live here: streamList, streamOne, downloadSong,
  // downloadAll and openSearch. Nothing called any of them, and streamList
  // pushed to a route named Player that the router has never defined, so it
  // would have thrown had anything tried.
  return { openArtist, openAlbum, openPlaylist }
}
