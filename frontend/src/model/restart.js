import { ref } from 'vue'
import { toast } from '/src/model/toast'
import { t } from '/src/i18n'
import { usePlayer } from '/src/model/player'
import * as decks from '/src/model/player/decks'
import { applyVolume } from '/src/model/player/sound'
import { saveSession } from '/src/model/player/session'

// Restarting into an update, kindly. The music fades instead of cutting, a
// screen says sorry and that it will only be a moment, and the app that
// comes back carries on with what was playing, at the same second, with a
// word to say it is back. Before, the window just vanished mid-song and came
// back paused.

/** What the "be right back" screen shows, while it shows. */
export const restarting = ref(null) // { playing, title }

const NOTE_KEY = 'dn.afterRestart'
// A note older than this is from some other day: the app was restarted by
// hand much later, and music starting by itself then would be a surprise.
const NOTE_FRESH_MS = 10 * 60 * 1000
const SCREEN_MS = 1700
const FADE_S = 0.9

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function player() {
  return usePlayer()
}

// Turn the music down to nothing, without touching the volume setting.
function fadeAway() {
  if (decks.engine) decks.engine.rampVolume(0, FADE_S)
  else if (decks.audio) {
    const a = decks.audio
    const from = a.volume
    for (let k = 1; k <= 10; k++) setTimeout(() => (a.volume = from * (1 - k / 10)), (FADE_S * 1000 * k) / 10)
  }
}

function fadeBack() {
  applyVolume()
}

/**
 * Restart by way of *run* (which restarts the app and says whether it did):
 * the music fades, the screen shows, then *run*. If it did not, everything is
 * as it was.
 * @param {() => Promise<boolean>|boolean} run
 */
export async function restartKindly(run) {
  const p = await player()
  const playing = !!(p.isPlaying && p.isPlaying.value)
  const track = p.currentTrack && p.currentTrack.value
  try {
    localStorage.setItem(NOTE_KEY, JSON.stringify({ playing, when: Date.now() }))
  } catch {
    // storage blocked: the app comes back paused, as it always did
  }
  try {
    saveSession()
  } catch {
    // the throttled save from a few seconds ago stands
  }
  restarting.value = { playing, title: (track && track.title) || '' }
  if (playing) fadeAway()
  await wait(SCREEN_MS)
  let ok = false
  try {
    ok = !!(await run())
  } catch {
    ok = false
  }
  if (!ok) {
    restarting.value = null
    try {
      localStorage.removeItem(NOTE_KEY)
    } catch {
      // nothing kept
    }
    if (playing) fadeBack()
  }
  return ok
}

/** Read, once, what was going on before a restart. */
export function takeRestartNote() {
  try {
    const note = JSON.parse(localStorage.getItem(NOTE_KEY) || 'null')
    localStorage.removeItem(NOTE_KEY)
    if (note && Date.now() - (note.when || 0) < NOTE_FRESH_MS) return note
  } catch {
    // nothing kept
  }
  return null
}

const WELCOMES = ['brb.welcomeA', 'brb.welcomeB', 'brb.welcomeC']

/**
 * After the session is back: if the app was restarted for an update while
 * music played, play on, and say hello.
 */
export async function welcomeBack() {
  const note = takeRestartNote()
  if (!note) return false
  const p = await player()
  const track = p.currentTrack.value
  if (note.playing && track) {
    p.play()
    const key = WELCOMES[Math.floor(Math.random() * WELCOMES.length)]
    toast(t(key, { title: track.title || '' }), { icon: 'ph:sparkle-fill', tone: 'success', timeout: 7000 })
  } else {
    toast(t('brb.welcomeIdle'), { icon: 'ph:sparkle-fill', tone: 'success', timeout: 6000 })
  }
  return true
}
