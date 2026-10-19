// What to play next from the library when the queue runs out and YouTube
// Music's endless mix cannot be had (offline, or a song it knows nothing
// about). More by the same artist first, then the rest of the album, then
// the rest of the library, never a song already in the queue. The music
// keeps going on a plane.

const MOST = 25

function shuffled(list, random) {
  const out = [...list]
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

function fold(text) {
  return String(text || '')
    .normalize('NFKD')
    .replace(/\p{M}+/gu, '')
    .toLowerCase()
    .trim()
}

/**
 * Library tracks to follow *current*, best first.
 *
 * *queued* is every track already in the queue (files and video ids are
 * compared). *random* is Math.random, or a fixed one for tests.
 */
export function chooseFromLibrary(current, tracks, queued = [], { limit = MOST, random = Math.random } = {}) {
  const taken = new Set()
  for (const t of queued) {
    if (t && t.file) taken.add(`f:${t.file}`)
    if (t && t.video_id) taken.add(`v:${t.video_id}`)
  }
  const free = (tracks || []).filter(
    (tr) => tr && tr.file && !tr.problem && !taken.has(`f:${tr.file}`) && !(tr.video_id && taken.has(`v:${tr.video_id}`))
  )
  const artist = fold(current && (current.group || current.artist))
  const album = fold(current && current.album)

  const sameArtist = []
  const sameAlbum = []
  const rest = []
  for (const tr of free) {
    const names = [tr.group, tr.artist, ...(tr.artists || [])].map(fold)
    if (artist && names.includes(artist)) sameArtist.push(tr)
    else if (album && fold(tr.album) === album) sameAlbum.push(tr)
    else rest.push(tr)
  }
  return [...shuffled(sameArtist, random), ...shuffled(sameAlbum, random), ...shuffled(rest, random)].slice(0, limit)
}
