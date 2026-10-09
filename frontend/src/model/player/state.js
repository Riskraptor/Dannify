import { ref, shallowRef, computed } from 'vue'

// What the rest of the player shares: the queue, where it is in it, the
// transport's state and the listener's settings that several parts read.
// It imports nothing else of the player's, so it is ready before any of them.

export const VOLUME_KEY = 'dannify-player-volume'

export const playlist = ref([])
// Storage can refuse to be read (blocked, or a browser in private mode on
// the LAN), and a throw here, while the module loads, blanked the whole app.
export function readStored(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
export function storeSetting(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // blocked storage: the choice lasts this session
  }
}

export const currentIndex = ref(-1)
export const isPlaying = ref(false)
export const isBuffering = ref(false)
export const currentTime = ref(0)
export const duration = ref(0)
export const volume = ref(parseFloat(readStored(VOLUME_KEY) || '0.85'))
export const isMuted = ref(false)
// Shuffle and repeat are a listening preference, not a per-session accident:
// someone who listens on shuffle expects to still be on shuffle tomorrow.
export const REPEAT_KEY = 'dannify-repeat'
export const SHUFFLE_KEY = 'dannify-shuffle'

function remembered(key, allowed, fallback) {
  try {
    const value = localStorage.getItem(key)
    if (value !== null && allowed.includes(value)) return value
  } catch {
    // Blocked storage: the default is fine.
  }
  return fallback
}

export const repeatMode = ref(remembered(REPEAT_KEY, ['off', 'all', 'one'], 'off'))
export const shuffle = ref(remembered(SHUFFLE_KEY, ['0', '1'], '0') === '1')
export const playbackRate = ref(Math.max(0.5, Math.min(2, Number(readStored('dannify-speed')) || 1)))

// --- Clip-loop (used by the sync editor) ---
// When set, the audio loops between [clipLoopStart, clipLoopEnd]. Lets the
// editor focus on a single lyric line so the user can re-stamp it without
// rewinding the whole song.
export const clipLoopStart = ref(null)
export const clipLoopEnd = ref(null)
// When true, audio ``ended`` does NOT auto-advance to the next track.
// Used by the lyrics sync editor: when the user is mid-edit and the song
// reaches the end, just stop: don't load a new track and reset the
// editor's context.
export const noAutoAdvance = ref(false)
// The playhead as the screen should draw it: read from the element every
// frame while playing. `timeupdate` only fires about four times a second, so
// the progress bar moved in visible steps and a lyric line could light up a
// quarter of a second late. Only the bar and the lyric highlight follow this;
// everything else stays on the slower clock and does not redraw every frame.
export const frameTime = ref(0)
// The shuffled play order: every queue index exactly once. What sits before
// the playing track in it has played, what sits after it is still to come.
// There is no separate position to keep in step: it is wherever the playing
// track is. A ref, so "Up next" follows it.
export const shuffleOrder = shallowRef([])
// Monotonic token bumped on every track change; async work checks it so stale
// callbacks from a previous track are discarded (prevents wrong-song audio).
export let playGen = 0
export function bumpPlayGen() {
  playGen += 1
  return playGen
}
// For length-less remux streams: server starts output at this offset, so the
// element's currentTime is relative to it: we add it back for the UI clock.
export let streamBaseOffset = 0
export function setStreamBaseOffset(seconds) {
  streamBaseOffset = seconds
}

export const YT_ID = /^[A-Za-z0-9_-]{11}$/

export function videoIdOf(track) {
  const id = track && (track.video_id || track.song_id)
  return typeof id === 'string' && YT_ID.test(id) ? id : ''
}

export const currentTrack = computed(() =>
  currentIndex.value >= 0 && currentIndex.value < playlist.value.length
    ? playlist.value[currentIndex.value]
    : null
)

// Drawn from the frame clock, so the bar glides instead of stepping.
export const progressPct = computed(() =>
  duration.value > 0 ? Math.min(100, (frameTime.value / duration.value) * 100) : 0
)
