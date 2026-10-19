import { ref } from 'vue'
import API from '/src/model/api'
import { trackFromSong } from '/src/model/player/makeTrack'
import { addToShuffleOrder } from '/src/model/player/order'
import { setPlaylist } from '/src/model/player/queue'
import {
  YT_ID,
  currentTrack,
  playGen,
  playlist,
  readStored,
  shuffle,
  videoIdOf,
} from '/src/model/player/state'
import { playAt } from '/src/model/player/transport'
import { useLibrary } from '/src/model/library'
import { chooseFromLibrary } from '/src/model/player/libraryRadio'

// Autoplay: when the queue runs dry, keep going with YouTube Music's endless
// mix for the last track: the behaviour every streaming app has.
const AUTOPLAY_KEY = 'dannify-autoplay-radio'
export const autoplayRadio = ref(readStored(AUTOPLAY_KEY) !== '0')
let radioSeed = ''

export function setAutoplayRadio(on) {
  autoplayRadio.value = !!on
  try {
    localStorage.setItem(AUTOPLAY_KEY, on ? '1' : '0')
  } catch {
    // ignore
  }
}

// Append the endless mix for `seed` and keep playing. Returns false when
// there is nothing to extend with (offline, no videoId, already tried).
// Fetching a station is a real round trip, and the user keeps clicking while
// it runs. Every one of these captures playGen first and drops its result if
// the queue moved on, so a late answer can never hijack what is playing now.
export async function extendWithRadio() {
  if (!autoplayRadio.value) return false
  const id = videoIdOf(currentTrack.value)
  const gen = playGen
  if (id && radioSeed !== id) {
    radioSeed = id
    try {
      const res = await API.getRadio(id)
      const songs = (res.data && res.data.songs) || []
      if (gen !== playGen) return true
      if (songs.length) {
        append(songs.map(trackFromSong))
        return true
      }
    } catch {
      // Offline, most likely: the library carries on instead.
    }
    if (gen !== playGen) return true
  }
  return continueFromLibrary()
}

function append(tracks) {
  const at = playlist.value.length
  const added = shuffle.value ? addToShuffleOrder(at, tracks.length, { mix: true }) : null
  playlist.value = [...playlist.value, ...tracks]
  playAt(added ? added[0] : at)
}

// No mix to be had (offline, or a song YouTube knows nothing of): more from
// the library, by the same artist first (libraryRadio.js).
function continueFromLibrary() {
  const current = currentTrack.value || {}
  const known = useLibrary().tracks.value
  const mine = known.find((tr) => tr.file && tr.file === current.file) || current
  const chosen = chooseFromLibrary(mine, known, playlist.value)
  if (!chosen.length) return false
  append(
    chosen.map((tr) => ({
      type: 'local',
      file: tr.file,
      url: API.downloadFileURL(tr.file),
      cover: API.coverFileURL(tr.file, Math.floor(tr.added || 0)),
      title: tr.title,
      artist: tr.artist_display || tr.artist,
      album: tr.album,
      duration: tr.duration,
      video_id: tr.video_id || '',
    }))
  )
  return true
}

/** Replace the queue with a station built around one song. */
export async function startRadio(song) {
  const seed = song && (song.video_id || song.song_id)
  if (!seed || !YT_ID.test(seed)) return false
  radioSeed = seed
  setPlaylist([trackFromSong(song)], { startIndex: 0 })
  const gen = playGen
  try {
    const res = await API.getRadio(seed)
    const songs = (res.data && res.data.songs) || []
    if (gen !== playGen) return false // the user started something else
    if (songs.length) {
      if (shuffle.value) addToShuffleOrder(playlist.value.length, songs.length, { mix: true })
      playlist.value = [...playlist.value, ...songs.map(trackFromSong)]
    }
    return songs.length > 0
  } catch {
    return false
  }
}
