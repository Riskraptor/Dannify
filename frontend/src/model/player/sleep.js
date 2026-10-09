import { ref } from 'vue'
import { audio, cancelTransition, engine } from '/src/model/player/decks'
import { applyVolume } from '/src/model/player/sound'
import { isPlaying } from '/src/model/player/state'
import { pause } from '/src/model/player/transport'

// --- Sleep timer ---
//
// After a time, or at the end of this song. On a time, the last ten seconds
// fade out rather than cut, the way someone turning it down would.
export const sleepMode = ref('off') // off | time | track
export const sleepEndsAt = ref(0)
const SLEEP_FADE_S = 10
let sleepTimer = 0
export let sleepFading = false

export function setSleepTimer(minutes) {
  cancelSleep()
  const ms = Math.max(1, Number(minutes) || 0) * 60000
  sleepMode.value = 'time'
  sleepEndsAt.value = Date.now() + ms
  sleepTimer = setTimeout(sleepFadeOut, Math.max(0, ms - SLEEP_FADE_S * 1000))
}

export function setSleepAfterTrack() {
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

export function cancelSleep() {
  clearTimeout(sleepTimer)
  sleepTimer = 0
  const wasFading = sleepFading
  sleepFading = false
  sleepMode.value = 'off'
  sleepEndsAt.value = 0
  if (wasFading) applyVolume()
}
