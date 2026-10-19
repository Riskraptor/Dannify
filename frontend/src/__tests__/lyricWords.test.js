import { describe, expect, it } from 'vitest'
import { lineWords, splitLineWords, syllables, wordAt } from '/src/model/lyrics/words'

describe('syllables', () => {
  it('counts vowel groups, at least one for any word', () => {
    expect(syllables('hello')).toBe(2)
    expect(syllables('beautiful')).toBe(3)
    expect(syllables('rhythm')).toBe(1)
    expect(syllables('été')).toBe(2)
    expect(syllables('')).toBe(0)
    expect(syllables('…')).toBe(0)
  })

  it('counts each character of a script written without spaces', () => {
    expect(syllables('사랑해')).toBe(3)
    expect(syllables('ありがとう')).toBe(5)
  })
})

describe('splitLineWords', () => {
  it('keeps the space after each word so the line joins back', () => {
    const words = splitLineWords('Hold me  close')
    expect(words).toEqual(['Hold ', 'me  ', 'close'])
  })

  it('splits a line in a script without spaces into characters', () => {
    expect(splitLineWords('사랑해')).toEqual(['사', '랑', '해'])
  })
})

describe('lineWords', () => {
  it('follows word times that came with the lyrics', () => {
    const line = {
      time: 10,
      text: 'Hello bright world',
      words: [
        { time: 10, text: 'Hello ' },
        { time: 10.5, text: 'bright ' },
        { time: 11.2, text: 'world' },
      ],
      end: 12,
    }
    const { words, exact } = lineWords(line, 14)
    expect(exact).toBe(true)
    expect(words.map((w) => w.time)).toEqual([10, 10.5, 11.2])
    expect(words[0].dur).toBeCloseTo(0.5)
    expect(words[2].dur).toBeCloseTo(0.8)
  })

  it('never holds a word past the next line, or longer than a held note', () => {
    const line = { time: 10, text: 'Oh', words: [{ time: 10, text: 'Oh' }] }
    expect(lineWords(line, 11).words[0].dur).toBeCloseTo(1)
    expect(lineWords(line, 30).words[0].dur).toBeCloseTo(2.5)
  })

  it('spreads an untimed line by syllables, inside the gap', () => {
    const { words, exact } = lineWords({ time: 20, text: 'Hello beautiful world' }, 30)
    expect(exact).toBe(false)
    expect(words).toHaveLength(3)
    expect(words[0].time).toBe(20)
    // Six syllables at an unhurried pace, not stretched over the long gap.
    const end = words[2].time + words[2].dur
    expect(end).toBeGreaterThan(21)
    expect(end).toBeLessThan(22)
    // Longer words take longer.
    expect(words[1].dur).toBeGreaterThan(words[0].dur)
  })

  it('fits a line into a short gap', () => {
    const { words } = lineWords({ time: 5, text: 'one two three four five six seven' }, 6.5)
    const last = words[words.length - 1]
    expect(last.time + last.dur).toBeLessThanOrEqual(6.4)
  })

  it('has no words for a blank or untimed line', () => {
    expect(lineWords({ time: 3, text: '' }, 5).words).toEqual([])
    expect(lineWords({ time: null, text: 'Hi' }, 5).words).toEqual([])
    expect(lineWords(null, 5).words).toEqual([])
  })
})

describe('wordAt', () => {
  const words = [{ time: 1 }, { time: 2 }, { time: 3 }]
  it('is the last word started', () => {
    expect(wordAt(words, 0.5)).toBe(-1)
    expect(wordAt(words, 1)).toBe(0)
    expect(wordAt(words, 2.5)).toBe(1)
    expect(wordAt(words, 9)).toBe(2)
  })
})
