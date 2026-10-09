import { ref } from 'vue'
import API from '/src/model/api'
import { currentTime, currentTrack, duration, isPlaying } from '/src/model/player/state'
import { play, seek } from '/src/model/player/transport'

// The synced lyrics of the track in the player: fetched as it starts, the
// line the playhead is on, the per-song offset and the versions to choose
// between.

// --- Synced lyrics state ---
export const lyricsLines = ref([]) // [{ time, text }]
export const lyricsPlain = ref(null)
export const lyricsLoading = ref(false)
export const activeLyricIndex = ref(-1)
export const lyricsOffset = ref(0) // seconds; positive = lyrics appear later
const lyricsMeta = ref({ title: '', artist: '' }) // for saving offsets
const lyricVersions = ref([]) // all synced versions [{synced, plain}]
export const lyricVersionIndex = ref(0) // which version is showing
export const lyricVersionCount = ref(0) // how many versions exist
let lyricsToken = 0

// --- Synced lyrics ---
function _lyricsParams(track) {
  if (track.type === 'local' && track.file) {
    // Send the file AND what we know about the track. The backend used to
    // get only the filename, so an online lookup could only go on whatever
    // tags the download happened to write. When those are thin (a missing
    // artist is enough) the lookup was skipped entirely, which is why
    // lyrics published for a downloaded song never came back.
    return {
      file: track.file,
      title: track.title || '',
      artist: track.artist || '',
      album: track.album || '',
      duration: Math.round(track.duration || duration.value || 0),
    }
  }
  if (track.spotify_url) return { url: track.spotify_url }
  return {
    title: track.title,
    artist: track.artist,
    album: track.album || '',
    duration: Math.round(track.duration || duration.value || 0),
  }
}

export async function loadLyricsForCurrent(forceRefresh = false) {
  const track = currentTrack.value
  lyricsLines.value = []
  lyricsPlain.value = null
  activeLyricIndex.value = -1
  lyricVersions.value = []
  lyricVersionIndex.value = 0
  lyricVersionCount.value = 0
  if (!track) return
  const token = ++lyricsToken
  lyricsLoading.value = true
  try {
    const params = _lyricsParams(track)
    if (forceRefresh) params.refresh = 1
    const res = await API.getLyrics(params)
    if (token !== lyricsToken) return // a newer track took over
    const data = res.data || {}
    lyricsLines.value = data.synced || []
    lyricsPlain.value = data.plain || null
    lyricsOffset.value = typeof data.offset === 'number' ? data.offset : 0
    lyricVersionIndex.value =
      typeof data.version === 'number' ? data.version : 0
    lyricVersionCount.value =
      typeof data.version_count === 'number' ? data.version_count : 0
    lyricsMeta.value = {
      title: data.title || track.title || '',
      artist:
        data.artist ||
        (Array.isArray(track.artists) && track.artists[0]) ||
        (track.artist || '').split(',')[0].trim() ||
        '',
    }
    updateActiveLyric()
  } catch {
    if (token === lyricsToken) {
      lyricsLines.value = []
      lyricsPlain.value = null
      lyricsOffset.value = 0
    }
  } finally {
    if (token === lyricsToken) lyricsLoading.value = false
  }
}

export function updateActiveLyric(at) {
  const lines = lyricsLines.value
  if (!lines || lines.length === 0) {
    activeLyricIndex.value = -1
    return
  }
  // Apply the per-song offset: positive = lyrics appear later, so we compare
  // against (currentTime - offset).
  const now = typeof at === 'number' ? at : currentTime.value
  const tNow = now - lyricsOffset.value
  let idx = -1
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].time <= tNow + 0.25) idx = i
    else break
  }
  if (idx !== activeLyricIndex.value) activeLyricIndex.value = idx
}

export function seekToLyric(index) {
  const lines = lyricsLines.value
  if (index < 0 || index >= lines.length) return
  // Honour the offset so clicking a line jumps to where it actually plays.
  seek(lines[index].time + lyricsOffset.value)
  if (!isPlaying.value) play()
}

// Manually re-fetch lyrics for the current track, bypassing all caches.
export function refreshLyrics() {
  return loadLyricsForCurrent(true)
}

function sameSong(a, b) {
  const norm = (s) =>
    String(s || '')
      .toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, '')
  return !!norm(a) && norm(a) === norm(b)
}

// Someone just published lyrics for a song. If it's the one on screen, pull
// them in: indexing needs a beat, so give it a couple of tries
// rather than leaving the panel stubbornly empty.
async function onLyricsPublished(detail) {
  const track = currentTrack.value
  if (!track || !detail) return
  const title = track.title || ''
  const artist = (track.artist || '').split(',')[0].trim()
  if (!sameSong(detail.track, title)) return
  if (detail.artist && artist && !sameSong(detail.artist, artist)) return
  for (const wait of [0, 1500, 4000]) {
    if (wait) await new Promise((r) => setTimeout(r, wait))
    if (currentTrack.value !== track) return
    await loadLyricsForCurrent(true)
    if (lyricsLines.value.length || lyricsPlain.value) return
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('dannify:lyrics-published', (e) => onLyricsPublished(e.detail))
}

// Nudge the lyric sync live (seconds). Updates the active line immediately.
export function adjustLyricsOffset(delta) {
  const next = Math.max(-30, Math.min(30, lyricsOffset.value + delta))
  lyricsOffset.value = Math.round(next * 10) / 10
  updateActiveLyric()
}

export function resetLyricsOffset() {
  lyricsOffset.value = 0
  updateActiveLyric()
}

// Persist the current offset for this song so it's shared with future users.
export function saveLyricsOffset() {
  const { title, artist } = lyricsMeta.value
  if (!title || !artist) return Promise.resolve()
  return API.saveLyricsOffset(
    title,
    artist,
    lyricsOffset.value,
    lyricVersionCount.value > 1 ? lyricVersionIndex.value : undefined
  ).catch(() => {})
}

// Cycle to the next synced lyric version (when there are several). Lazily
// fetches the full version list the first time it's needed.
export async function switchLyricVersion(dir = 1) {
  const track = currentTrack.value
  if (!track) return
  // The version list is a round trip, and the track can change while it is
  // out. Nothing checked, so switching version and then skipping put the
  // previous song's lyrics on the new one, and left its version list behind
  // for the next switch to cycle through.
  const token = lyricsToken
  if (lyricVersions.value.length === 0) {
    // Load all versions on demand.
    let versions = []
    try {
      const res = await API.getLyricVersions(_lyricsParams(track))
      versions = (res.data && res.data.versions) || []
    } catch {
      versions = []
    }
    if (token !== lyricsToken || currentTrack.value !== track) return
    lyricVersions.value = versions
    if (lyricVersions.value.length === 0) return
  }
  const n = lyricVersions.value.length
  if (n <= 1) return
  lyricVersionIndex.value = (lyricVersionIndex.value + dir + n) % n
  const v = lyricVersions.value[lyricVersionIndex.value]
  lyricsLines.value = v.synced || []
  lyricsPlain.value = v.plain || null
  lyricVersionCount.value = n
  updateActiveLyric()
}

export function prefetchLyrics(track) {
  if (!track) return
  let params
  if (track.type === 'local' && track.file) params = { file: track.file }
  else if (track.spotify_url) params = { url: track.spotify_url }
  else if (track.title) {
    params = {
      title: track.title,
      artist: track.artist || '',
      album: track.album || '',
      duration: Math.round(track.duration || 0),
    }
  }
  if (params) API.getLyrics(params).catch(() => {})
}
