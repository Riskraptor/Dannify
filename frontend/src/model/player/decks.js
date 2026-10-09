import { createEngine } from '/src/model/audioEngine'
import { updateActiveLyric } from '/src/model/player/lyrics'
import { syncMediaSession, syncPositionState } from '/src/model/player/mediaSession'
import { applyEq, balance, crossfade, gapless, mono } from '/src/model/player/mixer'
import { nextIndex } from '/src/model/player/order'
import { noteStarted, onPlaybackError } from '/src/model/player/recovery'
import { scheduleSessionSave } from '/src/model/player/session'
import { sleepMode } from '/src/model/player/sleep'
import { applyVolume, ensureStreamDuration } from '/src/model/player/sound'
import {
  clipLoopEnd,
  clipLoopStart,
  currentTime,
  currentTrack,
  duration,
  frameTime,
  isBuffering,
  isPlaying,
  noAutoAdvance,
  playGen,
  playlist,
  repeatMode,
  streamBaseOffset,
} from '/src/model/player/state'
import { onEnded, playAt } from '/src/model/player/transport'

// The audio elements and what they report. With the sound engine there are
// two decks, so the next song can load and fade in on one while the last one
// fades out on the other; without it, one element does everything.

let frameLoop = 0

export function elementTime() {
  if (!audio) return currentTime.value
  const track = currentTrack.value
  if (track && track.type === 'stream' && streamBaseOffset > 0) {
    return streamBaseOffset + audio.currentTime
  }
  return audio.currentTime
}

function tick() {
  frameLoop = 0
  if (!audio || audio.paused || document.hidden) return
  frameTime.value = elementTime()
  updateActiveLyric(frameTime.value)
  frameLoop = requestAnimationFrame(tick)
}

function startFrameClock() {
  if (!frameLoop && typeof requestAnimationFrame === 'function') {
    frameLoop = requestAnimationFrame(tick)
  }
}

function stopFrameClock() {
  if (frameLoop && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(frameLoop)
  frameLoop = 0
  frameTime.value = currentTime.value
}

export let audio = null
// The sound engine (see audioEngine.js), or null where there is none and the
// element's own volume does the work. *deck* is the one playing; the other
// waits, holds the next song ready, or fades out the last one.
export let engine = null
let engineTried = false
export let deck = null
const decks = []
// How long a song fades out when another is picked by hand, so a skip does
// not click. Automatic changes use the crossfade (or the gapless overlap).
export const MANUAL_FADE = 0.25
export const GAPLESS_OVERLAP = 0.12

export function ensureAudio() {
  if (audio) return audio
  if (!engineTried) {
    engineTried = true
    const made = createEngine()
    engine = made.available ? made : null
  }
  audio = makeElement()
  if (engine) {
    try {
      deck = engine.attach(audio)
      decks.push(deck)
      applyEq()
      engine.setBalance(balance.value)
      engine.setMono(mono.value)
    } catch {
      // The element would not join the graph: play without the engine.
      engine = null
      deck = null
    }
  }
  applyVolume(true)
  return audio
}

// The deck that is not playing, made the first time it is needed.
export function otherDeck() {
  if (!engine) return null
  if (decks.length < 2) {
    try {
      decks.push(engine.attach(makeElement()))
    } catch {
      return null
    }
  }
  return decks.find((d) => d !== deck) || null
}

// The waiting deck becomes the one that plays.
export function takeDeck(d) {
  deck = d
  audio = d.el
}

function stopElement(el) {
  try {
    el.pause()
  } catch {
    // already stopped
  }
  el.removeAttribute('src')
  try {
    el.load()
  } catch {
    // nothing to unload
  }
}

// The song that was playing goes quiet on its own deck and then stops,
// while the next one starts on the other.
export function retire(d, seconds) {
  if (!d || !d.el.src) return
  d.preloaded = null
  if (d.el.paused || seconds <= 0.01) {
    stopElement(d.el)
    return
  }
  d.fadeTo(0, seconds).then(() => {
    if (d !== deck) stopElement(d.el)
  })
}

// Stop anything still fading out (a pause, the sleep timer).
export function silenceRetiring() {
  for (const d of decks) if (d !== deck && d.el.src) stopElement(d.el)
}

// The next song, loaded on the waiting deck before it is needed: gapless
// means starting it the instant this one stops, and that only works if it is
// already there.
function preloadNext(i) {
  const nxt = playlist.value[i]
  if (!engine || !nxt) return
  const d = otherDeck()
  if (!d || d.preloaded === nxt) return
  if (d.el.src && !d.el.paused) return // still fading out the last one
  d.preloaded = nxt
  d.el.preload = 'auto'
  d.el.src = nxt.url
  try {
    d.el.load()
  } catch {
    // it loads when played
  }
}

// --- Crossfade and gapless: the change to the next song, near the end ---
let transitionTimer = 0
let transitionFor = -1
function plannedOverlap() {
  if (!engine) return -1
  if (repeatMode.value === 'one' || noAutoAdvance.value || clipLoopStart.value != null) return -1
  if (sleepMode.value === 'track') return -1
  if (crossfade.value > 0) return crossfade.value
  return gapless.value ? GAPLESS_OVERLAP : -1
}
function maybeTransition() {
  if (!audio || audio.paused || transitionFor === playGen) return
  const overlap = plannedOverlap()
  if (overlap < 0) return
  const d = duration.value
  // Short tracks (an intro, a skit) are not faded over half their length.
  if (!(d > 0) || d < overlap * 2 + 4) return
  const remaining = d - elementTime()
  if (remaining > overlap + 20) return
  const i = nextIndex()
  if (i < 0) return
  preloadNext(i)
  if (remaining > overlap + 1.5) return
  transitionFor = playGen
  const gen = playGen
  const rate = audio.playbackRate || 1
  transitionTimer = setTimeout(() => {
    transitionTimer = 0
    if (gen !== playGen || !audio || audio.paused) {
      if (gen === playGen) transitionFor = -1
      return
    }
    const j = nextIndex()
    if (j >= 0) playAt(j, { fade: overlap })
  }, Math.max(0, ((remaining - overlap) / rate) * 1000))
}
export function cancelTransition() {
  clearTimeout(transitionTimer)
  transitionTimer = 0
  transitionFor = -1
}

let visibilityHooked = false
function makeElement() {
  const el = new Audio()
  el.preload = 'metadata'
  // Only the deck that is playing speaks for the player. The other one's
  // events (its fade-out ending, its src being cleared) are not news.
  const on = (type, fn) =>
    el.addEventListener(type, (e) => {
      if (el === audio) fn(e)
    })
  on('timeupdate', () => {
    const track = currentTrack.value
    // With the byte-range proxy the browser knows the real currentTime
    // for streams too: no need for the virtual clock anymore. The
    // ``streamBaseOffset`` shim is only kept for the legacy ``?t=`` /
    // ffmpeg fallback path; it's 0 on the happy path.
    if (track && track.type === 'stream' && streamBaseOffset > 0) {
      currentTime.value = streamBaseOffset + audio.currentTime
    } else {
      currentTime.value = audio.currentTime
    }
    // Paused, seeking or hidden: the frame clock is not running, so the slow
    // clock is what the bar shows.
    if (!frameLoop) frameTime.value = currentTime.value
    scheduleSessionSave()
    // Clip-loop wrap-around: if a region is active and the playhead has
    // crossed the end, jump back to the start. Used by the sync editor
    // so the user can re-stamp a single line without rewinding the song.
    const ls = clipLoopStart.value
    const le = clipLoopEnd.value
    if (ls != null && le != null && audio && currentTime.value >= le) {
      try {
        audio.currentTime = ls
      } catch {
        // ignore: some streams reject assignment briefly post-seek
      }
    }
    updateActiveLyric()
    maybeTransition()
  })
  on('loadedmetadata', () => {
    const track = currentTrack.value
    // Byte-range proxy streams now expose a real numeric duration via
    // Content-Length: use it directly. Only fall back to /api/stream/info
    // if for some reason the browser still reports Infinity/NaN (e.g.
    // the legacy ffmpeg path is in effect).
    if (track && track.type === 'stream') {
      if (isFinite(audio.duration) && audio.duration > 0) {
        duration.value = audio.duration
      } else if (!duration.value) {
        ensureStreamDuration(track)
      }
      return
    }
    if (isFinite(audio.duration) && audio.duration > 0) {
      duration.value = audio.duration
    } else {
      const track = currentTrack.value
      if (track && track.type === 'stream' && !duration.value) {
        ensureStreamDuration(track)
      }
    }
  })
  on('durationchange', () => {
    const track = currentTrack.value
    if (track && track.type === 'stream') return // length-less remux
    if (isFinite(audio.duration) && audio.duration > 0) {
      duration.value = audio.duration
    }
  })
  on('waiting', () => {
    isBuffering.value = true
  })
  on('playing', () => {
    isBuffering.value = false
    noteStarted()
  })
  on('canplay', () => {
    isBuffering.value = false
  })
  on('ended', onEnded)
  on('error', onPlaybackError)
  on('play', () => {
    isPlaying.value = true
    if (engine) engine.resume()
    syncMediaSession()
    startFrameClock()
  })
  on('pause', () => {
    isPlaying.value = false
    if (engine) engine.idleSoon()
    syncMediaSession()
    stopFrameClock()
  })
  on('seeked', () => {
    frameTime.value = elementTime()
    syncPositionState()
  })
  on('durationchange', syncPositionState)
  on('ratechange', syncPositionState)
  // Ended or failed without pausing: nothing to draw, so no loop either.
  on('ended', stopFrameClock)
  on('error', stopFrameClock)
  on('emptied', stopFrameClock)
  if (!visibilityHooked && typeof document !== 'undefined' && document.addEventListener) {
    visibilityHooked = true
    // A hidden window draws nothing; the loop stops and picks up on return.
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && audio && !audio.paused) startFrameClock()
    })
  }
  return el
}
