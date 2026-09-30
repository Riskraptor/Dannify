import { ref } from 'vue'
import API from '/src/model/api'

// Who each saved artist is online: their page id and their own picture. The
// sidebar, the Artists grid and an artist's page used to show the cover of one
// of their albums; now they show the artist, once the server has found them
// (it looks each one up once and remembers). Until then, and offline, the
// album cover stays.

const links = ref({})
let inflight = null
let again = null
let tries = 0
let timer = null

function load() {
  if (inflight) {
    if (!again) {
      again = inflight.then(() => {
        again = null
        return load()
      })
    }
    return again
  }
  inflight = API.getArtistLinks()
    .then((res) => {
      const data = res.data || {}
      links.value = data.links || {}
      // Some still being looked up: ask again shortly, a few times.
      clearTimeout(timer)
      if (data.pending > 0 && tries < 8) {
        tries++
        timer = setTimeout(load, 3500)
      } else {
        tries = 0
      }
    })
    .catch(() => {})
    .finally(() => {
      inflight = null
    })
  return inflight
}

let started = false
function ensure() {
  if (!started) {
    started = true
    load()
  }
}

if (typeof window !== 'undefined') {
  // A new artist in the library is a new name to find.
  window.addEventListener('dannify:library-changed', () => {
    if (!started) return
    tries = 0
    clearTimeout(timer)
    timer = setTimeout(load, 1500)
  })
}

/** The artist's own picture, sized for where it is drawn, or ''. */
export function artistPhoto(name, px = 0) {
  const hit = links.value[name]
  const url = (hit && hit.photo) || ''
  if (!url || !px) return url
  return url.replace(/=w\d+-h\d+[^&]*$/, `=w${px}-h${px}-l90-rj`)
}

/** The artist's YouTube Music page id, or ''. */
export function artistId(name) {
  const hit = links.value[name]
  return (hit && hit.id) || ''
}

export function useArtistLinks() {
  ensure()
  return { links, load, artistPhoto, artistId }
}
