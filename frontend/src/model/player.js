import { ref, shallowRef, computed, watch } from 'vue'
import API from '/src/model/api'
import { useLibraryIndex } from '/src/model/libraryIndex'
import { useLibrary } from '/src/model/library'
import { useUi } from '/src/model/ui'
import { rememberPlayed } from '/src/model/recent'
import { notePlayed } from '/src/model/support'
import {
  reportNetworkFailure,
  useConnectivity,
  whenOnline,
} from '/src/model/connectivity'
import { toast } from '/src/model/toast'
import { repairFiles } from '/src/model/repair'
import { t } from '/src/i18n'
import { createEngine, EQ_PRESETS, EQ_BANDS } from '/src/model/audioEngine'

const connectivity = useConnectivity()

// The button on a "would not play" message for a saved track in the library.
// *force* is for a file the backend thinks is fine: it failed here all the
// same, and a fresh copy is still the fix.
function repairAction(file, force = false) {
  if (!file) return {}
  return {
    timeout: 9000,
    action: { label: t('repair.action'), run: () => repairFiles([file], { force }) },
  }
}

const _libraryIndex = useLibraryIndex()
const _ui = useUi()
// One-shot guard for the auto-open-lyrics-on-first-play affordance.
let _lyricsAutoOpened = false
// Prime the index on app boot: the data is small (one /api/library call)
// and being already loaded means the first time the user clicks a search
// result trackFromSong() returns a local file synchronously.
_libraryIndex.load()

const VOLUME_KEY = 'dannify-player-volume'

const playlist = ref([])
// Storage can refuse to be read (blocked, or a browser in private mode on
// the LAN), and a throw here, while the module loads, blanked the whole app.
function readStored(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

const currentIndex = ref(-1)
const isPlaying = ref(false)
const isBuffering = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const volume = ref(parseFloat(readStored(VOLUME_KEY) || '0.85'))

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
const trackGain = ref(1)
// A setting ("Even out loudness"): on unless it has been turned off.
const NORMALIZE_KEY = 'dannify-normalize'
const normalizeLoudness = ref(readStored(NORMALIZE_KEY) !== '0')
// How loud the evened-out level is: quiet for a library or late at night,
// loud for a noisy room. The same three Spotify offers. Loud leans on the
// limiter for the peaks it would otherwise clip.
const LEVEL_KEY = 'dannify-level'
export const VOLUME_LEVELS = { quiet: -5, normal: 0, loud: 3 }
const volumeLevel = ref(VOLUME_LEVELS[readStored(LEVEL_KEY)] !== undefined ? readStored(LEVEL_KEY) : 'normal')

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
function loudnessOf(track) {
  if (!track) return undefined
  if (typeof track.loudness === 'number') return track.loudness
  const id = videoIdOf(track)
  return id && loudnessCache.has(id) ? loudnessCache.get(id) : undefined
}
function gainOfTrack(track) {
  return gainFor(loudnessOf(track))
}

// Everything that sets a level goes through here, so the user's volume, the
// mute and the per-track gain can never get out of step.
function applyVolume(immediate = false) {
  if (!audio) return
  const gain = normalizeLoudness.value ? trackGain.value : 1
  if (engine) {
    engine.setVolume(isMuted.value ? 0 : volume.value)
    if (deck) deck.setNorm(gain, immediate ? 0.005 : 0.25)
    return
  }
  audio.volume = Math.max(0, Math.min(1, volume.value * gain))
}

// --- Crossfade, gapless, equalizer: the sound engine's settings ---
const CROSSFADE_KEY = 'dannify-crossfade'
const GAPLESS_KEY = 'dannify-gapless'
const EQ_KEY = 'dannify-eq'
const crossfade = ref(Math.max(0, Math.min(12, Number(readStored(CROSSFADE_KEY)) || 0)))
const gapless = ref(readStored(GAPLESS_KEY) !== '0')
const eq = ref(readEq())

function readEq() {
  try {
    const v = JSON.parse(readStored(EQ_KEY) || 'null')
    if (v && Array.isArray(v.gains) && v.gains.length === EQ_BANDS.length) {
      const preamp = typeof v.preamp === 'number' && Number.isFinite(v.preamp) ? v.preamp : 'auto'
      return { on: !!v.on, preset: String(v.preset || 'custom'), gains: v.gains.map((g) => Number(g) || 0), preamp }
    }
  } catch {
    // a damaged setting: start flat
  }
  return { on: false, preset: 'flat', gains: [...EQ_PRESETS.flat], preamp: 'auto' }
}
function storeSetting(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // blocked storage: the choice lasts this session
  }
}
function applyEq() {
  if (engine) engine.setEq(eq.value.on, eq.value.gains, eq.value.preamp === 'auto' ? null : eq.value.preamp)
}
function setEq(next) {
  eq.value = next
  storeSetting(EQ_KEY, JSON.stringify(next))
  applyEq()
}
function setEqEnabled(on) {
  setEq({ ...eq.value, on: !!on })
}
function setEqPreset(name) {
  const own = String(name).startsWith('user:') ? eqUserPresets.value.find((p) => 'user:' + p.name === name) : null
  const gains = own ? own.gains : EQ_PRESETS[name]
  if (!gains) return
  setEq({ ...eq.value, on: true, preset: name, gains: [...gains] })
}
function setEqBand(index, db) {
  if (index < 0 || index >= EQ_BANDS.length) return
  const gains = [...eq.value.gains]
  gains[index] = Math.max(-12, Math.min(12, Math.round(Number(db) * 2) / 2 || 0))
  setEq({ ...eq.value, on: true, preset: 'custom', gains })
}
/** 'auto' (half the biggest boost taken back) or dB, -12 to +12. */
function setEqPreamp(v) {
  const preamp = v === 'auto' ? 'auto' : Math.max(-12, Math.min(12, Math.round(Number(v) * 2) / 2 || 0))
  setEq({ ...eq.value, preamp })
}

// Equalizer settings of the listener's own, by name.
const EQ_USER_KEY = 'dannify-eq-user'
const EQ_USER_MAX = 12
const eqUserPresets = ref((() => {
  try {
    const v = JSON.parse(readStored(EQ_USER_KEY) || '[]')
    return Array.isArray(v)
      ? v.filter((p) => p && p.name && Array.isArray(p.gains) && p.gains.length === EQ_BANDS.length).slice(0, EQ_USER_MAX)
      : []
  } catch {
    return []
  }
})())
function saveEqPreset(name) {
  const clean = String(name || '').trim().slice(0, 40)
  if (!clean) return false
  const list = eqUserPresets.value.filter((p) => p.name !== clean)
  list.unshift({ name: clean, gains: [...eq.value.gains] })
  eqUserPresets.value = list.slice(0, EQ_USER_MAX)
  storeSetting(EQ_USER_KEY, JSON.stringify(eqUserPresets.value))
  setEq({ ...eq.value, preset: 'user:' + clean })
  return true
}
function deleteEqPreset(name) {
  eqUserPresets.value = eqUserPresets.value.filter((p) => p.name !== name)
  storeSetting(EQ_USER_KEY, JSON.stringify(eqUserPresets.value))
  if (eq.value.preset === 'user:' + name) setEq({ ...eq.value, preset: 'custom' })
}

// Listening speed, kept between runs, and whether the pitch stays put.
const SPEED_KEY = 'dannify-speed'
const PITCH_KEY = 'dannify-keep-pitch'
const speed = ref(Math.max(0.5, Math.min(2, Number(readStored(SPEED_KEY)) || 1)))
const keepPitch = ref(readStored(PITCH_KEY) !== '0')
function setSpeed(v) {
  speed.value = Math.max(0.5, Math.min(2, Math.round((Number(v) || 1) * 20) / 20))
  storeSetting(SPEED_KEY, String(speed.value))
  setPlaybackRate(speed.value)
}
function setKeepPitch(on) {
  keepPitch.value = !!on
  storeSetting(PITCH_KEY, on ? '1' : '0')
  if (audio) {
    try {
      audio.preservesPitch = keepPitch.value
    } catch {
      // not supported here
    }
  }
}
/** Back to the listener's own speed (after the lyrics editor's slow motion). */
function restoreSpeed() {
  setPlaybackRate(speed.value)
}
/** The output's spectrum into `out` (dB per bin); false without the engine. */
function spectrum(out) {
  return engine && typeof engine.spectrum === 'function' ? engine.spectrum(out) : false
}
function spectrumInfo() {
  return engine ? { bins: engine.bins || 0, sampleRate: engine.sampleRate || 48000 } : { bins: 0, sampleRate: 48000 }
}
function setCrossfade(seconds) {
  crossfade.value = Math.max(0, Math.min(12, Math.round(Number(seconds) || 0)))
  storeSetting(CROSSFADE_KEY, String(crossfade.value))
  cancelTransition()
}
function setGapless(on) {
  gapless.value = !!on
  storeSetting(GAPLESS_KEY, on ? '1' : '0')
  cancelTransition()
}

function setVolumeLevel(level) {
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

// Balance and mono (the sound engine's; see audioEngine.js).
const BALANCE_KEY = 'dannify-balance'
const MONO_KEY = 'dannify-mono'
const balance = ref(Math.max(-1, Math.min(1, Number(readStored(BALANCE_KEY)) || 0)))
const mono = ref(readStored(MONO_KEY) === '1')
function setBalance(v) {
  balance.value = Math.max(-1, Math.min(1, Math.round((Number(v) || 0) * 100) / 100))
  storeSetting(BALANCE_KEY, String(balance.value))
  if (engine) engine.setBalance(balance.value)
}
function setMono(on) {
  mono.value = !!on
  storeSetting(MONO_KEY, on ? '1' : '0')
  if (engine) engine.setMono(mono.value)
}
/** The equalizer's response at `freqs`, in dB, for drawing it. */
function eqCurve(freqs) {
  return engine && typeof engine.eqResponse === 'function' ? engine.eqResponse(freqs) : new Float32Array(freqs.length)
}

function setNormalizeLoudness(on) {
  normalizeLoudness.value = !!on
  try {
    localStorage.setItem(NORMALIZE_KEY, on ? '1' : '0')
  } catch {
    // ignore
  }
  applyVolume()
}
const isMuted = ref(false)
// Shuffle and repeat are a listening preference, not a per-session accident:
// someone who listens on shuffle expects to still be on shuffle tomorrow.
const REPEAT_KEY = 'dannify-repeat'
const SHUFFLE_KEY = 'dannify-shuffle'

function remembered(key, allowed, fallback) {
  try {
    const value = localStorage.getItem(key)
    if (value !== null && allowed.includes(value)) return value
  } catch {
    // Blocked storage: the default is fine.
  }
  return fallback
}

const repeatMode = ref(remembered(REPEAT_KEY, ['off', 'all', 'one'], 'off'))
const shuffle = ref(remembered(SHUFFLE_KEY, ['0', '1'], '0') === '1')
const playbackRate = ref(Math.max(0.5, Math.min(2, Number(readStored('dannify-speed')) || 1)))
// Autoplay: when the queue runs dry, keep going with YouTube Music's endless
// mix for the last track: the behaviour every streaming app has.
const AUTOPLAY_KEY = 'dannify-autoplay-radio'
const autoplayRadio = ref(readStored(AUTOPLAY_KEY) !== '0')
let radioSeed = ''

// Consecutive saved files that would not play, reset by the first that
// does. Stops one click walking a whole queue of dead tracks.
let deadRun = 0
// Streams already retried once after failing, so a second failure moves on.
const streamRetried = new WeakSet()
const DEAD_RUN_LIMIT = 3

// --- Session restore ---
//
// Closing a music player and reopening it to silence and an empty queue is
// the difference between an app and a web page. The queue, which track was
// playing and how far into it are kept, and the next launch comes back to
// exactly that, paused. Deliberately paused: starting audio on its own
// before the window has even finished drawing is startling, and there is a
// play button right there.
const SESSION_KEY = 'dannify.session.v1'
// Past this the queue is someone else's afternoon. Coming back to it would
// be surprising rather than helpful.
const SESSION_TTL_MS = 14 * 24 * 60 * 60 * 1000
// A queue longer than this is a whole playlist; storing all of it every few
// seconds is not worth the quota.
const SESSION_MAX_TRACKS = 200
let sessionTimer = null
let sessionRestored = false

function saveSession() {
  try {
    const list = playlist.value
    if (!list.length || currentIndex.value < 0) {
      localStorage.removeItem(SESSION_KEY)
      return
    }
    localStorage.setItem(
      SESSION_KEY,
      JSON.stringify({
        // A saved track keeps its path, not its URL. The URL names a file
        // that can be renamed between one run and the next, and converting
        // the library to containers renames all of them, so a queue written
        // before that came back pointing at files that no longer existed.
        // The path survives it; the URL is rebuilt on the way back in.
        tracks: list.slice(0, SESSION_MAX_TRACKS).map((t) =>
          t && t.type === 'local' && t.file ? { ...t, url: '', cover: '' } : t
        ),
        index: Math.min(currentIndex.value, SESSION_MAX_TRACKS - 1),
        time: Math.max(0, Math.floor(currentTime.value || 0)),
        ts: Date.now(),
      }),
    )
  } catch {
    // Quota or blocked storage: the session just will not come back.
  }
}

// Called from the time update, so it has to be cheap. Writes at most once
// every few seconds rather than four times a second.
function scheduleSessionSave() {
  if (sessionTimer) return
  sessionTimer = setTimeout(() => {
    sessionTimer = null
    saveSession()
  }, 4000)
}

function readSession() {
  try {
    const blob = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null')
    if (!blob || !Array.isArray(blob.tracks) || !blob.tracks.length) return null
    if (Date.now() - (blob.ts || 0) > SESSION_TTL_MS) return null
    const index = Number(blob.index)
    if (!Number.isInteger(index) || index < 0 || index >= blob.tracks.length) return null
    // Every url we store is relative, so a new port on the next launch does
    // not invalidate them. Anything absolute is from an older build.
    if (blob.tracks.some((t) => !t || typeof t.url !== 'string' || /^https?:/i.test(t.url))) {
      return null
    }
    // Rebuild the URL of every saved track from its path. Entries written by
    // an older build still carry the url the file had then, and that is the
    // one thing here that is allowed to be out of date.
    blob.tracks = blob.tracks.map((t) =>
      t && t.type === 'local' && t.file
        ? { ...t, url: API.downloadFileURL(t.file), cover: API.coverFileURL(t.file) }
        : t
    )
    return blob
  } catch {
    return null
  }
}

// Load the track the user left off on, cued to where they left it, without
// starting it.
function restoreSession() {
  if (sessionRestored) return false
  sessionRestored = true
  const blob = readSession()
  if (!blob) return false
  // A file opened from Explorer plays through a one-off address that dies
  // with the session it was made in. Restored, it was a dead link: the next
  // start came up on a track that could only fail. Those are left out.
  const opened = (tr) => String((tr && tr.url) || '').startsWith('/opened/')
  if (opened(blob.tracks[blob.index])) return false
  const tracks = blob.tracks.filter((tr) => !opened(tr))
  const index = tracks.indexOf(blob.tracks[blob.index])
  playlist.value = tracks
  currentIndex.value = index
  if (shuffle.value) buildShuffleOrder()
  const track = tracks[index]
  const at = Math.max(0, Number(blob.time) || 0)
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
  // Lyrics are fetched when a track starts playing, and a restored one has
  // not started: without this the panel said "No lyrics found" for the track
  // in the player on every launch, until something else was played.
  loadLyricsForCurrent()
  return true
}

if (typeof window !== 'undefined') {
  // The window can vanish without a clean shutdown (tray quit, a crash), so
  // the throttled save is backed up by one on the way out.
  window.addEventListener('beforeunload', saveSession)
  window.addEventListener('pagehide', saveSession)
}

// --- Clip-loop (used by the sync editor) ---
// When set, the audio loops between [clipLoopStart, clipLoopEnd]. Lets the
// editor focus on a single lyric line so the user can re-stamp it without
// rewinding the whole song.
const clipLoopStart = ref(null)
const clipLoopEnd = ref(null)
// When true, audio ``ended`` does NOT auto-advance to the next track.
// Used by the lyrics sync editor: when the user is mid-edit and the song
// reaches the end, just stop: don't load a new track and reset the
// editor's context.
const noAutoAdvance = ref(false)

// --- Synced lyrics state ---
const lyricsLines = ref([]) // [{ time, text }]
const lyricsPlain = ref(null)
const lyricsLoading = ref(false)
const activeLyricIndex = ref(-1)
// The playhead as the screen should draw it: read from the element every
// frame while playing. `timeupdate` only fires about four times a second, so
// the progress bar moved in visible steps and a lyric line could light up a
// quarter of a second late. Only the bar and the lyric highlight follow this;
// everything else stays on the slower clock and does not redraw every frame.
const frameTime = ref(0)
let frameLoop = 0

function elementTime() {
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
const lyricsOffset = ref(0) // seconds; positive = lyrics appear later
const lyricsMeta = ref({ title: '', artist: '' }) // for saving offsets
const lyricVersions = ref([]) // all synced versions [{synced, plain}]
const lyricVersionIndex = ref(0) // which version is showing
const lyricVersionCount = ref(0) // how many versions exist
let lyricsToken = 0

let audio = null
// The sound engine (see audioEngine.js), or null where there is none and the
// element's own volume does the work. *deck* is the one playing; the other
// waits, holds the next song ready, or fades out the last one.
let engine = null
let engineTried = false
let deck = null
const decks = []
// How long a song fades out when another is picked by hand, so a skip does
// not click. Automatic changes use the crossfade (or the gapless overlap).
const MANUAL_FADE = 0.25
const GAPLESS_OVERLAP = 0.12
// The shuffled play order: every queue index exactly once. What sits before
// the playing track in it has played, what sits after it is still to come.
// There is no separate position to keep in step: it is wherever the playing
// track is. A ref, so "Up next" follows it.
const shuffleOrder = shallowRef([])
// Monotonic token bumped on every track change; async work checks it so stale
// callbacks from a previous track are discarded (prevents wrong-song audio).
let playGen = 0
// For length-less remux streams: server starts output at this offset, so the
// element's currentTime is relative to it: we add it back for the UI clock.
let streamBaseOffset = 0

function ensureAudio() {
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
function otherDeck() {
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
function retire(d, seconds) {
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
function silenceRetiring() {
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
function cancelTransition() {
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
    deadRun = 0
  })
  on('canplay', () => {
    isBuffering.value = false
  })
  on('ended', onEnded)
  on('error', () => {
    const track = currentTrack.value
    if (!track) return
    isBuffering.value = false
    if (track.type !== 'stream') {
      // A saved file that will not play. This used to return here and do
      // nothing at all: no message, no skip, just a track sitting there that
      // was never going to start.
      //
      // Then it said so and skipped, which is right for one bad file and
      // wrong for a folder of them: skipping raises the next error, which
      // skips again, so one click walked the whole queue and stacked a toast
      // for every track in it. What looked like three failures was one, three
      // deep. So it stops after a few in a row, and says that instead.
      const err = audio.error
      console.error('[player] audio error', {
        code: err && err.code,
        message: err && err.message,
        networkState: audio.networkState,
        readyState: audio.readyState,
        src: audio.currentSrc,
      })
      // Why, first: the audio element cannot say (a 404 and a 409 both reach
      // it as MEDIA_ERR_SRC_NOT_SUPPORTED), so the server is asked. A file
      // that is simply not there any more is not a failure at all when the
      // song is on YouTube Music: it goes on from there, where it was.
      const src = audio.currentSrc
      const gen = playGen
      const at = currentTime.value
      fetch(src, { method: 'HEAD' })
        .then(
          (probe) => probe.status,
          () => 0
        )
        .then((status) => {
          if (gen !== playGen || currentTrack.value !== track) return
          const copy = status === 404 ? onlineCopyOf(track) : null
          if (copy) useOnlineCopy(currentIndex.value, copy, at)
          else savedTrackFailed(track, err, src, status)
        })
      return
    }
    const gen = playGen
    const at = currentTime.value
    // Wait for the verdict: the old code read "online" before the check
    // had run, so the first failure of a real outage never armed the
    // resume, and a failure while online just left the player sitting
    // there "playing" with no sound and a frozen bar.
    reportNetworkFailure().then((isOnline) => {
      if (gen !== playGen || currentTrack.value !== track) return
      if (!isOnline && track.savedCopyGone && hasNextInOrder()) {
        // Its saved copy has gone and there is no connection to play it
        // from. Waiting here would hold up every saved song after it.
        toast(t('player.notSavedOffline', { title: track.title || t('common.unknownTrack') }), {
          key: 'not-saved-offline',
        })
        next()
        return
      }
      if (!isOnline) {
        // Died because the network did: carry on when it is back.
        whenOnline(() => {
          if (gen !== playGen || currentTrack.value !== track) return
          playAt(currentIndex.value)
          if (at > 1) setTimeout(() => seek(at), 600)
        })
        return
      }
      // Online, so the stream itself failed. Once is often an expired
      // address that a fresh request replaces, so try again quietly.
      if (!streamRetried.has(track)) {
        streamRetried.add(track)
        playAt(currentIndex.value, { again: true })
        if (at > 1) setTimeout(() => seek(at), 600)
        return
      }
      isPlaying.value = false
      deadRun += 1
      if (deadRun >= DEAD_RUN_LIMIT) {
        toast(t('player.manyStreamsFailed'), { tone: 'error' })
        deadRun = 0
        return
      }
      toast(t('player.streamFailed'), { tone: 'error' })
      if (hasNextInOrder()) next()
    })
  })
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

// One implementation of the path encoding, in api.js. There were three, and
// this one encoded the whole path with encodeURIComponent, so the separators
// came out as %2F and a track in a subfolder asked for a file that was not
// there.
const fileUrl = (file) => API.downloadFileURL(file)
const coverUrl = (file) => API.coverFileURL(file)

// ---------------------------------------------------------------------------
// Saved songs that are not saved any more
// ---------------------------------------------------------------------------
// A song deleted from this computer (here, or in Explorer) is usually still
// on YouTube Music. The queue used to find out by trying: the song failed,
// a message said it "may have been moved or deleted", and it was skipped,
// though it would have played perfectly well online.

const _library = useLibrary()
const YT_VIDEO = /^[A-Za-z0-9_-]{11}$/

/** The YouTube Music copy of a saved song, or null when it has none. */
function onlineCopyOf(track) {
  const vid = track && track.video_id
  if (!vid || !YT_VIDEO.test(vid)) return null
  return {
    type: 'stream',
    file: null,
    song_id: vid,
    video_id: vid,
    spotify_url: '',
    url: API.streamURL(vid),
    // Its picture was in the file. YouTube Music's is asked for when the
    // song comes up (one request, not one per song in a long queue).
    cover: '',
    title: track.title || '',
    artist: track.artist || '',
    album: track.album || '',
    duration: track.duration || 0,
    savedCopyGone: true,
  }
}

function fillOnlineDetails(track) {
  API.resolveStream(`https://music.youtube.com/watch?v=${track.video_id}`)
    .then((res) => {
      const song = (res && res.data) || {}
      if (song.cover_url && !track.cover) track.cover = song.cover_url
      if (!track.duration && song.duration > 0) track.duration = song.duration
      if (currentTrack.value !== track) return
      syncMediaSession()
      // Its tile on Home now has the picture, in place of the saved
      // copy's, which went with the file.
      rememberPlayed(track)
    })
    .catch(() => {
      // Offline, or YouTube said no: the song plays without a picture.
    })
}

/** Put the online copy in a saved song's place and play it from *at*. */
function useOnlineCopy(index, copy, at = 0) {
  if (index < 0 || index >= playlist.value.length) return
  const list = [...playlist.value]
  list[index] = copy
  playlist.value = list
  playAt(index, { again: true })
  if (at > 1) setTimeout(() => seek(at), 600)
}

// A saved song that would not play, and has no online copy to go to.
function savedTrackFailed(track, err, src, status) {
  // Skipping raises the next error, which skips again, so one click on a
  // folder of bad files walked the whole queue and stacked a toast for each.
  // It stops after a few in a row, and says that instead.
  deadRun += 1
  if (deadRun >= DEAD_RUN_LIMIT) {
    toast(t('player.manyUnplayable'), { tone: 'error' })
    isPlaying.value = false
    deadRun = 0
    return
  }
  const title = track.title || t('common.unknownTrack')
  const index = currentIndex.value
  if (status === 404) {
    // Not there any more, and nowhere else to play it from: said once, and
    // out of the queue so it does not come round again.
    toast(t('player.fileGone', { title }), { key: `gone:${track.file}` })
    if (hasNextInOrder()) next()
    else isPlaying.value = false
    if (playlist.value[index] === track) removeFromQueue(index)
    return
  }
  // A 409 is the backend's answer for a container this installation has no
  // key for: the file is right there, so it is offered a repair rather than
  // a hint that it was moved. Named, so two broken songs are two messages,
  // each with its own Repair button.
  const kind = status === 409 || (err && err.code === 3) ? 'fileUnreadable' : 'fileUnplayable'
  const file = track.file && /\/downloads\//.test(src) ? track.file : ''
  toast(t(`player.${kind}`, { title }), {
    tone: 'error',
    ...(kind === 'fileUnreadable' ? repairAction(file, status !== 409) : {}),
  })
  if (hasNextInOrder()) next()
  else isPlaying.value = false
}

// Put the queue right whenever the library is read again (a download, a
// delete here, a file moved in Explorer, coming back to the window): a saved
// song whose file has gone plays from its new place if it was only moved,
// from YouTube Music if it is there, and otherwise leaves the queue, before
// it ever comes up. The playing song is left to finish what it has.
function settleMissingSaved() {
  if (!_library.loaded.value || _library.error.value) return
  const list = playlist.value
  if (!list.length) return
  const saved = new Set()
  const byVideo = new Map()
  for (const tr of _library.tracks.value) {
    if (!tr || !tr.file) continue
    saved.add(tr.file)
    if (tr.video_id && !tr.problem) byVideo.set(tr.video_id, tr.file)
  }
  let swapped = null
  const gone = []
  list.forEach((tr, i) => {
    if (!tr || tr.type !== 'local' || !tr.file || saved.has(tr.file)) return
    if (i === currentIndex.value) return
    const moved = tr.video_id && byVideo.get(tr.video_id)
    const replacement = moved
      ? { ...tr, file: moved, url: API.downloadFileURL(moved), cover: API.coverFileURL(moved) }
      : onlineCopyOf(tr)
    if (replacement) (swapped || (swapped = [...list]))[i] = replacement
    else gone.push(i)
  })
  if (swapped) playlist.value = swapped
  for (const i of gone.reverse()) removeFromQueue(i)
}
watch([() => _library.tracks.value, () => _library.loaded.value], settleMissingSaved)

function trackFromFile(file) {
  const noExt = file.replace(/\.[^.]+$/, '')
  let artist = ''
  let title = noExt
  const dash = noExt.indexOf(' - ')
  if (dash > 0) {
    artist = noExt.slice(0, dash).trim()
    title = noExt.slice(dash + 3).trim()
  }
  return {
    type: 'local',
    file,
    url: fileUrl(file),
    cover: coverUrl(file),
    title,
    artist,
  }
}

// Build a streaming track from a resolved/preview song dict.
//
// Two kinds of song dicts arrive here:
//  * YouTube-sourced (search / explorer): ``song_id`` is a real 11-char
//    YouTube videoId: we can stream it directly.
//  * Spotify-sourced (preview of a pasted link): ``song_id`` is a 22-char
//    Spotify track id with no YouTube match yet: we must stream by URL so
//    the backend resolves the matching YouTube video first.
function trackFromSong(song) {
  const artists = song.artists || []
  const spotifyUrl =
    song.url && song.url.includes('spotify') ? song.url : ''

  // A YouTube videoId is exactly 11 url-safe chars. Anything else (e.g. a
  // Spotify 22-char id) is NOT a playable video id.
  const isYtId = (v) =>
    typeof v === 'string' && /^[A-Za-z0-9_-]{11}$/.test(v)

  let videoId = ''
  if (isYtId(song.video_id)) videoId = song.video_id
  else if (song.source === 'youtube' && isYtId(song.song_id))
    videoId = song.song_id
  else if (!spotifyUrl && isYtId(song.song_id)) videoId = song.song_id

  // ---------------------------------------------------------------------
  // Local-first: if this song is already downloaded, ALWAYS play the
  // on-disk file. Zero ffmpeg, zero network, instant start, lyrics from
  // the local .lrc. The library index is pre-loaded on app boot and
  // refreshed whenever a download finishes (WS library_changed event).
  // ---------------------------------------------------------------------
  try {
    const localFile = _libraryIndex && _libraryIndex.localFileFor(song)
    if (localFile) {
      const stem = localFile.replace(/\.[^.]+$/, '')
      const slash = stem.lastIndexOf('/')
      const tail = slash >= 0 ? stem.slice(slash + 1) : stem
      const dash = tail.indexOf(' - ')
      const guessedArtist = dash > 0 ? tail.slice(0, dash) : ''
      const guessedTitle = dash > 0 ? tail.slice(dash + 3) : tail
      return {
        type: 'local',
        file: localFile,
        url: API.downloadFileURL(localFile),
        cover: API.coverFileURL(localFile),
        title: song.name || guessedTitle,
        artist:
          (Array.isArray(artists) ? artists.join(', ') : String(artists || '')) ||
          guessedArtist,
        album: song.album_name || '',
        duration: song.duration || 0,
        video_id: videoId,
        song_id: song.song_id || videoId,
        _song: song,
      }
    }
  } catch {
    // libraryIndex not yet imported: fall through to stream track.
  }

  // Stream URL: prefer a real videoId; otherwise hand the Spotify URL to the
  // backend (/api/stream?url=) which resolves + matches it to YouTube.
  let url
  if (videoId) url = API.streamURL(videoId)
  else if (spotifyUrl) url = API.streamURLFromLink(spotifyUrl)
  else url = API.streamURL(song.song_id || '') // last-ditch

  return {
    type: 'stream',
    file: null,
    song_id: song.song_id || videoId,
    video_id: videoId, // '' until resolved (Spotify case)
    spotify_url: spotifyUrl,
    url,
    cover: song.cover_url || '',
    title: song.name || '',
    artist: Array.isArray(artists) ? artists.join(', ') : String(artists || ''),
    album: song.album_name || '',
    duration: song.duration || 0,
    _song: song,
  }
}

// --- Synced lyrics ---
function _lyricsParams(track) {
  if (track.type === 'local' && track.file) {
    // Send the file AND what we know about the track. The backend used to
    // get only the filename, so an online lookup could only go on whatever
    // tags the download happened to write. When those are thin (a missing
    // artist is enough) the lookup was skipped entirely, which is why
    // lyrics published for a downloaded song never came back.
    return {
      file: track.file,
      title: track.title || '',
      artist: track.artist || '',
      album: track.album || '',
      duration: Math.round(track.duration || duration.value || 0),
    }
  }
  if (track.spotify_url) return { url: track.spotify_url }
  return {
    title: track.title,
    artist: track.artist,
    album: track.album || '',
    duration: Math.round(track.duration || duration.value || 0),
  }
}

async function loadLyricsForCurrent(forceRefresh = false) {
  const track = currentTrack.value
  lyricsLines.value = []
  lyricsPlain.value = null
  activeLyricIndex.value = -1
  lyricVersions.value = []
  lyricVersionIndex.value = 0
  lyricVersionCount.value = 0
  if (!track) return
  const token = ++lyricsToken
  lyricsLoading.value = true
  try {
    const params = _lyricsParams(track)
    if (forceRefresh) params.refresh = 1
    const res = await API.getLyrics(params)
    if (token !== lyricsToken) return // a newer track took over
    const data = res.data || {}
    lyricsLines.value = data.synced || []
    lyricsPlain.value = data.plain || null
    lyricsOffset.value = typeof data.offset === 'number' ? data.offset : 0
    lyricVersionIndex.value =
      typeof data.version === 'number' ? data.version : 0
    lyricVersionCount.value =
      typeof data.version_count === 'number' ? data.version_count : 0
    lyricsMeta.value = {
      title: data.title || track.title || '',
      artist:
        data.artist ||
        (Array.isArray(track.artists) && track.artists[0]) ||
        (track.artist || '').split(',')[0].trim() ||
        '',
    }
    updateActiveLyric()
  } catch {
    if (token === lyricsToken) {
      lyricsLines.value = []
      lyricsPlain.value = null
      lyricsOffset.value = 0
    }
  } finally {
    if (token === lyricsToken) lyricsLoading.value = false
  }
}

function updateActiveLyric(at) {
  const lines = lyricsLines.value
  if (!lines || lines.length === 0) {
    activeLyricIndex.value = -1
    return
  }
  // Apply the per-song offset: positive = lyrics appear later, so we compare
  // against (currentTime - offset).
  const now = typeof at === 'number' ? at : currentTime.value
  const tNow = now - lyricsOffset.value
  let idx = -1
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].time <= tNow + 0.25) idx = i
    else break
  }
  if (idx !== activeLyricIndex.value) activeLyricIndex.value = idx
}

function seekToLyric(index) {
  const lines = lyricsLines.value
  if (index < 0 || index >= lines.length) return
  // Honour the offset so clicking a line jumps to where it actually plays.
  seek(lines[index].time + lyricsOffset.value)
  if (!isPlaying.value) play()
}

// Manually re-fetch lyrics for the current track, bypassing all caches.
function refreshLyrics() {
  return loadLyricsForCurrent(true)
}

function sameSong(a, b) {
  const norm = (s) =>
    String(s || '')
      .toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, '')
  return !!norm(a) && norm(a) === norm(b)
}

// Someone just published lyrics for a song. If it's the one on screen, pull
// them in: indexing needs a beat, so give it a couple of tries
// rather than leaving the panel stubbornly empty.
async function onLyricsPublished(detail) {
  const track = currentTrack.value
  if (!track || !detail) return
  const title = track.title || ''
  const artist = (track.artist || '').split(',')[0].trim()
  if (!sameSong(detail.track, title)) return
  if (detail.artist && artist && !sameSong(detail.artist, artist)) return
  for (const wait of [0, 1500, 4000]) {
    if (wait) await new Promise((r) => setTimeout(r, wait))
    if (currentTrack.value !== track) return
    await loadLyricsForCurrent(true)
    if (lyricsLines.value.length || lyricsPlain.value) return
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('dannify:lyrics-published', (e) => onLyricsPublished(e.detail))
}

// Nudge the lyric sync live (seconds). Updates the active line immediately.
function adjustLyricsOffset(delta) {
  const next = Math.max(-30, Math.min(30, lyricsOffset.value + delta))
  lyricsOffset.value = Math.round(next * 10) / 10
  updateActiveLyric()
}

function resetLyricsOffset() {
  lyricsOffset.value = 0
  updateActiveLyric()
}

// Persist the current offset for this song so it's shared with future users.
function saveLyricsOffset() {
  const { title, artist } = lyricsMeta.value
  if (!title || !artist) return Promise.resolve()
  return API.saveLyricsOffset(
    title,
    artist,
    lyricsOffset.value,
    lyricVersionCount.value > 1 ? lyricVersionIndex.value : undefined
  ).catch(() => {})
}

// Cycle to the next synced lyric version (when there are several). Lazily
// fetches the full version list the first time it's needed.
async function switchLyricVersion(dir = 1) {
  const track = currentTrack.value
  if (!track) return
  // The version list is a round trip, and the track can change while it is
  // out. Nothing checked, so switching version and then skipping put the
  // previous song's lyrics on the new one, and left its version list behind
  // for the next switch to cycle through.
  const token = lyricsToken
  if (lyricVersions.value.length === 0) {
    // Load all versions on demand.
    let versions = []
    try {
      const res = await API.getLyricVersions(_lyricsParams(track))
      versions = (res.data && res.data.versions) || []
    } catch {
      versions = []
    }
    if (token !== lyricsToken || currentTrack.value !== track) return
    lyricVersions.value = versions
    if (lyricVersions.value.length === 0) return
  }
  const n = lyricVersions.value.length
  if (n <= 1) return
  lyricVersionIndex.value = (lyricVersionIndex.value + dir + n) % n
  const v = lyricVersions.value[lyricVersionIndex.value]
  lyricsLines.value = v.synced || []
  lyricsPlain.value = v.plain || null
  lyricVersionCount.value = n
  updateActiveLyric()
}

// --- Stream duration + prefetch (speed) ---
async function ensureStreamDuration(track) {
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

function noteLoudness(track, db) {
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
async function ensureLocalGain(track) {
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
function loudnessReady(track, pending, ms) {
  if (loudnessOf(track) !== undefined || !pending) return Promise.resolve()
  return Promise.race([pending.catch(() => {}), new Promise((r) => setTimeout(r, ms))])
}

// Warm the next stream's cache file (and lyrics) so advancing the queue is
// instant and lyrics are ready before the next track even starts.
let prefetchTimer = null
function prefetchNext() {
  clearTimeout(prefetchTimer)
  prefetchTimer = setTimeout(() => {
    // The track that plays next, which under shuffle is not the next row.
    const nxt = playlist.value[nextIndex()]
    if (!nxt || nxt === currentTrack.value) return
    if (nxt.type === 'stream' && nxt.video_id) {
      // prefetch=1 → server transcodes the next track to cache in background.
      // Its loudness comes with it, so it starts at the right level.
      API.getStreamInfo(nxt.video_id, 1)
        .then((res) => {
          const data = (res && res.data) || {}
          if (data.duration > 0 && !(nxt.duration > 0)) nxt.duration = data.duration
          noteLoudness(nxt, data.loudness_db)
        })
        .catch(() => {})
    } else if (nxt.type === 'local') {
      ensureLocalGain(nxt)
    }
    prefetchLyrics(nxt)
  }, 500)
}

function prefetchLyrics(track) {
  if (!track) return
  let params
  if (track.type === 'local' && track.file) params = { file: track.file }
  else if (track.spotify_url) params = { url: track.spotify_url }
  else if (track.title) {
    params = {
      title: track.title,
      artist: track.artist || '',
      album: track.album || '',
      duration: Math.round(track.duration || 0),
    }
  }
  if (params) API.getLyrics(params).catch(() => {})
}

// --- Media Session (OS / lock-screen controls) ---
function syncMediaSession() {
  if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) {
    return
  }
  const track = currentTrack.value
  if (!track) return
  try {
    navigator.mediaSession.metadata = new window.MediaMetadata({
      title: track.title || '',
      artist: track.artist || '',
      album: track.album || '',
      // Windows needs an absolute url for the artwork; a relative one
      // resolves to nothing and the flyout shows an empty square.
      artwork: track.cover
        ? [
            {
              src: new URL(track.cover, window.location.href).href,
              sizes: '512x512',
              type: 'image/jpeg',
            },
          ]
        : [],
    })
    navigator.mediaSession.playbackState = isPlaying.value
      ? 'playing'
      : 'paused'
    navigator.mediaSession.setActionHandler('play', () => mediaCommand('play'))
    navigator.mediaSession.setActionHandler('pause', () => mediaCommand('pause'))
    navigator.mediaSession.setActionHandler('previoustrack', () =>
      mediaCommand('prev')
    )
    navigator.mediaSession.setActionHandler('nexttrack', () =>
      mediaCommand('next')
    )
    navigator.mediaSession.setActionHandler('seekto', (d) => {
      if (d.seekTime != null) seek(d.seekTime)
    })
    navigator.mediaSession.setActionHandler('seekbackward', (d) => seek(elementTime() - ((d && d.seekOffset) || 10)))
    navigator.mediaSession.setActionHandler('seekforward', (d) => seek(elementTime() + ((d && d.seekOffset) || 10)))
    navigator.mediaSession.setActionHandler('stop', () => pause())
  } catch {
    // MediaSession not fully supported: ignore.
  }
  syncPositionState()
}

// Where the song is and how long it is, for the timeline in Windows' media
// flyout. It had none: the flyout showed the title with no progress at all.
function syncPositionState() {
  try {
    const d = duration.value
    if (typeof navigator === 'undefined' || !navigator.mediaSession) return
    if (typeof navigator.mediaSession.setPositionState !== 'function') return
    if (!(d > 0) || !Number.isFinite(d)) return
    navigator.mediaSession.setPositionState({
      duration: d,
      playbackRate: (audio && audio.playbackRate) || 1,
      position: Math.max(0, Math.min(d, elementTime())),
    })
  } catch {
    // a position the browser will not take: the flyout just has no timeline
  }
}

function shuffled(indices) {
  for (let i = indices.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[indices[i], indices[j]] = [indices[j], indices[i]]
  }
  return indices
}

// A fresh shuffle, for a new queue or shuffle just switched on: *first* (the
// track playing, or about to) leads and everything else follows in random
// order. It used to be shuffled in with the rest, which only worked because
// the order never ended: whatever landed ahead of it played on the way round.
// Now that repeat off ends the order, that would never have played at all.
function buildShuffleOrder(first = currentIndex.value) {
  const n = playlist.value.length
  const rest = []
  for (let i = 0; i < n; i++) if (i !== first) rest.push(i)
  shuffled(rest)
  shuffleOrder.value = first >= 0 && first < n ? [first, ...rest] : rest
}

// Every queue edit keeps the order in step itself. This only catches a
// queue that changed some other way, and it has to run before the edit.
function ensureShuffleOrder() {
  if (shuffleOrder.value.length !== playlist.value.length) buildShuffleOrder()
}

// Where the playing track sits in the shuffled order; -1 with nothing
// loaded, which leaves the whole order still to come.
function shufflePosition() {
  return currentIndex.value >= 0 ? shuffleOrder.value.indexOf(currentIndex.value) : -1
}

// Queue edits under shuffle. Each of these used to throw the order away and
// deal a new one: "Play next" landed anywhere, a track that had already
// played could come round again, and Previous went somewhere random. They now
// change only what the edit touches.
//
// *count* tracks were inserted into the queue at *at*: shift the indices at
// and after it, and put the new ones straight after the playing track
// ("Play next") or at the end of the order ("Add to queue"), or, for a batch
// the listener did not pick one by one (a radio station), at the end in
// random order. Returns the new indices in the order they will play.
function addToShuffleOrder(at, count, { next = false, mix = false } = {}) {
  ensureShuffleOrder()
  const added = []
  for (let k = 0; k < count; k++) added.push(at + k)
  if (mix) shuffled(added)
  const order = shuffleOrder.value.map((i) => (i >= at ? i + count : i))
  const where = next ? shufflePosition() + 1 : order.length
  // Not splice(where, 0, ...added): that passes every index as an argument
  // and runs out of stack when a whole big library is queued.
  shuffleOrder.value = [...order.slice(0, where), ...added, ...order.slice(where)]
  return added
}

// The track at *index* is leaving the queue.
function dropFromShuffleOrder(index) {
  ensureShuffleOrder()
  shuffleOrder.value = shuffleOrder.value
    .filter((i) => i !== index)
    .map((i) => (i > index ? i - 1 : i))
}

function setPlaylist(files, options = {}) {
  const tracks = (files || []).map((f) => {
    if (typeof f === 'string') return trackFromFile(f)
    if (f && (f.song_id || f.video_id) && !f.url) return trackFromSong(f)
    if (f && f.name && (f.artists || f.album_name) && !f.title) {
      return trackFromSong(f)
    }
    return f
  })
  playlist.value = tracks
  if (currentIndex.value >= tracks.length) currentIndex.value = -1
  let start = null
  if (typeof options.startIndex === 'number') {
    start = options.startIndex
  } else if (options.autoplay && tracks.length > 0 && currentIndex.value < 0) {
    start = 0
  }
  // The track it starts on leads the new shuffle.
  if (shuffle.value) buildShuffleOrder(start != null ? start : currentIndex.value)
  if (start != null) playAt(start)
}

// A saved track opened from outside the app: double-clicked in Explorer, or
// passed on the command line. The shell has already worked out how to reach
// it, so this is a finished track and there is nothing to look up.
window.addEventListener('dannify:play-file', (e) => {
  const track = e && e.detail
  if (!track) return
  if (track.error) {
    toast(t('player.fileCantPlay', { name: track.name || '' }), {
      tone: 'error',
      // Only a track in the library can be repaired: it is put back where it
      // was, and a file from anywhere else has no place in it to go back to.
      ...repairAction(track.file || ''),
    })
    return
  }
  if (!track.url) return
  setPlaylist([track], { startIndex: 0 })
})

// Queue a list of streamable songs (from preview/search) and start playing.
function playStreamSongs(songs, startIndex = 0) {
  setPlaylist(songs.map(trackFromSong), { startIndex })
}

// Trigger a real download for a streamed track (so the user can keep it).
function downloadTrack(track) {
  const song = (track && track._song) || null
  if (!song) return Promise.resolve()
  return API.download(song).catch(() => {})
}

function toTrack(item) {
  if (typeof item === 'string') return trackFromFile(item)
  if (item && item.url && (item.type === 'local' || item.type === 'stream')) {
    return item
  }
  return trackFromSong(item)
}

// Insert tracks right after the current one ("Play next") or at the end of
// the queue ("Add to queue"). Accepts track objects, song dicts or file
// paths. Starts playback when nothing is loaded yet.
function enqueue(items, { next: asNext = false } = {}) {
  const tracks = (Array.isArray(items) ? items : [items])
    .filter(Boolean)
    .map(toTrack)
  if (!tracks.length) return
  const before = playlist.value
  const afterCurrent = asNext && currentIndex.value >= 0
  const at = afterCurrent ? currentIndex.value + 1 : before.length
  if (shuffle.value) addToShuffleOrder(at, tracks.length, { next: afterCurrent })
  playlist.value = [...before.slice(0, at), ...tracks, ...before.slice(at)]
  if (currentIndex.value < 0) playAt(at)
}

function enqueueNext(song) {
  enqueue([song], { next: true })
}

// Remove one entry from the queue without interrupting playback.
function removeFromQueue(index) {
  if (index < 0 || index >= playlist.value.length) return
  if (index === currentIndex.value) {
    // Removing the playing track: whatever Next would have played takes its
    // place, in the play order, so under shuffle too. It used to be the next
    // row, always started, even on a paused player; and removing the last
    // track went back to the one before it and started that.
    let succ = nextIndex()
    if (succ === index) succ = -1 // a queue of one, under repeat all
    const wasPlaying = isPlaying.value
    const list = [...playlist.value]
    list.splice(index, 1)
    if (shuffle.value) dropFromShuffleOrder(index)
    playlist.value = list
    if (succ < 0) {
      // Nothing after it: the queue is over, as it would be at the end.
      currentIndex.value = -1
      pause()
      return
    }
    playAt(succ > index ? succ - 1 : succ, { autoplay: wasPlaying })
    return
  }
  const list = [...playlist.value]
  list.splice(index, 1)
  if (shuffle.value) dropFromShuffleOrder(index)
  playlist.value = list
  if (index < currentIndex.value) currentIndex.value -= 1
}

// Drop everything that would play after the playing track. Under shuffle
// that is the rest of the shuffled order, not the rows below it: clearing by
// row kept tracks that were still to come, and they played anyway.
function clearUpcoming() {
  if (currentIndex.value < 0) {
    playlist.value = []
    shuffleOrder.value = []
    return
  }
  if (!shuffle.value) {
    playlist.value = playlist.value.slice(0, currentIndex.value + 1)
    return
  }
  ensureShuffleOrder()
  // What has played, and the playing track, in the order they played.
  const kept = shuffleOrder.value.slice(0, shufflePosition() + 1)
  const rows = [...kept].sort((a, b) => a - b)
  const moved = new Map(rows.map((old, i) => [old, i]))
  const list = playlist.value
  playlist.value = rows.map((i) => list[i])
  shuffleOrder.value = kept.map((i) => moved.get(i))
  currentIndex.value = moved.get(currentIndex.value)
}

// Where the row at *i* ends up once the row at *from* moves to *to*.
function movedIndex(i, from, to) {
  if (i === from) return to
  if (from < i && i <= to) return i - 1
  if (to <= i && i < from) return i + 1
  return i
}

function moveInQueue(from, to) {
  const list = [...playlist.value]
  if (from < 0 || from >= list.length || to < 0 || to >= list.length) return
  const [item] = list.splice(from, 1)
  list.splice(to, 0, item)
  // Under shuffle, moving a row does not change when the track plays.
  if (shuffle.value) {
    ensureShuffleOrder()
    shuffleOrder.value = shuffleOrder.value.map((i) => movedIndex(i, from, to))
  }
  currentIndex.value = movedIndex(currentIndex.value, from, to)
  playlist.value = list
}

/**
 * Move a song in "Up next" (dragged in the queue). `from` and `to` are places
 * in the order the songs will play, which under shuffle is not the list's.
 */
function moveUpcoming(from, to) {
  const up = upcoming.value
  if (from === to || from < 0 || to < 0 || from >= up.length || to >= up.length) return
  if (shuffle.value && shuffleOrder.value.length === playlist.value.length) {
    const order = [...shuffleOrder.value]
    const base = order.indexOf(currentIndex.value) + 1
    const [item] = order.splice(base + from, 1)
    order.splice(base + to, 0, item)
    shuffleOrder.value = order
    return
  }
  moveInQueue(up[from], up[to])
}

// Media keys can reach us twice (OS media session + keydown while focused).
// Collapse identical commands that land within a few hundred milliseconds.
let _lastMedia = { cmd: '', at: 0 }
function mediaCommand(cmd) {
  const now = performance.now()
  if (_lastMedia.cmd === cmd && now - _lastMedia.at < 350) return
  _lastMedia = { cmd, at: now }
  if (cmd === 'play') play()
  else if (cmd === 'pause') pause()
  else if (cmd === 'toggle') toggle()
  else if (cmd === 'next') next()
  else if (cmd === 'prev') prev()
}

// *autoplay* false loads the track and leaves it paused, for a change of
// track the listener did not ask to hear (removing the playing one while
// paused).
// *again*: the same song started over (a retry, its online copy taking over
// from a saved file that went), which is not another listen to record.
function playAt(index, { autoplay = true, fade = null, again = false } = {}) {
  if (index < 0 || index >= playlist.value.length) return
  ensureAudio()
  cancelTransition()
  const track = playlist.value[index]
  // With the engine, the next song goes on the other deck: the one that was
  // playing fades out by itself (briefly when picked by hand, over the
  // crossfade when it ran out), so a change never cuts or clicks.
  let preloaded = false
  if (engine && deck) {
    const incoming = otherDeck()
    if (incoming) {
      const outgoing = deck
      const playing = !!(outgoing.el.src && !outgoing.el.paused)
      retire(outgoing, fade != null ? fade : playing ? MANUAL_FADE : 0)
      preloaded = incoming.preloaded === track && !!incoming.el.src
      incoming.preloaded = null
      deck = incoming
      audio = incoming.el
      deck.setFade(fade != null && fade > GAPLESS_OVERLAP ? 0 : 1)
    }
  }
  const a = audio
  currentIndex.value = index
  if (shuffle.value) ensureShuffleOrder()
  // Bump the generation token so any in-flight async work (duration/lyrics
  // fetches, the previous stream's media events) from the prior track is
  // ignored: this prevents "wrong audio / wrong metadata" races when the
  // user switches tracks quickly.
  playGen += 1
  // Nothing buffers until it is asked to play.
  isBuffering.value = autoplay && track.type === 'stream'
  streamBaseOffset = 0
  // Point the element at the new track and let it do the rest. This used to
  // clear the src and call load() first, on the theory that the old buffer
  // needed flushing. Assigning a new src already discards it, and the
  // teardown had a cost: with no source the browser drops its media session,
  // so Windows tore the now-playing flyout down and rebuilt it on every
  // skip. That is the blink.
  try {
    a.pause()
  } catch {
    // ignore
  }
  if (!preloaded) {
    a.src = track.url
    a.currentTime = 0
  }
  // Re-apply playback rate: browsers reset it to 1.0 on src change.
  try {
    a.playbackRate = playbackRate.value
    a.preservesPitch = keepPitch.value
  } catch {
    // ignore
  }
  currentTime.value = 0
  frameTime.value = 0
  duration.value = track.duration || 0
  // Reset lyrics immediately so the old song's lyrics don't linger.
  lyricsLines.value = []
  lyricsPlain.value = null
  activeLyricIndex.value = -1
  // The song's level before its first note (see loudnessCache).
  trackGain.value = gainOfTrack(track)
  track.gain = trackGain.value
  applyVolume(true)
  const info = track.type === 'stream' ? ensureStreamDuration(track) : ensureLocalGain(track)
  if (autoplay) {
    const gen = playGen
    const d = deck
    const begin = () => {
      if (gen !== playGen) return
      trackGain.value = gainOfTrack(track)
      applyVolume(true)
      if (engine) engine.resume()
      a.play().catch(() => {})
      if (d && fade != null && fade > GAPLESS_OVERLAP) d.fadeTo(1, fade)
    }
    // Waiting on the measurement only when it changes something: levelling
    // on, a song YouTube measures, and nothing known about it yet.
    if (normalizeLoudness.value && videoIdOf(track) && loudnessOf(track) === undefined) {
      loudnessReady(track, info, 700).then(begin)
    } else {
      begin()
    }
  }
  loadLyricsForCurrent()
  syncMediaSession()
  if (track.savedCopyGone && !track.cover) fillOnlineDetails(track)
  if (!again) {
    rememberPlayed(track)
    notePlayed()
    // For whoever keeps a history of listens (the YouTube Music account).
    if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      window.dispatchEvent(new CustomEvent('dannify:played', { detail: track }))
    }
  }
  saveSession()
  // First-play affordance: surface the lyrics panel the very first time
  // the user plays something this session, so they see the headline
  // feature immediately. After that, respect whatever panel state they
  // chose: closing the panel mid-session won't be undone by the next
  // track change. Never pop it over the content on small windows.
  if (
    !_lyricsAutoOpened &&
    _ui.autoOpenLyrics.value &&
    _ui.panel.value == null &&
    !_ui.panelFloating.value
  ) {
    _ui.openPanel('lyrics')
  }
  _lyricsAutoOpened = true
  // Warm the next track (stream cache + lyrics) regardless of type.
  prefetchNext()
}

function play() {
  if (playlist.value.length === 0) return
  const a = ensureAudio()
  if (currentIndex.value < 0) {
    // The head of the play order: the first row, or under shuffle the first
    // of the shuffled order, which is what "Up next" shows.
    playAt(Math.max(0, nextIndex()))
    return
  }
  if (!a.src) {
    a.src = playlist.value[currentIndex.value].url
  }
  // Playing again while the sleep timer fades out means "not yet".
  if (sleepFading) cancelSleep()
  if (engine) engine.resume()
  a.play().catch(() => {})
}

function pause() {
  if (audio) audio.pause()
  cancelTransition()
  silenceRetiring()
}

function toggle() {
  if (isPlaying.value) pause()
  else play()
}

function seek(seconds) {
  const a = ensureAudio()
  // Clamp to the end only once the end is known. A stream still waiting on
  // its length reports 0, and clamping to that sent every seek (+10 s
  // included) back to the start of the song.
  const d = duration.value
  const max = Number.isFinite(d) && d > 0 ? d : Infinity
  const clamped = Math.max(0, Math.min(max, seconds))
  // For BOTH local files AND streams: just move the playhead.
  // The byte-range proxy lets the browser request the right offset
  // natively (``Range: bytes=N-``) so streams seek just like local files.
  try {
    a.currentTime = clamped
  } catch {
    // Some browsers reject the assignment on a length-less <audio>
    // element. As a last resort, fall through to the legacy server-side
    // seek path that re-spawns ffmpeg with -ss.
    const track = currentTrack.value
    if (track && track.type === 'stream') {
      streamBaseOffset = clamped
      const base =
        track.video_id && /^[A-Za-z0-9_-]{11}$/.test(track.video_id)
          ? API.streamURL(track.video_id)
          : track.url.split('&t=')[0]
      a.src = `${base}${base.includes('?') ? '&' : '?'}t=${Math.floor(clamped)}&force_mp3=1`
      isBuffering.value = true
      a.play().catch(() => {})
    }
  }
  currentTime.value = clamped
  frameTime.value = clamped
  // A change near the end was planned from the old position.
  cancelTransition()
  syncPositionState()
}

function seekRatio(ratio) {
  if (!duration.value) return
  seek(duration.value * Math.max(0, Math.min(1, ratio)))
}

// ─── Playback rate (used by the sync editor for slow-mo syncing) ───
function setPlaybackRate(rate) {
  const clamped = Math.max(0.25, Math.min(2.5, Number(rate) || 1.0))
  playbackRate.value = clamped
  if (audio) {
    try {
      audio.playbackRate = clamped
    } catch {
      // ignore: some browsers refuse rates outside [0.5, 2.0]
    }
  }
}

// ─── Clip-loop helpers ───
// Loop the audio between [start, end]. The sync editor wraps a single
// lyric line so the user can re-stamp it without rewinding. Pass null
// to either bound (or call clipUnloop) to disable.
function clipLoop(start, end) {
  const s = Math.max(0, Number(start) || 0)
  const e = Math.max(s + 0.2, Number(end) || s + 0.2)
  clipLoopStart.value = s
  clipLoopEnd.value = e
  // Jump the playhead in immediately so the user hears the loop start.
  seek(s)
  if (!isPlaying.value) play()
}

function clipUnloop() {
  clipLoopStart.value = null
  clipLoopEnd.value = null
}

function setVolume(v) {
  const clamped = Math.max(0, Math.min(1, v))
  volume.value = clamped
  applyVolume()
  try {
    localStorage.setItem(VOLUME_KEY, String(clamped))
  } catch {
    // ignore
  }
  if (clamped > 0 && isMuted.value) {
    isMuted.value = false
    if (audio && !engine) audio.muted = false
    applyVolume()
  }
}

function toggleMute() {
  isMuted.value = !isMuted.value
  if (engine) applyVolume()
  else if (audio) audio.muted = isMuted.value
}

// --- Sleep timer ---
//
// After a time, or at the end of this song. On a time, the last ten seconds
// fade out rather than cut, the way someone turning it down would.
const sleepMode = ref('off') // off | time | track
const sleepEndsAt = ref(0)
const SLEEP_FADE_S = 10
let sleepTimer = 0
let sleepFading = false

function setSleepTimer(minutes) {
  cancelSleep()
  const ms = Math.max(1, Number(minutes) || 0) * 60000
  sleepMode.value = 'time'
  sleepEndsAt.value = Date.now() + ms
  sleepTimer = setTimeout(sleepFadeOut, Math.max(0, ms - SLEEP_FADE_S * 1000))
}

function setSleepAfterTrack() {
  cancelSleep()
  sleepMode.value = 'track'
  cancelTransition()
}

function sleepFadeOut() {
  if (!isPlaying.value) {
    cancelSleep()
    return
  }
  sleepFading = true
  if (engine) engine.rampVolume(0, SLEEP_FADE_S)
  else if (audio) {
    const from = audio.volume
    const steps = 20
    for (let k = 1; k <= steps; k++) {
      setTimeout(() => {
        if (sleepFading && audio) audio.volume = from * (1 - k / steps)
      }, (SLEEP_FADE_S * 1000 * k) / steps)
    }
  }
  sleepTimer = setTimeout(() => {
    pause()
    cancelSleep()
  }, SLEEP_FADE_S * 1000)
}

function cancelSleep() {
  clearTimeout(sleepTimer)
  sleepTimer = 0
  const wasFading = sleepFading
  sleepFading = false
  sleepMode.value = 'off'
  sleepEndsAt.value = 0
  if (wasFading) applyVolume()
}

// Under shuffle the shuffled order ends the way the list does. It used to
// wrap round whatever the repeat setting, so with repeat off a shuffled queue
// never ended, and autoplay radio never got its turn.
function nextIndex() {
  if (playlist.value.length === 0) return -1
  if (shuffle.value) {
    ensureShuffleOrder()
    const order = shuffleOrder.value
    const nextPos = shufflePosition() + 1
    if (nextPos >= order.length) {
      return repeatMode.value === 'all' ? order[0] : -1
    }
    return order[nextPos]
  }
  const i = currentIndex.value + 1
  if (i >= playlist.value.length) {
    return repeatMode.value === 'all' ? 0 : -1
  }
  return i
}

// Whether anything follows the current track in the play order, not counting
// a wrap-around. A track that will not play moves on only while this holds;
// it used to ask whether a row followed it, which under shuffle is a
// different question.
function hasNextInOrder() {
  if (shuffle.value) {
    ensureShuffleOrder()
    return shufflePosition() < shuffleOrder.value.length - 1
  }
  return currentIndex.value < playlist.value.length - 1
}

function prevIndex() {
  if (playlist.value.length === 0) return -1
  if (shuffle.value) {
    ensureShuffleOrder()
    const order = shuffleOrder.value
    const prevPos = shufflePosition() - 1
    if (prevPos < 0) {
      return repeatMode.value === 'all' ? order[order.length - 1] : order[0]
    }
    return order[prevPos]
  }
  const i = currentIndex.value - 1
  if (i < 0) {
    return repeatMode.value === 'all' ? playlist.value.length - 1 : 0
  }
  return i
}

const YT_ID = /^[A-Za-z0-9_-]{11}$/

function videoIdOf(track) {
  const id = track && (track.video_id || track.song_id)
  return typeof id === 'string' && YT_ID.test(id) ? id : ''
}

function setAutoplayRadio(on) {
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
async function extendWithRadio() {
  if (!autoplayRadio.value) return false
  const id = videoIdOf(currentTrack.value)
  if (!id || radioSeed === id) return false
  radioSeed = id
  const gen = playGen
  try {
    const res = await API.getRadio(id)
    const songs = (res.data && res.data.songs) || []
    if (!songs.length || gen !== playGen) return gen !== playGen
    const at = playlist.value.length
    const added = shuffle.value ? addToShuffleOrder(at, songs.length, { mix: true }) : null
    playlist.value = [...playlist.value, ...songs.map(trackFromSong)]
    playAt(added ? added[0] : at)
    return true
  } catch {
    return false
  }
}

/** Replace the queue with a station built around one song. */
async function startRadio(song) {
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

function next() {
  const i = nextIndex()
  if (i < 0) {
    const gen = playGen
    extendWithRadio().then((extended) => {
      // Only stop if nothing else took over while the station loaded.
      if (!extended && gen === playGen) pause()
    })
    return
  }
  playAt(i)
}

function prev() {
  ensureAudio()
  // Where the song really is: on the fallback stream the element counts from
  // where that stream started, not from the top of the song.
  if (elementTime() > 3) {
    seek(0)
    return
  }
  const i = prevIndex()
  if (i < 0) return
  playAt(i)
}

function onEnded() {
  // "Stop after this song": it has ended, so stop here.
  if (sleepMode.value === 'track') {
    cancelSleep()
    isPlaying.value = false
    return
  }
  if (repeatMode.value === 'one') {
    seek(0)
    if (audio) audio.play().catch(() => {})
    return
  }
  // The lyrics sync editor sets this flag: when on, just stop at the
  // end instead of yanking the user to the next song mid-sync.
  if (noAutoAdvance.value) {
    return
  }
  next()
}

function setRepeat(mode) {
  if (!['off', 'all', 'one'].includes(mode)) return
  repeatMode.value = mode
  try {
    localStorage.setItem(REPEAT_KEY, mode)
  } catch {
    // The choice just will not survive a restart.
  }
}

function cycleRepeat() {
  const order = ['off', 'all', 'one']
  const i = order.indexOf(repeatMode.value)
  setRepeat(order[(i + 1) % order.length])
}

function setShuffle(v) {
  const was = shuffle.value
  shuffle.value = !!v
  // Only switching it on deals a new order; saying "on" again keeps the one
  // in play.
  if (shuffle.value && !was) buildShuffleOrder()
  try {
    localStorage.setItem(SHUFFLE_KEY, shuffle.value ? '1' : '0')
  } catch {
    // As above.
  }
}

function toggleShuffle() {
  setShuffle(!shuffle.value)
}

const currentTrack = computed(() =>
  currentIndex.value >= 0 && currentIndex.value < playlist.value.length
    ? playlist.value[currentIndex.value]
    : null
)

// The queue indices still to play after the current track, in the order they
// will play: the rest of the shuffled order under shuffle, the rows below
// otherwise. "Up next" used to list the rows below even with shuffle on, so
// the panel showed one thing and the player then played another.
const upcoming = computed(() => {
  const list = playlist.value
  const cur = currentIndex.value
  if (shuffle.value) {
    const order = shuffleOrder.value
    // Out of step only until the next move rebuilds it; the rows are the
    // best guess until then.
    if (order.length === list.length) {
      return order.slice((cur >= 0 ? order.indexOf(cur) : -1) + 1)
    }
  }
  const out = []
  for (let i = Math.max(0, cur + 1); i < list.length; i++) out.push(i)
  return out
})

// Drawn from the frame clock, so the bar glides instead of stepping.
const progressPct = computed(() =>
  duration.value > 0 ? Math.min(100, (frameTime.value / duration.value) * 100) : 0
)

// --- Global keyboard shortcuts (installed once) ---
let keyboardInstalled = false
function isTypingTarget(el) {
  if (!el) return false
  const tag = el.tagName
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    el.isContentEditable
  )
}

// Space is how a keyboard presses whatever has focus: a button, a link, a
// checkbox, a switch. Taking it for play/pause whenever there was a queue
// meant none of those could be pressed from the keyboard.
const SPACE_TAGS = new Set(['BUTTON', 'A', 'SUMMARY', 'AUDIO', 'VIDEO'])
const SPACE_ROLES = new Set([
  'button',
  'link',
  'checkbox',
  'switch',
  'radio',
  'tab',
  'option',
  'menuitem',
  'menuitemcheckbox',
  'menuitemradio',
  'slider',
  'spinbutton',
  'combobox',
  'textbox',
  'searchbox',
  'treeitem',
])
function ownsSpace(el) {
  if (!el) return false
  if (isTypingTarget(el) || SPACE_TAGS.has(el.tagName)) return true
  const role = typeof el.getAttribute === 'function' ? el.getAttribute('role') : null
  return !!role && SPACE_ROLES.has(role.trim().split(/\s+/)[0].toLowerCase())
}

function installKeyboardShortcuts() {
  if (keyboardInstalled || typeof window === 'undefined') return
  keyboardInstalled = true
  window.addEventListener('keydown', (e) => {
    // A focused widget (track list, menu, dialog, slider) already handled it.
    if (e.defaultPrevented) return
    // Never hijack typing in inputs/textareas or with modifier combos.
    if (isTypingTarget(e.target) || e.metaKey || e.ctrlKey || e.altKey) return
    // While the lyrics-sync editor is open the global Space/Arrow
    // shortcuts compete with the editor's own keyboard contract
    // (Space = stamp, ↑/↓ = move active line). The noAutoAdvance flag
    // is a perfectly good proxy for "editor is open" so we use that
    // here to defer to the editor.
    if (noAutoAdvance.value) return
    if (playlist.value.length === 0 && e.code !== 'Space') return

    switch (e.code) {
      case 'Space':
        if (playlist.value.length === 0 || ownsSpace(e.target)) return
        e.preventDefault()
        toggle()
        break
      case 'ArrowRight':
        // Shift = next track, plain = seek +10s
        if (e.shiftKey) {
          e.preventDefault()
          next()
        } else {
          e.preventDefault()
          seek((currentTime.value || 0) + 10)
        }
        break
      case 'ArrowLeft':
        if (e.shiftKey) {
          e.preventDefault()
          prev()
        } else {
          e.preventDefault()
          seek((currentTime.value || 0) - 10)
        }
        break
      case 'MediaTrackNext':
        e.preventDefault()
        mediaCommand('next')
        break
      case 'MediaTrackPrevious':
        e.preventDefault()
        mediaCommand('prev')
        break
      case 'MediaPlayPause':
        e.preventDefault()
        mediaCommand('toggle')
        break
      case 'ArrowUp':
        e.preventDefault()
        setVolume(Math.min(1, volume.value + 0.05))
        break
      case 'ArrowDown':
        e.preventDefault()
        setVolume(Math.max(0, volume.value - 0.05))
        break
      case 'KeyM':
        e.preventDefault()
        toggleMute()
        break
      case 'KeyN':
        e.preventDefault()
        next()
        break
      case 'KeyP':
        e.preventDefault()
        prev()
        break
      case 'KeyS':
        e.preventDefault()
        toggleShuffle()
        break
      case 'KeyR':
        e.preventDefault()
        cycleRepeat()
        break
      default:
        break
    }
  })
}

// Install immediately when this module is first used in the browser.
installKeyboardShortcuts()

export function formatTime(seconds) {
  if (!isFinite(seconds) || seconds < 0) return '0:00'
  const total = Math.floor(seconds)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function trackInfoFromFile(file) {
  return trackFromFile(file)
}

export function songToTrack(song) {
  return trackFromSong(song)
}

export function usePlayer() {
  return {
    playlist,
    currentIndex,
    currentTrack,
    isPlaying,
    isBuffering,
    currentTime,
    duration,
    progressPct,
    volume,
    isMuted,
    repeatMode,
    shuffle,
    upcoming,
    // lyrics
    lyricsLines,
    lyricsPlain,
    lyricsLoading,
    activeLyricIndex,
    lyricsOffset,
    lyricVersionIndex,
    lyricVersionCount,
    seekToLyric,
    refreshLyrics,
    adjustLyricsOffset,
    resetLyricsOffset,
    saveLyricsOffset,
    switchLyricVersion,
    // playback
    setPlaylist,
    restoreSession,
    playStreamSongs,
    downloadTrack,
    enqueue,
    enqueueNext,
    removeFromQueue,
    clearUpcoming,
    moveInQueue,
    moveUpcoming,
    mediaCommand,
    playAt,
    play,
    pause,
    toggle,
    seek,
    seekRatio,
    setVolume,
    toggleMute,
    next,
    prev,
    setRepeat,
    cycleRepeat,
    setShuffle,
    toggleShuffle,
    // autoplay / radio
    autoplayRadio,
    setAutoplayRadio,
    normalizeLoudness,
    eqUserPresets,
    saveEqPreset,
    deleteEqPreset,
    setEqPreamp,
    speed,
    setSpeed,
    keepPitch,
    setKeepPitch,
    restoreSpeed,
    spectrum,
    spectrumInfo,
    volumeLevel,
    setVolumeLevel,
    balance,
    setBalance,
    mono,
    setMono,
    eqCurve,
    setNormalizeLoudness,
    startRadio,
    // the sound engine
    hasEngine: () => !!(ensureAudio() && engine),
    crossfade,
    setCrossfade,
    gapless,
    setGapless,
    eq,
    setEqEnabled,
    setEqPreset,
    setEqBand,
    // sleep timer
    sleepMode,
    sleepEndsAt,
    setSleepTimer,
    setSleepAfterTrack,
    cancelSleep,
    // sync-editor extras
    playbackRate,
    setPlaybackRate,
    clipLoopStart,
    clipLoopEnd,
    clipLoop,
    clipUnloop,
    noAutoAdvance,
  }
}
