import { describe, expect, it } from 'vitest'
import { createLineEditor, makeLine } from '../model/lyrics/lineEditor'

function editorWith(...lines) {
  const ed = createLineEditor()
  ed.load(lines.map(([text, time = null]) => ({ text, time })))
  return ed
}
const texts = (ed) => ed.lines.value.map((l) => l.text)
const times = (ed) => ed.lines.value.map((l) => l.time)

describe('makeLine', () => {
  it('gives every line its own key', () => {
    expect(makeLine('a')._id).not.toBe(makeLine('a')._id)
    expect(makeLine(null, '4.5')).toMatchObject({ text: '', time: 4.5 })
  })
})

describe('load', () => {
  it('puts the cursor on the first line still to time', () => {
    const ed = editorWith(['a', 1], ['b', 2], ['c'], ['d'])
    expect(ed.active.value).toBe(2)
    expect(ed.timed.value).toBe(2)
  })

  it('starts at the top when everything is timed, with no history', () => {
    const ed = editorWith(['a', 1], ['b', 2])
    expect(ed.active.value).toBe(0)
    expect(ed.canUndo.value).toBe(false)
  })
})

describe('stamping', () => {
  it('times the line and moves on to the next', () => {
    const ed = editorWith(['a'], ['b'])
    expect(ed.stamp(0, 12.34567)).toBe(true)
    expect(times(ed)).toEqual([12.346, null])
    expect(ed.active.value).toBe(1)
  })

  it('stays put when asked to, and on the last line', () => {
    const ed = editorWith(['a'], ['b'])
    ed.stamp(0, 1, { advance: false })
    expect(ed.active.value).toBe(0)
    ed.setActive(1)
    expect(ed.stamp(1, 2)).toBe(false)
    expect(ed.active.value).toBe(1)
  })

  it('ignores a line that is not there', () => {
    const ed = editorWith(['a'])
    expect(ed.stamp(5, 1)).toBe(false)
    expect(ed.canUndo.value).toBe(false)
  })

  it('clears the lowest timed line, not the last one touched', () => {
    const ed = editorWith(['a', 5], ['b', 9], ['c'])
    ed.stamp(0, 6, { advance: false })
    expect(ed.clearLastStamp()).toBe(true)
    expect(times(ed)).toEqual([6, null, null])
  })

  it('clears everything in one undoable step', () => {
    const ed = editorWith(['a', 5], ['b', 9])
    expect(ed.clearAll()).toBe(true)
    expect(times(ed)).toEqual([null, null])
    ed.undo()
    expect(times(ed)).toEqual([5, 9])
    expect(editorWith(['a']).clearAll()).toBe(false)
  })

  it('nudges the line under the cursor, never below zero', () => {
    const ed = editorWith(['a', 0.05], ['b'])
    ed.setActive(0)
    ed.nudge(0.1)
    expect(times(ed)[0]).toBe(0.15)
    ed.nudge(-1)
    expect(times(ed)[0]).toBe(0)
    ed.setActive(1)
    expect(ed.nudge(0.1)).toBe(false)
  })

  it('reports lines out of order as they happen', () => {
    const ed = editorWith(['a', 10], ['b', 20], ['c'])
    ed.stamp(2, 15)
    expect(ed.issues.value).toEqual([2])
  })
})

describe('moving the cursor', () => {
  it('stops at either end', () => {
    const ed = editorWith(['a'], ['b'])
    ed.setActive(0)
    expect(ed.move(-1)).toBe(false)
    expect(ed.move(1)).toBe(true)
    expect(ed.move(1)).toBe(false)
    expect(ed.active.value).toBe(1)
    expect(ed.setActive(7)).toBe(false)
  })
})

describe('lines in and out', () => {
  it('inserts an empty line, open for typing, as one undo step with its words', () => {
    const ed = editorWith(['a', 1], ['b', 2])
    expect(ed.insertAt(1)).toBe(1)
    expect(ed.editing.value).toBe(1)
    ed.setText(1, 'n')
    ed.setText(1, 'new')
    ed.stopEdit()
    expect(texts(ed)).toEqual(['a', 'new', 'b'])
    ed.undo()
    expect(texts(ed)).toEqual(['a', 'b'])
  })

  it('removes a line and keeps the cursor on the list', () => {
    const ed = editorWith(['a'], ['b'], ['c'])
    ed.setActive(2)
    ed.remove(2)
    expect(texts(ed)).toEqual(['a', 'b'])
    expect(ed.active.value).toBe(1)
    ed.remove(0)
    ed.remove(0)
    expect(ed.lines.value).toEqual([])
    expect(ed.active.value).toBe(0)
  })

  it('keeps the keys of the lines around an insert', () => {
    const ed = editorWith(['a'], ['b'])
    const before = ed.lines.value.map((l) => l._id)
    ed.insertAt(1)
    expect([ed.lines.value[0]._id, ed.lines.value[2]._id]).toEqual(before)
  })
})

describe('typing in a line', () => {
  it('makes one undo step of a whole edit, not one per key', () => {
    const ed = editorWith(['Kuwa mbali na wewe', 15.5])
    ed.startEdit(0)
    ed.setText(0, 'Kuwa mbali')
    ed.setText(0, 'Kuwa mbali nawe')
    ed.stopEdit()
    expect(texts(ed)).toEqual(['Kuwa mbali nawe'])
    ed.undo()
    expect(texts(ed)).toEqual(['Kuwa mbali na wewe'])
    expect(ed.canUndo.value).toBe(false)
  })

  it('puts the words back on Escape, and leaves no empty undo step', () => {
    const ed = editorWith(['before'])
    ed.startEdit(0)
    ed.setText(0, 'after')
    ed.cancelEdit()
    expect(texts(ed)).toEqual(['before'])
    expect(ed.editing.value).toBe(-1)
    expect(ed.canUndo.value).toBe(false)
  })

  it('closes the edit when another line is picked', () => {
    const ed = editorWith(['a'], ['b'])
    ed.startEdit(0)
    ed.setActive(1)
    expect(ed.editing.value).toBe(-1)
  })
})

describe('undo and redo', () => {
  it('walks back and forth through the changes', () => {
    const ed = editorWith(['a'], ['b'])
    ed.stamp(0, 1)
    ed.stamp(1, 2)
    ed.undo()
    expect(times(ed)).toEqual([1, null])
    expect(ed.active.value).toBe(1)
    ed.undo()
    expect(times(ed)).toEqual([null, null])
    expect(ed.undo()).toBe(false)
    ed.redo()
    ed.redo()
    expect(times(ed)).toEqual([1, 2])
    expect(ed.redo()).toBe(false)
  })

  it('forgets what could be redone once something new is done', () => {
    const ed = editorWith(['a'], ['b'])
    ed.stamp(0, 1)
    ed.undo()
    ed.stamp(1, 3)
    expect(ed.canRedo.value).toBe(false)
  })

  it('keeps the last two hundred steps', () => {
    const ed = editorWith(['a'])
    for (let i = 0; i < 250; i++) ed.stamp(0, i, { advance: false })
    let steps = 0
    while (ed.undo()) steps++
    expect(steps).toBe(200)
    expect(times(ed)).toEqual([49])
  })
})
