import API from '/src/model/api'

// How a queue entry is written down between runs, and read back.
//
// The queue used to be stored as the track objects themselves. That kept
// everything, but twice over (the track's title, picture and length again on
// the song it came from), with the level measured for this run and every
// address in full, so a long queue of YouTube songs was mostly repetition.
// An entry is now each detail once, without anything that can be rebuilt
// (addresses) or measured again (loudness), and with a ceiling on how much
// any one field can hold. Read back, it is the same track the views, the
// lyrics lookup and the system media controls were reading before.

export const SESSION_KEY = 'dannify.session.v2'
// Written by versions before this one: whole track objects.
export const OLD_SESSION_KEY = 'dannify.session.v1'
// Past this the queue is someone else's afternoon. Coming back to it would
// be surprising rather than helpful.
export const SESSION_TTL_MS = 14 * 24 * 60 * 60 * 1000
// A queue longer than this is a whole playlist; storing all of it every few
// seconds is not worth the quota.
export const SESSION_MAX_TRACKS = 200
// What has played is worth less than what is still to come: a cut queue
// starts this far before the playing track, and reaches further back only
// when the queue ends sooner than the window does.
const KEEP_PLAYED = 50
// The whole blob, in characters. Only an unusual queue gets near it.
const SESSION_MAX_CHARS = 400 * 1024

const MAX_TEXT = 500 // a title, an artist, an album
const MAX_LINK = 2048 // a picture's address
const MAX_EXTRA = 300 // any other detail a song came with
const MAX_LIST = 20 // artists, genres
const MAX_EXTRAS = 40

const YT_VIDEO = /^[A-Za-z0-9_-]{11}$/

export const musicLink = (id) => `https://music.youtube.com/watch?v=${id}`

/** A track played from a one-off address (a file opened from Explorer). */
export function isOneOff(track) {
  return String((track && track.url) || '').startsWith('/opened/')
}

const text = (v) => (typeof v === 'string' ? v.slice(0, MAX_TEXT) : '')
const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
// A picture held in the address itself (data:) can be most of a megabyte,
// and it comes back with the song anyway.
const link = (v) => (typeof v === 'string' && v.length <= MAX_LINK && !/^data:/i.test(v) ? v : '')

function put(out, key, value) {
  if (value === '' || value === null || value === undefined || value === 0) return
  if (Array.isArray(value) && !value.length) return
  out[key] = value
}

function flat(v) {
  if (typeof v === 'string') return v.length <= MAX_EXTRA ? v : undefined
  if (typeof v === 'number') return Number.isFinite(v) ? v : undefined
  if (typeof v === 'boolean' || v === null) return v
  return undefined
}

// One more detail a song came with (an artist's channel, an album's id, a
// track number a download is told about). Kept when it is small and plain;
// anything nested or long is the source's business and comes back with it.
function extra(v) {
  if (!Array.isArray(v)) return flat(v)
  const out = []
  for (const item of v.slice(0, MAX_LIST)) {
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const o = {}
      for (const [k, x] of Object.entries(item)) {
        const f = flat(x)
        if (f !== undefined) o[k] = f
      }
      out.push(o)
    } else {
      const f = flat(item)
      if (f !== undefined) out.push(f)
    }
  }
  return out
}

function streamUrlOf({ video_id, spotify_url }) {
  if (video_id) return API.streamURL(video_id)
  if (spotify_url) return API.streamURLFromLink(spotify_url)
  return ''
}

const sameList = (a, b) => Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((x, i) => x === b[i])
const splitArtists = (artist) => (artist ? artist.split(', ') : [])

// What the song itself knows and the track does not. Whatever the track
// already says (its title, picture, length, ids) is left for unpack() to
// copy back.
function packSong(song, track) {
  const out = {}
  const vid = track.video_id || ''
  for (const [key, value] of Object.entries(song)) {
    if (Object.keys(out).length >= MAX_EXTRAS) break
    if (key === 'name' && value === track.title) continue
    if (key === 'cover_url' && value === track.cover) continue
    if (key === 'duration' && value === track.duration) continue
    if (key === 'album_name' && value === track.album) continue
    if (key === 'song_id' && value === track.song_id) continue
    if (key === 'video_id' && value === vid) continue
    if (key === 'artists' && sameList(value, splitArtists(track.artist))) continue
    if (key === 'url' && (value === track.spotify_url || (vid && value === musicLink(vid)))) continue
    let v
    if (key === 'name' || key === 'album_name') v = text(value)
    else if (key === 'cover_url' || key === 'url') v = link(value)
    else v = extra(value)
    if (v !== undefined && v !== '') out[key] = v
  }
  return out
}

/** A track as it is written down, or null for one that cannot come back. */
export function pack(track) {
  if (!track || typeof track !== 'object' || isOneOff(track)) return null
  const local = track.type === 'local'
  if (local && !track.file) return null
  const vid = typeof track.video_id === 'string' && YT_VIDEO.test(track.video_id) ? track.video_id : ''
  const out = { type: local ? 'local' : 'stream' }
  if (local) out.file = String(track.file)
  put(out, 'title', text(track.title))
  put(out, 'artist', text(track.artist))
  put(out, 'album', text(track.album))
  put(out, 'duration', Math.round(num(track.duration) * 1000) / 1000)
  put(out, 'video_id', vid)
  if (track.song_id !== vid) put(out, 'song_id', text(track.song_id))
  put(out, 'spotify_url', link(track.spotify_url))
  // Only a stream keeps its picture and address: a saved song's are rebuilt
  // from its path.
  if (!local) {
    put(out, 'cover', link(track.cover))
    const url = typeof track.url === 'string' ? track.url : ''
    if (url && url !== streamUrlOf(out)) put(out, 'url', link(url))
    if (!out.url && !streamUrlOf(out)) return null
  }
  if (track.savedCopyGone) out.gone = true
  const song = track._song
  if (song && typeof song === 'object') {
    out.song = packSong(song, { ...track, ...out, video_id: vid, song_id: out.song_id ?? vid })
  }
  return out
}

/** A written-down entry as the track the player plays, or null. */
export function unpack(entry) {
  if (!entry || typeof entry !== 'object') return null
  const vid = typeof entry.video_id === 'string' && YT_VIDEO.test(entry.video_id) ? entry.video_id : ''
  const songId = typeof entry.song_id === 'string' ? entry.song_id : vid
  const title = text(entry.title)
  const artist = text(entry.artist)
  const album = text(entry.album)
  const duration = num(entry.duration)
  let track
  if (entry.type === 'local') {
    if (typeof entry.file !== 'string' || !entry.file) return null
    track = {
      type: 'local',
      file: entry.file,
      url: API.downloadFileURL(entry.file),
      cover: API.coverFileURL(entry.file),
      title,
      artist,
      album,
      duration,
      video_id: vid,
      song_id: songId,
    }
  } else {
    const spotify = link(entry.spotify_url)
    const url = streamUrlOf({ video_id: vid, spotify_url: spotify }) || link(entry.url)
    if (!url || isOneOff({ url }) || /^https?:/i.test(url)) return null
    track = {
      type: 'stream',
      file: null,
      song_id: songId,
      video_id: vid,
      spotify_url: spotify,
      url,
      cover: link(entry.cover),
      title,
      artist,
      album,
      duration,
    }
    if (entry.gone) track.savedCopyGone = true
  }
  const song = entry.song
  if (song && typeof song === 'object') {
    track._song = {
      ...song,
      song_id: song.song_id ?? songId,
      video_id: song.video_id ?? vid,
      name: song.name ?? title,
      artists: Array.isArray(song.artists) ? song.artists : splitArtists(artist),
      album_name: song.album_name ?? album,
      cover_url: song.cover_url ?? (track.type === 'stream' ? track.cover : ''),
      duration: song.duration ?? duration,
      url: song.url ?? (track.spotify_url || (vid ? musicLink(vid) : '')),
    }
  }
  return track
}

/**
 * The queue as it is stored: a window of it around the playing track, each
 * entry packed. Returns null when there is nothing worth keeping.
 */
export function packSession(list, index, time) {
  if (!Array.isArray(list) || index < 0 || index >= list.length) return null
  if (isOneOff(list[index])) return null
  const kept = []
  let at = -1
  list.forEach((tr, i) => {
    const p = i === index || !isOneOff(tr) ? pack(tr) : null
    if (i === index) {
      if (!p) return
      at = kept.length
    }
    if (p) kept.push(p)
  })
  if (at < 0) return null
  // Most of a cut queue is what is still to come.
  let size = SESSION_MAX_TRACKS
  for (;;) {
    const start = Math.max(0, Math.min(at - Math.min(KEEP_PLAYED, size - 1), kept.length - size))
    const tracks = kept.slice(start, start + size)
    const blob = JSON.stringify({
      v: 2,
      tracks,
      index: at - start,
      time: Math.max(0, Math.floor(num(time))),
      ts: Date.now(),
    })
    if (blob.length <= SESSION_MAX_CHARS || size <= 1) return blob
    size = Math.max(1, Math.floor(size / 2))
  }
}

/**
 * The stored queue as tracks: `{ tracks, index, time }`, or null. Reads what
 * this version writes and, failing that, what the one before it wrote.
 */
export function readSessionFrom(storage) {
  let raw = null
  let old = false
  try {
    raw = storage.getItem(SESSION_KEY)
    if (!raw) {
      raw = storage.getItem(OLD_SESSION_KEY)
      old = !!raw
    }
  } catch {
    return null
  }
  let blob
  try {
    blob = JSON.parse(raw || 'null')
  } catch {
    return null
  }
  if (!blob || !Array.isArray(blob.tracks) || !blob.tracks.length) return null
  if (Date.now() - (blob.ts || 0) > SESSION_TTL_MS) return null
  const index = Number(blob.index)
  if (!Number.isInteger(index) || index < 0 || index >= blob.tracks.length) return null
  // The old form is whole tracks: packing them first gives them the same
  // treatment (addresses rebuilt, measurements dropped) as the new one.
  const entries = old ? blob.tracks.map(pack) : blob.tracks
  if (!entries[index]) return null
  const tracks = []
  let at = -1
  entries.forEach((e, i) => {
    const tr = unpack(e)
    if (!tr) return
    if (i === index) at = tracks.length
    tracks.push(tr)
  })
  if (at < 0) return null
  return { tracks, index: at, time: Math.max(0, Number(blob.time) || 0) }
}
