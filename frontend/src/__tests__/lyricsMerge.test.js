import { describe, expect, it } from 'vitest'
import { mergeTimes, wordsOf, outText, BREAK } from '../model/lyricsMerge'

const timed = [
  { text: 'Kukosana na wewe', time: 10.5 },
  { text: 'Kuwa mbali na wewe', time: 15.5 },
  { text: 'Kutengana na wewe', time: 20.4 },
  { text: 'Nimetamani nilewe', time: 25.4 },
]

describe('mergeTimes', () => {
  it('keeps every time when nothing changed', () => {
    expect(mergeTimes(timed.map((l) => l.text), timed)).toEqual(timed)
  })

  it('keeps the time of a line whose typo was fixed', () => {
    const texts = ['Kukosana na wewe', 'Kuwa mbali nawe', 'Kutengana na wewe', 'Nimetamani nilewe']
    expect(mergeTimes(texts, timed).map((l) => l.time)).toEqual([10.5, 15.5, 20.4, 25.4])
  })

  it('leaves a new line untimed and keeps the others', () => {
    const texts = ['Kukosana na wewe', 'A brand new line', 'Kuwa mbali na wewe', 'Kutengana na wewe', 'Nimetamani nilewe']
    expect(mergeTimes(texts, timed).map((l) => l.time)).toEqual([10.5, null, 15.5, 20.4, 25.4])
  })

  it('drops the time of a removed line only', () => {
    const texts = ['Kukosana na wewe', 'Kutengana na wewe', 'Nimetamani nilewe']
    expect(mergeTimes(texts, timed).map((l) => l.time)).toEqual([10.5, 20.4, 25.4])
  })

  it('does not care about spacing or case', () => {
    const texts = ['kukosana  NA wewe', ...timed.slice(1).map((l) => l.text)]
    expect(mergeTimes(texts, timed)[0].time).toBe(10.5)
  })

  it('times nothing when there was no timing', () => {
    expect(mergeTimes(['a', 'b'], []).map((l) => l.time)).toEqual([null, null])
  })

  it('keeps a repeated chorus in order', () => {
    const song = [
      { text: 'Chorus', time: 1 },
      { text: 'Verse', time: 5 },
      { text: 'Chorus', time: 9 },
    ]
    expect(mergeTimes(['Chorus', 'Verse', 'Chorus'], song).map((l) => l.time)).toEqual([1, 5, 9])
  })
})

describe('breaks', () => {
  it('shows an instrumental break as ♪ and sends it as an empty line', () => {
    expect(wordsOf([{ text: 'a' }, { text: '' }, { text: 'b' }])).toBe(`a\n${BREAK}\nb`)
    expect(outText(BREAK)).toBe('')
    expect(outText(' words ')).toBe('words')
  })
})
