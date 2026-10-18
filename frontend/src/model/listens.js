import { ref, watch } from 'vue'
import API from '/src/model/api'
import { createListenMeter } from '/src/model/listenMeter'
import { sameSong } from '/src/model/recent'
import { entryOf } from '/src/model/playlists'
import { queueRow } from '/src/model/tracks'
import { currentTime, currentTrack, duration, isPlaying } from '/src/model/player/state'
import { notePlayed } from '/src/model/support'

// What has been listened to: the app's own history, behind the History and
// Stats pages and the shelves Home makes from them.
//
// It is kept by the app (Backend/dannify/listens.py), in its data folder, not
// in this window's storage: a history is the kind of thing somebody expects
// to still be there after the window's storage has been cleared, and it grows
// for years. This watches the player, counts the time each song really spent
// playing (listenMeter.js), and hands each listen over as it ends.
//
// It stays on this computer, it can be switched off, and one listen or all of
// them can be taken out again. Nothing is sent anywhere else unless
// ListenBrainz is connected in Settings, and then only the listens, which go
// on from the app (scrobble.py) even while the history itself is paused.

const KEEP_KEY = 'dn.listenHistory'
const PENDING_KEY = 'dn.listens'
// How much more has to be heard before the listen so far is written down
// again, in case the app goes without saying goodbye.
const NOTE_EVERY = 10
const MAX_WAITING = 200

function readStored(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw === null ? fallback : JSON.parse(raw)
  } catch {
    return fallback
  }
}
function writeStored(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Blocked or full: a listen can be lost if the app closes mid-song.
  }
}

/** Whether a history is kept at all. On, unless it was turned off. */
export const keeping = ref(readStored(KEEP_KEY, true) !== false)
/** Goes up whenever the history changes; pages showing it read it again. */
export const listensEpoch = ref(0)
/** Whether listens go on to ListenBrainz (connected in Settings). */
export const scrobbling = ref(false)
/** Listens are counted when either wants them. */
function counting() {
  return keeping.value || scrobbling.value
}

// Listens that have ended and are waiting to be handed over, and the one
// still going as it stood a moment ago. Read back at the next start, so a
// song cut short by the app closing still counts.
const stored = readStored(PENDING_KEY, null)
const waiting = Array.isArray(stored && stored.done) ? stored.done.slice(-MAX_WAITING) : []
if (stored && stored.open) waiting.push(stored.open)
let openNote = null
let notedAt = 0

function save() {
  writeStored(PENDING_KEY, { done: waiting, open: openNote })
}

/** A listen as the app is told of it, or null when there is nothing to play
 *  the song by later (a file opened from outside the library). */
function payloadOf(listen) {
  if (!listen || !listen.track || !listen.started) return null
  const track = entryOf(queueRow(listen.track, 0))
  if (!track || (!track.video_id && !track.file)) return null
  if (listen.duration > 0) track.duration = Math.round(listen.duration)
  return { track, seconds: listen.seconds, started: Math.round(listen.started / 1000) }
}

let draining = false
let retry = 0
async function drain() {
  if (draining) return
  draining = true
  clearTimeout(retry)
  try {
    while (waiting.length) {
      let recorded = false
      try {
        const res = await API.recordListen(waiting[0])
        recorded = !!(res && res.data && res.data.recorded)
      } catch (err) {
        // No answer at all: the app is not listening yet, or has gone. Kept,
        // and tried again shortly. An answer that says no is final.
        if (!err || !err.response) {
          retry = setTimeout(drain, 15000)
          break
        }
      }
      waiting.shift()
      save()
      if (recorded) listensEpoch.value++
    }
  } finally {
    draining = false
  }
}

function keep(listen) {
  openNote = null
  notedAt = 0
  // Counted whether or not the history is kept: it is only a number.
  notePlayed()
  const payload = counting() ? payloadOf(listen) : null
  if (payload) {
    // For the history, or for ListenBrainz alone while the history is paused.
    payload.keep = keeping.value
    waiting.push(payload)
    if (waiting.length > MAX_WAITING) waiting.splice(0, waiting.length - MAX_WAITING)
  }
  save()
  if (payload) drain()
}

const meter = createListenMeter({ same: sameSong })

function report() {
  const finished = meter.tick({
    track: currentTrack.value,
    playing: isPlaying.value,
    position: currentTime.value,
    duration: duration.value,
  })
  if (finished) keep(finished)
  if (!counting()) return
  const sofar = meter.peek()
  if (sofar && sofar.seconds - notedAt >= NOTE_EVERY) note(sofar)
}

function note(sofar = meter.peek()) {
  if (!counting()) return
  const payload = payloadOf(sofar)
  if (!payload) return
  payload.keep = keeping.value
  openNote = payload
  notedAt = payload.seconds
  save()
}

let started = false
/** Start keeping count. Called once, as the app starts. */
export function startListening() {
  if (started || typeof window === 'undefined') return
  started = true
  // Not `flush: 'sync'`: taking a song out of the queue moves the list and
  // then the place in it, and between the two the player seems, for an
  // instant, to be on another song. Read then, the song still playing was
  // counted as ended and begun again.
  watch([currentTrack, isPlaying, currentTime], report)
  // The same song starting over because the queue came round to it.
  window.addEventListener('dannify:played', () => {
    const finished = meter.restart()
    if (finished) keep(finished)
  })
  window.addEventListener('pagehide', () => note())
  window.addEventListener('beforeunload', () => note())
  API.listenBrainzStatus()
    .then((res) => setScrobbling(!!(res.data && res.data.connected)))
    .catch(() => {})
  if (waiting.length) {
    save()
    drain()
  }
}

export function setKeeping(on) {
  keeping.value = !!on
  writeStored(KEEP_KEY, keeping.value)
  if (!on) {
    // What was waiting for the history is not kept now. It still goes to
    // ListenBrainz when that is connected.
    if (scrobbling.value) {
      waiting.forEach((p) => (p.keep = false))
      if (openNote) openNote.keep = false
    } else {
      openNote = null
      waiting.length = 0
    }
    save()
  }
}

export function setScrobbling(on) {
  scrobbling.value = !!on
}

// ---------------------------------------------------------------------------
// Reading it back
// ---------------------------------------------------------------------------

// The last answer for each stretch, good until the history changes: going
// from Stats to a song and back does not ask again.
const statsCache = new Map()

/** The summary for the last `days` days (0: ever). See listens.stats. */
export async function fetchStats(days = 0, top = 50) {
  const key = `${days}:${top}`
  const hit = statsCache.get(key)
  if (hit && hit.epoch === listensEpoch.value) return hit.data
  const epoch = listensEpoch.value
  const res = await API.getListenStats(days, top)
  statsCache.set(key, { epoch, data: res.data })
  return res.data
}

/** A page of the history, newest first: `{items, more, total}`. */
export async function fetchHistory(limit = 100, before = 0) {
  const res = await API.getListenHistory(limit, before)
  return res.data
}

/** Take one listen out of the history. */
export async function forgetListen(item) {
  const res = await API.forgetListen(item.at, item.key)
  const removed = !!(res.data && res.data.removed)
  if (removed) listensEpoch.value++
  return removed
}

/** Forget everything that was listened to. */
export async function clearListens() {
  await API.clearListens()
  waiting.length = 0
  openNote = null
  save()
  listensEpoch.value++
}

export function useListens() {
  return {
    keeping,
    setKeeping,
    scrobbling,
    setScrobbling,
    listensEpoch,
    fetchStats,
    fetchHistory,
    forgetListen,
    clearListens,
  }
}
