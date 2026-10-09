import { ensureAudio } from '/src/model/player/decks'
import { loadLyricsForCurrent } from '/src/model/player/lyrics'
import { syncMediaSession } from '/src/model/player/mediaSession'
import { buildShuffleOrder } from '/src/model/player/order'
import { fillMissingDetails, needsDetails } from '/src/model/player/recovery'
import {
  OLD_SESSION_KEY,
  SESSION_KEY,
  packSession,
  readSessionFrom,
} from '/src/model/player/sessionFormat'
import { ensureStreamDuration } from '/src/model/player/sound'
import {
  currentIndex,
  currentTime,
  currentTrack,
  duration,
  frameTime,
  playGen,
  playlist,
  shuffle,
} from '/src/model/player/state'

// --- Session restore ---
//
// Closing a music player and reopening it to silence and an empty queue is
// the difference between an app and a web page. The queue, which track was
// playing and how far into it are kept, and the next launch comes back to
// exactly that, paused. Deliberately paused: starting audio on its own
// before the window has even finished drawing is startling, and there is a
// play button right there. How the queue is written down, and read back
// from what older versions wrote, is in sessionFormat.js.
let sessionTimer = null
let sessionRestored = false

export function saveSession() {
  try {
    const blob = packSession(playlist.value, currentIndex.value, currentTime.value)
    if (!blob) {
      localStorage.removeItem(SESSION_KEY)
      return
    }
    localStorage.setItem(SESSION_KEY, blob)
    // The new form replaces the old; reading both would bring an old queue
    // back the day this one is cleared.
    localStorage.removeItem(OLD_SESSION_KEY)
  } catch {
    // Quota or blocked storage: the session just will not come back.
  }
}

// Called from the time update, so it has to be cheap. Writes at most once
// every few seconds rather than four times a second.
export function scheduleSessionSave() {
  if (sessionTimer) return
  sessionTimer = setTimeout(() => {
    sessionTimer = null
    saveSession()
  }, 4000)
}

// Load the track the user left off on, cued to where they left it, without
// starting it.
export function restoreSession() {
  if (sessionRestored) return false
  sessionRestored = true
  const blob = readSessionFrom(localStorage)
  if (!blob) return false
  const { tracks, index } = blob
  playlist.value = tracks
  currentIndex.value = index
  if (shuffle.value) buildShuffleOrder()
  // The queue's own copy, so that details filled in later reach the views.
  const track = currentTrack.value
  const at = blob.time
  duration.value = track.duration || 0
  currentTime.value = at
  frameTime.value = at
  const a = ensureAudio()
  try {
    a.src = track.url
    // The element has no idea how long the track is until it has read the
    // headers, and seeking before that silently does nothing.
    //
    // Tied to this load: if the restored track never loads (the file was
    // deleted since), the listener would otherwise wait for the next track's
    // metadata and throw that one to the old position.
    const gen = playGen
    const seek = () => {
      a.removeEventListener('loadedmetadata', seek)
      if (gen !== playGen) return
      try {
        if (at > 0 && at < (a.duration || Infinity)) a.currentTime = at
      } catch {
        // A stream that refuses to seek still plays from the start.
      }
    }
    a.addEventListener('loadedmetadata', seek)
    a.load()
  } catch {
    return false
  }
  syncMediaSession()
  if (track.type === 'stream') ensureStreamDuration(track)
  // An entry from an older version can be missing what the views show.
  if (needsDetails(track)) fillMissingDetails(track)
  // Lyrics are fetched when a track starts playing, and a restored one has
  // not started: without this the panel said "No lyrics found" for the track
  // in the player on every launch, until something else was played. One with
  // no title yet is looked up once its details are in.
  if (track.title) loadLyricsForCurrent()
  return true
}

if (typeof window !== 'undefined') {
  // The window can vanish without a clean shutdown (tray quit, a crash), so
  // the throttled save is backed up by one on the way out.
  window.addEventListener('beforeunload', saveSession)
  window.addEventListener('pagehide', saveSession)
}
