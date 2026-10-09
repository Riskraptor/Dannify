// The lines being timed, and every change made to them, undoable.
//
// No player in here: a stamp is given its time by whoever calls it. That
// keeps the editing rules (what moves the cursor, what a deleted line takes
// with it, what undo brings back) testable on their own.

import { ref, computed } from 'vue'
import { roundTime, nudgeTime, stampQuality, issueIndexes, countTimed } from './timing'

const UNDO_CAP = 200

// A local key per line, so Vue's keyed lists stay put while lines are
// inserted and deleted around them.
let nextId = 1
export function makeLine(text = '', time = null) {
  return { _id: nextId++, text: String(text || ''), time: time == null ? null : Number(time) }
}

export function createLineEditor() {
  const lines = ref([])
  const active = ref(0)
  // The line whose words are open for typing, or -1.
  const editing = ref(-1)
  const undoStack = ref([])
  const redoStack = ref([])
  // The text a line had when typing in it began, for Escape to put back,
  // and whether that edit has been recorded for undo yet.
  let editStart = null
  let editRecorded = false
  // Whether this edit's undo step is its own (not an insert's), so that
  // Escape can take it back off the history along with the typing.
  let editOwnsUndo = false

  const quality = computed(() => stampQuality(lines.value))
  const issues = computed(() => issueIndexes(quality.value))
  const timed = computed(() => countTimed(lines.value))
  const canUndo = computed(() => undoStack.value.length > 0)
  const canRedo = computed(() => redoStack.value.length > 0)

  function snapshot() {
    return {
      lines: lines.value.map((l) => ({ _id: l._id, text: l.text, time: l.time })),
      active: active.value,
    }
  }
  function restore(snap) {
    lines.value = snap.lines
    active.value = Math.min(snap.active, Math.max(0, snap.lines.length - 1))
    editing.value = -1
  }
  // Called before every change: the state it is about to leave is what an
  // undo returns to. A new change makes the redo history meaningless.
  function record() {
    undoStack.value.push(snapshot())
    if (undoStack.value.length > UNDO_CAP) undoStack.value.shift()
    redoStack.value = []
  }

  /** Start over with these lines; the cursor goes to the first untimed one. */
  function load(list) {
    lines.value = (list || []).map((l) => makeLine(l.text, l.time))
    const firstUntimed = lines.value.findIndex((l) => l.time == null)
    active.value = Math.max(0, firstUntimed)
    editing.value = -1
    undoStack.value = []
    redoStack.value = []
  }

  function valid(idx) {
    return idx >= 0 && idx < lines.value.length
  }

  function setActive(idx) {
    if (!valid(idx)) return false
    active.value = idx
    if (editing.value !== idx) stopEdit()
    return true
  }

  /** Move the cursor by `delta` lines; false at either end. */
  function move(delta) {
    const to = active.value + delta
    if (!valid(to)) return false
    active.value = to
    return true
  }

  /**
   * Give a line its time. With `advance`, the cursor goes on to the next
   * line, ready for the next tap. Returns whether it moved.
   */
  function stamp(idx, seconds, { advance = true } = {}) {
    if (!valid(idx)) return false
    record()
    lines.value[idx].time = roundTime(seconds)
    if (advance && idx < lines.value.length - 1) {
      active.value = idx + 1
      return true
    }
    return false
  }

  function clearStamp(idx) {
    if (!valid(idx) || lines.value[idx].time == null) return false
    record()
    lines.value[idx].time = null
    return true
  }

  /** Untime the line timed last in the song (the quick "oops" key). */
  function clearLastStamp() {
    for (let i = lines.value.length - 1; i >= 0; i--) {
      if (lines.value[i].time != null) return clearStamp(i)
    }
    return false
  }

  function clearAll() {
    if (!lines.value.some((l) => l.time != null)) return false
    record()
    for (const l of lines.value) l.time = null
    return true
  }

  function nudge(delta) {
    const line = lines.value[active.value]
    if (!line || line.time == null) return false
    record()
    line.time = nudgeTime(line.time, delta)
    return true
  }

  /** A new, empty line at `idx`, open for typing. */
  function insertAt(idx) {
    const at = Math.max(0, Math.min(idx, lines.value.length))
    record()
    lines.value.splice(at, 0, makeLine('', null))
    active.value = at
    startEdit(at)
    // The insert itself is the undo step: typing into the new line is part
    // of it, not a second one.
    editRecorded = true
    return at
  }

  function remove(idx) {
    if (!valid(idx)) return false
    record()
    lines.value.splice(idx, 1)
    editing.value = -1
    if (active.value >= lines.value.length) active.value = Math.max(0, lines.value.length - 1)
    return true
  }

  function startEdit(idx) {
    if (!valid(idx)) return false
    active.value = idx
    editing.value = idx
    editStart = lines.value[idx].text
    editRecorded = false
    editOwnsUndo = false
    return true
  }

  /** Typing into the open line. One undo step per edit, not per key. */
  function setText(idx, text) {
    if (!valid(idx)) return
    if (!editRecorded) {
      record()
      editRecorded = true
      editOwnsUndo = true
    }
    lines.value[idx].text = String(text ?? '')
  }

  function stopEdit() {
    editing.value = -1
    editStart = null
    editRecorded = false
    editOwnsUndo = false
  }

  /** Escape while typing: the line goes back to what it said before. */
  function cancelEdit() {
    const idx = editing.value
    if (valid(idx) && editStart != null) lines.value[idx].text = editStart
    if (editOwnsUndo) undoStack.value.pop()
    stopEdit()
  }

  function undo() {
    if (!undoStack.value.length) return false
    redoStack.value.push(snapshot())
    restore(undoStack.value.pop())
    return true
  }

  function redo() {
    if (!redoStack.value.length) return false
    undoStack.value.push(snapshot())
    restore(redoStack.value.pop())
    return true
  }

  return {
    lines,
    active,
    editing,
    quality,
    issues,
    timed,
    canUndo,
    canRedo,
    load,
    setActive,
    move,
    stamp,
    clearStamp,
    clearLastStamp,
    clearAll,
    nudge,
    insertAt,
    remove,
    startEdit,
    setText,
    stopEdit,
    cancelEdit,
    undo,
    redo,
  }
}
