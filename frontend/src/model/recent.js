import { ref } from 'vue'

// Local listening history + recent searches (persisted, per device). Powers
// the "Jump back in" shelf on Home and the recent list on the Search page.

const PLAYED_KEY = 'dn.recentPlayed'
const SEARCH_KEY = 'dn.recentSearches'
const MAX_PLAYED = 40
const MAX_SEARCHES = 12

function load(key) {
  try {
    const v = JSON.parse(localStorage.getItem(key) || '[]')
    return Array.isArray(v) ? v : []
  } catch {
    return []
  }
}

function save(key, list) {
  try {
    localStorage.setItem(key, JSON.stringify(list))
  } catch {
    // quota / blocked storage: history is best-effort
  }
}

const played = ref(load(PLAYED_KEY))
const searches = ref(load(SEARCH_KEY))

export function trackKey(t) {
  if (!t) return ''
  return t.file ? `f:${t.file}` : `s:${t.song_id || t.video_id || t.url || t.title}`
}

// Only keep what's needed to replay the track later (and nothing huge).
function slim(track) {
  const song = track._song
  return {
    type: track.type,
    file: track.file || null,
    url: track.url,
    cover: track.cover || '',
    title: track.title || '',
    artist: track.artist || '',
    album: track.album || '',
    duration: track.duration || 0,
    song_id: track.song_id || '',
    video_id: track.video_id || '',
    spotify_url: track.spotify_url || '',
    _song: song
      ? {
          song_id: song.song_id,
          video_id: song.video_id,
          name: song.name,
          artists: song.artists,
          artist_ids: song.artist_ids,
          album_name: song.album_name,
          album_id: song.album_id,
          cover_url: song.cover_url,
          duration: song.duration,
          url: song.url,
          source: song.source,
          explicit: song.explicit,
        }
      : null,
    playedAt: Date.now(),
  }
}

export function rememberPlayed(track) {
  if (!track || !track.url) return
  const key = trackKey(track)
  const next = [slim(track), ...played.value.filter((t) => trackKey(t) !== key)]
  played.value = next.slice(0, MAX_PLAYED)
  save(PLAYED_KEY, played.value)
}

export function forgetPlayed(track) {
  const key = trackKey(track)
  played.value = played.value.filter((t) => trackKey(t) !== key)
  save(PLAYED_KEY, played.value)
}

export function rememberSearch(query) {
  const q = String(query || '').trim()
  if (!q || q.length > 200) return
  const next = [q, ...searches.value.filter((s) => s.toLowerCase() !== q.toLowerCase())]
  searches.value = next.slice(0, MAX_SEARCHES)
  save(SEARCH_KEY, searches.value)
}

export function forgetSearch(query) {
  searches.value = searches.value.filter((s) => s !== query)
  save(SEARCH_KEY, searches.value)
}

export function clearSearches() {
  searches.value = []
  save(SEARCH_KEY, searches.value)
}

export function useRecent() {
  return {
    played,
    searches,
    rememberPlayed,
    forgetPlayed,
    rememberSearch,
    forgetSearch,
    clearSearches,
  }
}
