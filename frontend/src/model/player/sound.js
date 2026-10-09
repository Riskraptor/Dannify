import { ref } from 'vue'
import API from '/src/model/api'
import { audio, deck, engine } from '/src/model/player/decks'
import {
  currentTrack,
  duration,
  isMuted,
  readStored,
  storeSetting,
  videoIdOf,
  volume,
} from '/src/model/player/state'

// --- Per-track loudness normalization ---
//
// A YouTube mix puts a loud modern single next to a quiet album cut and the
// difference is jarring. YouTube publishes how far above its own target each
// track was mastered, so the fix is to turn the loud ones down.
//
// Loud tracks are turned down. Quiet ones are turned up too, by at most 6 dB,
// but only through the sound engine, whose limiter catches the peaks that
// lifting them would otherwise clip; without it, only down.
const TARGET_LUFS = -7 // YouTube Music's target, not the video site's -14
const MAX_ATTENUATION_DB = -24
const MAX_BOOST_DB = 6
export const trackGain = ref(1)
// A setting ("Even out loudness"): on unless it has been turned off.
const NORMALIZE_KEY = 'dannify-normalize'
export const normalizeLoudness = ref(readStored(NORMALIZE_KEY) !== '0')
// How loud the evened-out level is: quiet for a library or late at night,
// loud for a noisy room. The same three Spotify offers. Loud leans on the
// limiter for the peaks it would otherwise clip.
const LEVEL_KEY = 'dannify-level'
export const VOLUME_LEVELS = { quiet: -5, normal: 0, loud: 3 }
export const volumeLevel = ref(VOLUME_LEVELS[readStored(LEVEL_KEY)] !== undefined ? readStored(LEVEL_KEY) : 'normal')

function gainFor(loudnessDb) {
  if (typeof loudnessDb !== 'number' || !Number.isFinite(loudnessDb)) return 1
  const db = TARGET_LUFS + (VOLUME_LEVELS[volumeLevel.value] || 0) - (loudnessDb - 14)
  if (Math.abs(db) < 0.05) return 1
  if (db > 0) return engine ? Math.pow(10, Math.min(db, MAX_BOOST_DB) / 20) : 1
  return Math.pow(10, Math.max(db, MAX_ATTENUATION_DB) / 20)
}

// What each song measures, by video id, kept between runs. Each song used
// to start at full level and drop a moment later, when its measurement came
// back from the network: an audible jump at the start of almost every song.
// Known in advance (from here, or fetched while the song before it plays),
// the level is right from the first note.
const LOUDNESS_KEY = 'dannify-loudness'
const LOUDNESS_MAX = 4000
const loudnessCache = (() => {
  try {
    const raw = JSON.parse(readStored(LOUDNESS_KEY) || '{}')
    return new Map(Object.entries(raw && typeof raw === 'object' ? raw : {}))
  } catch {
    return new Map()
  }
})()
let loudnessSaveTimer = 0
function rememberLoudness(id, db) {
  if (!id || typeof db !== 'number' || !Number.isFinite(db)) return
  loudnessCache.delete(id)
  loudnessCache.set(id, db)
  while (loudnessCache.size > LOUDNESS_MAX) loudnessCache.delete(loudnessCache.keys().next().value)
  clearTimeout(loudnessSaveTimer)
  loudnessSaveTimer = setTimeout(() => {
    try {
      localStorage.setItem(LOUDNESS_KEY, JSON.stringify(Object.fromEntries(loudnessCache)))
    } catch {
      // storage full or blocked: measured again next time
    }
  }, 1500)
}
export function loudnessOf(track) {
  if (!track) return undefined
  if (typeof track.loudness === 'number') return track.loudness
  const id = videoIdOf(track)
  return id && loudnessCache.has(id) ? loudnessCache.get(id) : undefined
}
export function gainOfTrack(track) {
  return gainFor(loudnessOf(track))
}

// Everything that sets a level goes through here, so the user's volume, the
// mute and the per-track gain can never get out of step.
export function applyVolume(immediate = false) {
  if (!audio) return
  const gain = normalizeLoudness.value ? trackGain.value : 1
  if (engine) {
    engine.setVolume(isMuted.value ? 0 : volume.value)
    if (deck) deck.setNorm(gain, immediate ? 0.005 : 0.25)
    return
  }
  audio.volume = Math.max(0, Math.min(1, volume.value * gain))
}

export function setVolumeLevel(level) {
  if (VOLUME_LEVELS[level] === undefined) return
  volumeLevel.value = level
  storeSetting(LEVEL_KEY, level)
  // The playing song moves to the new level now, gently.
  const track = currentTrack.value
  if (track) {
    track.gain = gainOfTrack(track)
    trackGain.value = track.gain
  }
  applyVolume()
}

export function setNormalizeLoudness(on) {
  normalizeLoudness.value = !!on
  try {
    localStorage.setItem(NORMALIZE_KEY, on ? '1' : '0')
  } catch {
    // ignore
  }
  applyVolume()
}

// --- What the backend measured: a stream's length, a song's level ---
export async function ensureStreamDuration(track) {
  if (!track || track.type !== 'stream' || !track.video_id) return
  const haveDuration = track.duration > 0
  if (haveDuration) duration.value = track.duration
  // The gain is worth one more call even when the duration is known: the
  // backend answers this from the same cache entry it resolved the stream
  // from, so a warm track costs about a millisecond.
  if (haveDuration && loudnessOf(track) !== undefined) return
  try {
    const res = await API.getStreamInfo(track.video_id)
    const d = (res.data && res.data.duration) || 0
    if (d > 0) {
      track.duration = d
      // Only apply if this is still the current track.
      if (currentTrack.value === track) duration.value = d
    }
    noteLoudness(track, res.data && res.data.loudness_db)
  } catch {
    // ignore: duration stays 0 (live/unknown) and the volume stays untouched
  }
}

export function noteLoudness(track, db) {
  if (typeof db === 'number' && Number.isFinite(db)) {
    track.loudness = db
    rememberLoudness(videoIdOf(track), db)
  } else if (track.loudness === undefined) {
    track.loudness = null // asked, and there is none
  }
  track.gain = gainOfTrack(track)
  if (currentTrack.value === track) {
    trackGain.value = track.gain
    applyVolume()
  }
}

// A saved song's loudness, from the same place a stream's comes from. Only
// streams had it, so with "Even out loudness" on a mixed queue turned the
// streamed songs down and left the saved ones loud: the opposite of the point.
// Offline this fails quietly and the song plays at its own level.
export async function ensureLocalGain(track) {
  if (!track || track.type !== 'local' || !track.video_id || loudnessOf(track) !== undefined) return
  try {
    const res = await API.getStreamInfo(track.video_id)
    noteLoudness(track, res.data && res.data.loudness_db)
  } catch {
    // unity gain
  }
}

// Resolves once a song's loudness is known, or after *ms* regardless: a song
// is not held back for long by a slow network.
export function loudnessReady(track, pending, ms) {
  if (loudnessOf(track) !== undefined || !pending) return Promise.resolve()
  return Promise.race([pending.catch(() => {}), new Promise((r) => setTimeout(r, ms))])
}
