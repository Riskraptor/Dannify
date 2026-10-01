import { ref } from 'vue'
import API from './api'

// Local listening history + recent searches (persisted, per device). Powers
// the "Jump back in" shelf on Home and the recent list on the Search page.

const PLAYED_KEY = 'dn.recentPlayed'
const SEARCH_KEY = 'dn.recentSearches'
const MAX_PLAYED = 40
const MAX_SEARCHES = 12

// A saved track's URL is rebuilt from its path, never replayed from storage.
//
// This used to keep the resolved url, which was fine until the file it named
// was renamed underneath it. Converting the library to containers renames
// every one of them, so a shelf written before that pointed at .mp3 files
// that no longer existed, and kept pointing at them across restarts: the
// library refresh reaches what the app is showing, not what a previous run
// wrote to disk. The path is the durable part, so that is what is stored.
function rebuilt(entry) {
  if (!entry || typeof entry !== 'object') return entry
  if (entry.type !== 'local' || !entry.file) return entry
  return {
    ...entry,
    url: API.downloadFileURL(entry.file),
    cover: API.coverFileURL(entry.file),
  }
}

// A file opened from Explorer plays through a one-off address that dies with
// the run it was made in. Kept here, it came back after a restart as a tile
// with no picture that could only fail when pressed.
function oneOff(entry) {
  return !!entry && typeof entry === 'object' && String(entry.url || '').startsWith('/opened/')
}

function load(key) {
  try {
    const v = JSON.parse(localStorage.getItem(key) || '[]')
    if (!Array.isArray(v)) return []
    return v.filter((e) => !oneOff(e)).map(rebuilt)
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

// Written back without the rebuilt URLs, so what lands on disk stays
// path-only and a later rename cannot strand it.
function savePlayed() {
  save(
    PLAYED_KEY,
    played.value.map((e) =>
      e && e.type === 'local' && e.file ? { ...e, url: '', cover: '' } : e
    )
  )
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
  const local = track.type === 'local' && track.file
  return {
    type: track.type,
    file: track.file || null,
    // Rebuilt from `file` on the way back in, so a rename cannot strand it.
    url: local ? '' : track.url,
    cover: local ? '' : track.cover || '',
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
  if (!track || !track.url || oneOff(track)) return
  const key = trackKey(track)
  const next = [
    rebuilt(slim(track)),
    ...played.value.filter((t) => trackKey(t) !== key),
  ]
  played.value = next.slice(0, MAX_PLAYED)
  savePlayed()
}

export function forgetPlayed(track) {
  const key = trackKey(track)
  played.value = played.value.filter((t) => trackKey(t) !== key)
  savePlayed()
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
