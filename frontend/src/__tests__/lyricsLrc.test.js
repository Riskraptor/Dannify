import { describe, expect, it } from 'vitest'
import {
  hasStamps,
  splitWords,
  parseLrc,
  formatLrcTime,
  formatClock,
  formatShort,
  toSynced,
  toPlain,
  BLANK_STAMP,
} from '../model/lyrics/lrc'

describe('hasStamps', () => {
  it('sees a line time anywhere in the text', () => {
    expect(hasStamps('Intro\n[00:10.53]Kukosana na wewe')).toBe(true)
    expect(hasStamps('[1:05]short form')).toBe(true)
  })

  it('does not mistake words in brackets for times', () => {
    expect(hasStamps('[Chorus]\nKukosana na wewe')).toBe(false)
    expect(hasStamps('')).toBe(false)
    expect(hasStamps(null)).toBe(false)
  })
})

describe('splitWords', () => {
  it('trims every line and leaves blank ones out, whatever the line endings', () => {
    expect(splitWords('  one \r\n\r\ntwo\n   \nthree  ')).toEqual(['one', 'two', 'three'])
  })
})

describe('parseLrc', () => {
  it('reads each line with its time, in the order written', () => {
    expect(parseLrc('[00:10.53]Kukosana na wewe\n[00:15.50]Kuwa mbali na wewe')).toEqual([
      { time: 10.53, text: 'Kukosana na wewe' },
      { time: 15.5, text: 'Kuwa mbali na wewe' },
    ])
  })

  it('makes one line per time when a chorus is written once with several', () => {
    expect(parseLrc('[00:10.00][01:10.00]Halo, halo')).toEqual([
      { time: 10, text: 'Halo, halo' },
      { time: 70, text: 'Halo, halo' },
    ])
  })

  it('keeps an untimed line, and a timed empty one as a break', () => {
    expect(parseLrc('Intro\n[00:20.00]')).toEqual([
      { time: null, text: 'Intro' },
      { time: 20, text: '' },
    ])
  })

  it('skips the file details but keeps annotations that are lyrics', () => {
    const text = '[ar:Sauti Sol]\n[ti:Suzanna]\n[length:03:50]\n[Hook: Bien]\n[00:01.00]Suzanna'
    expect(parseLrc(text)).toEqual([
      { time: null, text: '[Hook: Bien]' },
      { time: 1, text: 'Suzanna' },
    ])
  })

  it('applies the file offset (positive is sooner) and never goes below zero', () => {
    expect(parseLrc('[offset:+500]\n[00:10.00]a\n[00:00.20]b')).toEqual([
      { time: 9.5, text: 'a' },
      { time: 0, text: 'b' },
    ])
  })

  it('drops word-by-word times from enhanced files and Windows line endings', () => {
    expect(parseLrc('[00:05.00]<00:05.00>Change <00:05.60>your <00:06.10>mind\r\n')).toEqual([
      { time: 5, text: 'Change your mind' },
    ])
  })

  it('reads three-digit minutes', () => {
    expect(parseLrc('[100:00.00]long mix')[0].time).toBe(6000)
  })
})

describe('time formats', () => {
  it('writes LRC times to the hundredth', () => {
    expect(formatLrcTime(0)).toBe('00:00.00')
    expect(formatLrcTime(65.3)).toBe('01:05.30')
    expect(formatLrcTime(10.536)).toBe('00:10.54')
  })

  it('carries a rounded-up second into the minute instead of writing :60', () => {
    expect(formatLrcTime(59.999)).toBe('01:00.00')
  })

  it('has nothing to say about a missing time', () => {
    expect(formatLrcTime(null)).toBe('')
    expect(formatLrcTime(NaN)).toBe('')
    expect(BLANK_STAMP).toBe('--:--.--')
  })

  it('shows the playhead to the millisecond, and nonsense as zero', () => {
    expect(formatClock(72.33)).toBe('01:12.330')
    expect(formatClock(-4)).toBe('00:00.000')
    expect(formatClock(Infinity)).toBe('00:00.000')
  })

  it('shows a short time the way the lyrics view does', () => {
    expect(formatShort(65.9)).toBe('1:05')
    expect(formatShort(0)).toBe('0:00')
    expect(formatShort(undefined)).toBe('0:00')
  })
})

describe('toSynced', () => {
  it('writes the timed lines in time order and leaves the untimed out', () => {
    const lines = [
      { text: 'second', time: 15.5 },
      { text: 'not yet', time: null },
      { text: 'first', time: 10.53 },
    ]
    expect(toSynced(lines)).toBe('[00:10.53]first\n[00:15.50]second')
  })

  it('writes a break as an empty timed line', () => {
    expect(toSynced([{ text: '♪', time: 30 }])).toBe('[00:30.00]')
  })
})

describe('toPlain', () => {
  it('keeps one blank line between verses, none at the ends', () => {
    const lines = [
      { text: '♪', time: null },
      { text: 'verse one', time: null },
      { text: '', time: null },
      { text: '♪', time: null },
      { text: 'verse two', time: null },
      { text: '♪', time: null },
    ]
    expect(toPlain(lines)).toBe('verse one\n\nverse two')
  })

  it('is empty for no lines', () => {
    expect(toPlain([])).toBe('')
  })
})

describe('reading what was written', () => {
  it('gives the same lines back', () => {
    const lines = [
      { text: 'Kukosana na wewe', time: 10.53 },
      { text: 'Kuwa mbali na wewe', time: 15.5 },
      { text: '', time: 61.07 },
    ]
    expect(parseLrc(toSynced(lines))).toEqual(lines)
  })
})
