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
let loaded = false
let loadingPromise = null

function norm(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
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
  if (loadingPromise) return loadingPromise
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
        const k = `${norm(tr.artist || '')}|${norm(tr.title || '')}`
        kMap.set(k, tr.file)
        const t = norm(tr.title || '')
        // Title-only map: only meaningful titles (>=4 chars), so "Hey" doesn't
        // collide with every random track. First match wins.
        if (t.length >= 4 && !tMap.has(t)) tMap.set(t, tr.file)
      }
      byVideoId.value = vMap
      byKey.value = kMap
      titleOnly.value = tMap
      loaded = true
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
  if (key && byKey.value.has(key)) return true
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
  }
}
