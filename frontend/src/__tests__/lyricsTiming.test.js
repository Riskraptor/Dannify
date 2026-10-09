import { describe, expect, it } from 'vitest'
import {
  roundTime,
  nudgeTime,
  stampQuality,
  issueIndexes,
  nextIssue,
  countTimed,
  minTimed,
  enoughTimed,
  predictLine,
  loopWindow,
  stampTicks,
} from '../model/lyrics/timing'

const at = (...times) => times.map((time, i) => ({ text: `line ${i + 1}`, time }))

describe('times', () => {
  it('keeps milliseconds and never goes below zero', () => {
    expect(roundTime(12.34567)).toBe(12.346)
    expect(roundTime(-1)).toBe(0)
    expect(nudgeTime(10, 0.1)).toBe(10.1)
    expect(nudgeTime(0.05, -0.1)).toBe(0)
  })
})

describe('stampQuality', () => {
  it('finds nothing wrong with lines in order', () => {
    expect(stampQuality(at(1, 3, 5))).toEqual({})
  })

  it('flags a line timed before the one above it', () => {
    expect(stampQuality(at(10, 5, 12))).toEqual({ 1: { error: true } })
  })

  it('warns about a line too close to the one above to be read', () => {
    expect(stampQuality(at(10, 10.1, 12))).toEqual({ 1: { warn: true } })
  })

  it('compares with the last timed line, skipping untimed ones', () => {
    expect(stampQuality(at(10, null, 9))).toEqual({ 2: { error: true } })
  })

  it('lists the issues top to bottom and finds the next one round the end', () => {
    const issues = issueIndexes(stampQuality(at(10, 5, 12, 11, 20)))
    expect(issues).toEqual([1, 3])
    expect(nextIssue(issues, 1)).toBe(3)
    expect(nextIssue(issues, 3)).toBe(1)
    expect(nextIssue([], 0)).toBe(-1)
  })
})

describe('how much has to be timed', () => {
  it('asks for half the song and at least two lines', () => {
    expect(minTimed(10)).toBe(5)
    expect(minTimed(3)).toBe(2)
    expect(minTimed(0)).toBe(0)
  })

  it('lets a one-line song through with its one line', () => {
    expect(minTimed(1)).toBe(1)
    expect(enoughTimed(at(4))).toBe(true)
  })

  it('needs lines at all', () => {
    expect(enoughTimed([])).toBe(false)
  })

  it('counts the timed lines', () => {
    expect(countTimed(at(1, null, 3, null))).toBe(2)
    expect(enoughTimed(at(1, null, 3, null))).toBe(true)
    expect(enoughTimed(at(1, null, null, null, null))).toBe(false)
  })
})

describe('predictLine', () => {
  const lines = at(10, 15, 20, null)

  it('is the line after the last one whose time has come', () => {
    expect(predictLine(lines, 16)).toBe(2)
  })

  it('moves on a little before the time, so the tap is ready', () => {
    expect(predictLine(lines, 19.8)).toBe(3)
    expect(predictLine(lines, 19.7)).toBe(2)
  })

  it('stays on the last line at the end, and knows nothing before the first time', () => {
    expect(predictLine(at(10, 15), 100)).toBe(1)
    expect(predictLine(lines, 5)).toBe(-1)
    expect(predictLine(at(null, null), 50)).toBe(-1)
  })
})

describe('loopWindow', () => {
  it('runs from a moment before a timed line to a little after', () => {
    expect(loopWindow(at(10, 20), 1, 0, 200)).toEqual({ start: 18.5, end: 22 })
  })

  it('never starts before the song or runs past its end', () => {
    expect(loopWindow(at(1), 0, 0, 2.5)).toEqual({ start: 0, end: 2.5 })
  })

  it('places an untimed line between its neighbours', () => {
    expect(loopWindow(at(10, null, 20), 1, 0, 200)).toEqual({ start: 13.5, end: 17 })
  })

  it('places it after the line above, or before the line below', () => {
    expect(loopWindow(at(10, null), 1, 0, 200)).toEqual({ start: 10, end: 13.5 })
    expect(loopWindow(at(null, 20), 0, 0, 200)).toEqual({ start: 17, end: 20.5 })
  })

  it('falls back on the playhead when nothing is timed', () => {
    expect(loopWindow(at(null, null), 0, 42, 200)).toEqual({ start: 40.5, end: 44 })
  })
})

describe('stampTicks', () => {
  it('puts each timed line along the song, marking the ones out of order', () => {
    const lines = at(50, null, 25)
    expect(stampTicks(lines, 100, stampQuality(lines))).toEqual([
      { index: 0, time: 50, text: 'line 1', left: 50, error: false },
      { index: 2, time: 25, text: 'line 3', left: 25, error: true },
    ])
  })

  it('keeps marks on the bar when the length is unknown', () => {
    expect(stampTicks(at(5), 0)[0].left).toBe(100)
  })
})
