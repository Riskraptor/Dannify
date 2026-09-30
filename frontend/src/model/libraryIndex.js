import { ref } from 'vue'
import API from '/src/model/api'

// A lightweight, shared index of what's already on disk so search/queue/player
// can show a "downloaded" state instead of an endless download button - AND
// so clicking a downloaded song plays the local file instead of re-streaming
// it from YouTube.
//
// Two maps:
//   * ``byVideoId``  YouTube videoId → file (exact, written by recent downloads
//                    via the DANNIFY_VIDEO_ID tag)
//   * ``byKey``      normalized "artist|title" → file (fuzzy fallback for
//                    legacy files predating the video_id tag)
//
// Both are populated from a single ``/api/library`` fetch on first use.

const byVideoId = ref(new Map())
const byKey = ref(new Map())
const titleOnly = ref(new Map()) // normalised title alone: last-resort
// When the index was last read from the server.
const loadedAt = ref(0)
let loaded = false
let loadingPromise = null
let again = null

// Lower case, accents off, anything but a letter or digit a space. Letters in
// any script: this used to keep a to z and 0 to 9 only, which turned every
// Japanese, Korean or Cyrillic title into nothing. Two such songs then shared
// one empty key, so pressing Play on one could play the other, and every one
// of them showed as already downloaded.
function norm(s) {
  return String(s || '')
    .normalize('NFKD')
    .replace(/\p{M}+/gu, '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
}

function keyForSong(song) {
  if (!song) return ''
  const title = song.title || song.name || ''
  let artist = ''
  if (Array.isArray(song.artists) && song.artists.length) artist = song.artists[0]
  else artist = song.artist || ''
  return `${norm(artist)}|${norm(title)}`
}

function videoIdFor(song) {
  if (!song) return ''
  for (const k of ['video_id', 'videoId', 'song_id']) {
    const v = song[k]
    if (typeof v === 'string' && /^[A-Za-z0-9_-]{11}$/.test(v)) return v
  }
  return ''
}

async function load(force = false) {
  if (loaded && !force) return
  if (loadingPromise) {
    // Asked to read again while a read is on its way: two downloads finishing
    // close together. The second used to be dropped, and its song kept its
    // Download button and streamed instead of playing the saved copy.
    if (!force) return loadingPromise
    if (!again) {
      again = loadingPromise.then(() => {
        again = null
        return load(true)
      })
    }
    return again
  }
  // Stamped with when it was asked for, not when it came back: a read that
  // was already out when a download finished cannot know about that song,
  // and must not count as having looked.
  const askedAt = Date.now()
  loadingPromise = API.getLibrary()
    .then((res) => {
      const data = res.data || {}
      const tracks = Array.isArray(data.tracks) ? data.tracks : []
      const vMap = new Map()
      const kMap = new Map()
      const tMap = new Map()
      for (const tr of tracks) {
        if (!tr || !tr.file) continue
        // A saved copy that will not play is not a copy. Counted here, the
        // song showed as downloaded everywhere and every play of it from
        // search or home went to the broken file instead of streaming.
        if (tr.problem) continue
        if (tr.video_id && /^[A-Za-z0-9_-]{11}$/.test(tr.video_id)) {
          vMap.set(tr.video_id, tr.file)
        }
        const t0 = norm(tr.title || '')
        // No title left to go on (an emoji, say): a key of nothing but the
        // artist would claim every other such song by them.
        if (t0) kMap.set(`${norm(tr.artist || '')}|${t0}`, tr.file)
        const t = norm(tr.title || '')
        // Title-only map: only meaningful titles (>=4 chars), so "Hey" doesn't
        // collide with every random track. First match wins.
        if (t.length >= 4 && !tMap.has(t)) tMap.set(t, tr.file)
      }
      byVideoId.value = vMap
      byKey.value = kMap
      titleOnly.value = tMap
      loaded = true
      loadedAt.value = askedAt
    })
    .catch(() => {})
    .finally(() => {
      loadingPromise = null
    })
  return loadingPromise
}

function isDownloaded(song) {
  if (!song) return false
  const vid = videoIdFor(song)
  if (vid && byVideoId.value.has(vid)) return true
  const key = keyForSong(song)
  if (!key.split('|')[1]) return false
  if (byKey.value.has(key)) return true
  // Title-only fallback is ONLY used when we have no artist hint at all.
  // Otherwise we'd flag songs as "already downloaded" just because a
  // different artist's track happens to share the title.
  const [artistKey, titleNorm] = key.split('|')
  if (!artistKey && titleNorm.length >= 4 && titleOnly.value.has(titleNorm)) {
    return true
  }
  return false
}

// Synchronous local-file lookup. Returns the file path string when this
// song already exists on disk, '' otherwise. Used by trackFromSong so
// hitting Play on a downloaded result plays the local file instantly
// (no ffmpeg, no network) instead of re-streaming.
function localFileFor(song) {
  if (!song) return ''
  const vid = videoIdFor(song)
  if (vid) {
    const f = byVideoId.value.get(vid)
    if (f) return f
  }
  const key = keyForSong(song)
  if (!key.split('|')[1]) return ''
  const f = byKey.value.get(key)
  if (f) return f
  // Title-only is the LAST resort and ONLY fires when the caller had no
  // artist info at all (otherwise a different artist's "Nakupenda" would
  // wrongly play instead of streaming the requested artist's version).
  const [artistKey, titleNorm] = key.split('|')
  if (!artistKey && titleNorm.length >= 4) {
    const t = titleOnly.value.get(titleNorm)
    if (t) return t
  }
  return ''
}


// Server told us the on-disk library changed (a download finished, the
// user picked a new folder, etc.): drop our cache so the next call
// re-fetches from /api/library.
function invalidate() {
  loaded = false
  load(true)
}

export function useLibraryIndex() {
  return {
    load,
    isDownloaded,
    localFileFor,
    invalidate,
    byVideoId,
    byKey,
    loadedAt,
  }
}
