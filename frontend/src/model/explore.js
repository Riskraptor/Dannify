import { ref } from 'vue'
import API from '/src/model/api'
import router from '/src/router'
import { usePlayer } from '/src/model/player'
import { useDownloadManager } from '/src/model/download'

// --- Persistent search/explore state (module-level → survives navigation) ---
// So pressing the Search icon (or Back) restores your last query, results,
// active tab and scroll position instead of clearing everything.
const searchState = ref({
  query: '',
  data: { songs: [], artists: [], albums: [], playlists: [] },
  activeTab: 'all',
  scrollY: 0,
  loaded: false,
})

export function useSearchState() {
  return searchState
}

// Shared helpers for the online explorer: navigation + play/download actions
// that work on the YouTube-Music song dicts the explorer endpoints return.
export function useExplore() {
  const player = usePlayer()
  const dm = useDownloadManager()

  function openArtist(id) {
    if (id) router.push({ name: 'ExploreArtist', params: { id } })
  }
  function openAlbum(id) {
    if (id) router.push({ name: 'ExploreAlbum', params: { id } })
  }
  function openPlaylist(id) {
    if (id) router.push({ name: 'ExplorePlaylist', params: { id } })
  }
  function openSearch(q) {
    if (q && q.trim()) router.push({ name: 'Search', params: { query: q } })
  }

  // Stream a list of songs starting at index. By default we DO NOT navigate
  // away: playback starts in the background and the user stays on the page
  // they were exploring (Spotify behaviour). Pass navigate=true to jump to
  // the full player.
  function streamList(songs, index = 0, navigate = false) {
    if (!songs || !songs.length) return
    player.playStreamSongs(songs, index)
    if (navigate) router.push({ name: 'Player' })
  }

  function streamOne(song, navigate = false) {
    streamList([song], 0, navigate)
  }

  function downloadSong(song) {
    return dm.downloadSongs ? dm.downloadSongs([song]) : dm.queue(song)
  }

  function downloadAll(songs, playlistUrl = '') {
    if (!songs || !songs.length) return
    if (dm.downloadSongs) return dm.downloadSongs(songs, playlistUrl)
    songs.forEach((s) => dm.queue(s))
  }

  return {
    openArtist,
    openAlbum,
    openPlaylist,
    openSearch,
    streamList,
    streamOne,
    downloadSong,
    downloadAll,
  }
}
