// Timing lyrics against the song: the line editor wired to the player.
//
// Taps take the playhead's time, the cursor follows the song while it
// plays, one line can be looped to get it right, and the keyboard drives
// all of it (see keymap.js).

import { ref, computed, watch } from 'vue'
import { loopWindow, predictLine, NUDGE_STEP } from './timing'
import { syncCommand } from './keymap'

// After the user does something themselves, the cursor stays where they
// put it this long before following the song again.
const MANUAL_HOLD_MS = 800

const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now())

/**
 * @param {object} o
 * @param {object} o.player   the player model (usePlayer())
 * @param {object} o.editor   a line editor (createLineEditor())
 * @param {import('vue').Ref<boolean>} o.enabled  whether the timing step is showing
 * @param {() => void} [o.release]  takes the focus off a button that a Space
 *   tap would otherwise press as well
 */
export function useSyncSession({ player, editor, enabled, release = () => {} }) {
  // The looped line, by identity: indexes shift as lines come and go.
  const loopId = ref(null)
  const loopIndex = computed(() =>
    loopId.value == null ? -1 : editor.lines.value.findIndex((l) => l._id === loopId.value)
  )
  // Bumped whenever the cursor should be brought into view.
  const reveal = ref(0)
  let lastManual = 0

  function markManual() {
    lastManual = now()
  }
  function show() {
    reveal.value++
  }

  function stopLoop() {
    player.clipUnloop()
    loopId.value = null
  }

  // The looped line went away (deleted, or undone): so does the loop. At
  // once, not on the next tick: a loop set and its line removed in between
  // would otherwise look like no change at all.
  watch(
    loopIndex,
    (idx) => {
      if (idx < 0 && loopId.value != null) stopLoop()
    },
    { flush: 'sync' }
  )
  // Leaving the timing step ends any loop.
  watch(enabled, (on) => {
    if (!on && loopId.value != null) stopLoop()
  })

  function stamp(idx = editor.active.value, { advance = true } = {}) {
    markManual()
    editor.stamp(idx, player.currentTime.value, { advance })
    show()
  }

  function select(idx) {
    markManual()
    editor.setActive(idx)
  }

  function moveTo(idx) {
    markManual()
    if (editor.setActive(idx)) show()
  }

  function step(delta) {
    markManual()
    if (editor.move(delta)) show()
  }

  function nudge(delta) {
    markManual()
    editor.nudge(delta)
  }

  function toggleLoop(idx = editor.active.value) {
    const line = editor.lines.value[idx]
    if (!line) return
    if (loopIndex.value === idx) return stopLoop()
    const { start, end } = loopWindow(editor.lines.value, idx, player.currentTime.value, player.duration.value)
    editor.setActive(idx)
    loopId.value = line._id
    player.clipLoop(start, end)
  }

  function playFrom(idx = editor.active.value) {
    const line = editor.lines.value[idx]
    if (!line || line.time == null) return
    stopLoop()
    player.seek(line.time)
    if (!player.isPlaying.value) player.play()
  }

  function playFromStart() {
    markManual()
    stopLoop()
    player.seek(0)
    editor.setActive(0)
    show()
    if (!player.isPlaying.value) player.play()
  }

  function seekBy(delta) {
    player.seek(Math.max(0, (player.currentTime.value || 0) + delta))
  }

  function setRate(rate) {
    player.setPlaybackRate(rate)
  }

  function stepRate(delta) {
    player.setPlaybackRate((player.playbackRate.value || 1) + delta)
  }

  function insertBelow(idx = editor.active.value) {
    editor.insertAt(idx + 1)
    show()
  }

  function remove(idx = editor.active.value) {
    editor.remove(idx)
    show()
  }

  function clearAll() {
    if (editor.clearAll()) stopLoop()
  }

  function jumpToIssue() {
    const issues = editor.issues.value
    if (!issues.length) return
    const at = issues.find((i) => i > editor.active.value) ?? issues[0]
    moveTo(at)
  }

  // As the song plays, the cursor moves to the line about to be sung, so
  // the user only has to tap at the right moment. Not while they are typing,
  // not while a line is looped (that is them working on one line), and not
  // right after they moved it themselves.
  watch([() => player.currentTime.value, () => player.isPlaying.value], ([t, playing]) => {
    if (!enabled.value || !playing) return
    if (editor.editing.value !== -1 || loopId.value != null) return
    if (now() - lastManual < MANUAL_HOLD_MS) return
    const target = predictLine(editor.lines.value, t)
    if (target < 0 || target === editor.active.value) return
    editor.active.value = target
    show()
  })

  const COMMANDS = {
    stamp: () => stamp(editor.active.value, { advance: true }),
    'stamp-stay': () => stamp(editor.active.value, { advance: false }),
    insert: () => insertBelow(),
    next: () => step(1),
    prev: () => step(-1),
    first: () => moveTo(0),
    last: () => moveTo(editor.lines.value.length - 1),
    'nudge-back': () => nudge(-NUDGE_STEP),
    'nudge-forward': () => nudge(NUDGE_STEP),
    'clear-last': () => editor.clearLastStamp(),
    undo: () => editor.undo(),
    redo: () => editor.redo(),
    loop: () => toggleLoop(),
    play: () => player.toggle(),
    edit: () => editor.startEdit(editor.active.value),
    slower: () => stepRate(-0.25),
    faster: () => stepRate(0.25),
    delete: () => remove(),
  }

  /** The editor's keydown, while the timing step shows. True if it was used. */
  function handleKey(e) {
    if (!enabled.value) return false
    const el = e.target
    const cmd = syncCommand(e, {
      tag: el && el.tagName,
      role: el && typeof el.getAttribute === 'function' ? el.getAttribute('role') : null,
    })
    if (!cmd || !COMMANDS[cmd]) return false
    e.preventDefault()
    // A focused button would take the Space too, on its way up, and time a
    // second line.
    if (cmd.startsWith('stamp') && typeof document !== 'undefined' && document.activeElement?.tagName === 'BUTTON') {
      release()
    }
    COMMANDS[cmd]()
    return true
  }

  return {
    loopIndex,
    reveal,
    stamp,
    select,
    moveTo,
    step,
    nudge,
    toggleLoop,
    stopLoop,
    playFrom,
    playFromStart,
    seekBy,
    setRate,
    stepRate,
    insertBelow,
    remove,
    clearAll,
    jumpToIssue,
    handleKey,
    markManual,
  }
}
