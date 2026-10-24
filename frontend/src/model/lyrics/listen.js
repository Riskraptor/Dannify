// Listening while the words are typed: the song played, paused and moved
// through from inside the editor, by keys that never type a letter or move
// the cursor in the words box.
//
// Writing lyrics down as the song plays is play, hear a line, pause, type
// it, play again. Playing again from the very moment it stopped cut the
// line's run-up off, so by default it goes back a little first and the last
// words are heard again, the way transcription tools do it.

import { ref } from 'vue'

/** Seconds heard again when the song plays after a pause from here. */
export const REPLAY = 2
/** Seconds the back and forward keys move. */
export const SKIP = 5

const REPLAY_KEY = 'dannify-lyrics-replay'
// Moved further than this while paused, the song was put somewhere on
// purpose: it plays from there, not before it.
const MOVED = 0.5

function store() {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null
  } catch {
    return null
  }
}

function loadReplay() {
  try {
    return store()?.getItem(REPLAY_KEY) !== '0'
  } catch {
    return true
  }
}

/**
 * The editor's listening keys: Ctrl+Space plays and pauses, Alt+Left and
 * Alt+Right go back and forward. In a text box none of them writes anything
 * or moves the cursor (Ctrl+Left would: it jumps a word), and the timing
 * step's own keys use neither Ctrl+Space nor Alt.
 * @param {{code: string, ctrlKey?: boolean, metaKey?: boolean,
 *          altKey?: boolean, shiftKey?: boolean}} e a keydown event
 * @returns {'toggle'|'back'|'forward'|null}
 */
export function listenCommand(e) {
  if (e.shiftKey) return null
  // Ctrl itself on a Mac too: Cmd+Space is the system's search.
  if (e.ctrlKey && !e.altKey && !e.metaKey && e.code === 'Space') return 'toggle'
  if (e.altKey && !e.ctrlKey && !e.metaKey) {
    if (e.code === 'ArrowLeft') return 'back'
    if (e.code === 'ArrowRight') return 'forward'
  }
  return null
}

/**
 * @param {object} o
 * @param {object} o.player  the player model (usePlayer())
 * @param {(delta: number) => void} o.seekBy  moves the song (the timing
 *   session's, which keeps the line to tap in step when paused)
 * @param {() => boolean} [o.replays]  whether playing again goes back a
 *   little first: in the words step, not while lines are being tapped in
 */
export function createListen({ player, seekBy, replays = () => true }) {
  const replay = ref(loadReplay())
  // Where the song was paused from here; null once it has played again or
  // was not paused from here.
  let pausedAt = null

  function setReplay(on) {
    replay.value = !!on
    try {
      store()?.setItem(REPLAY_KEY, on ? '1' : '0')
    } catch {
      // Storage that throws: on for this time only.
    }
  }

  function toggle() {
    if (player.isPlaying.value) {
      player.pause()
      pausedAt = player.currentTime.value || 0
      return
    }
    const at = player.currentTime.value || 0
    if (replay.value && replays() && pausedAt != null && Math.abs(at - pausedAt) < MOVED) {
      seekBy(-REPLAY)
    }
    pausedAt = null
    player.play()
  }

  function back() {
    seekBy(-SKIP)
  }

  function forward() {
    seekBy(SKIP)
  }

  const COMMANDS = { toggle, back, forward }

  /** The editor's keydown, in any step. True if it was used. */
  function handleKey(e) {
    const cmd = listenCommand(e)
    if (!cmd) return false
    e.preventDefault()
    // Kept from the app's own keys too: Alt+Left there goes back a page,
    // under the editor.
    e.stopPropagation()
    if (!e.repeat || cmd !== 'toggle') COMMANDS[cmd]()
    return true
  }

  return { replay, setReplay, toggle, back, forward, handleKey }
}
