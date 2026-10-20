import { describe, expect, it } from 'vitest'
import { insertPart, lineSpan, partLabel, repeatLines } from '../model/lyrics/repeat'

const SONG = 'Verse one\nChorus a\nChorus b\nVerse two'
const at = (text, s) => text.indexOf(s)

describe('lineSpan', () => {
  it('takes whole lines however the selection falls', () => {
    const from = at(SONG, 'orus a')
    const to = at(SONG, 'us b') + 2
    expect(SONG.slice(...Object.values(lineSpan(SONG, from, to)))).toBe('Chorus a\nChorus b')
  })

  it('leaves out the next line when the selection only reached its start', () => {
    const from = at(SONG, 'Chorus a')
    const to = at(SONG, 'Chorus b')
    const { start, end } = lineSpan(SONG, from, to)
    expect(SONG.slice(start, end)).toBe('Chorus a')
  })

  it('is the cursor’s line with nothing selected', () => {
    const { start, end } = lineSpan(SONG, at(SONG, 'two'))
    expect(SONG.slice(start, end)).toBe('Verse two')
  })
})

describe('repeatLines', () => {
  it('puts the chorus again right below it, and selects the copy', () => {
    const r = repeatLines(SONG, at(SONG, 'Chorus a'), at(SONG, 'Verse two') - 1)
    expect(r.text).toBe('Verse one\nChorus a\nChorus b\nChorus a\nChorus b\nVerse two')
    expect(r.part).toBe('Chorus a\nChorus b')
    expect(r.text.slice(r.selStart, r.selEnd)).toBe('Chorus a\nChorus b')
  })

  it('repeats again from the copy, so pressing twice gives three', () => {
    const once = repeatLines(SONG, at(SONG, 'Chorus a'), at(SONG, 'Verse two') - 1)
    const twice = repeatLines(once.text, once.selStart, once.selEnd)
    expect(twice.text.match(/Chorus a/g)).toHaveLength(3)
  })

  it('does nothing on an empty line', () => {
    expect(repeatLines('a\n\nb', 2)).toBeNull()
  })

  it('works on the last line, with no newline after it', () => {
    expect(repeatLines('a\nlast', 3).text).toBe('a\nlast\nlast')
  })
})

describe('insertPart', () => {
  it('fills an empty line with the part', () => {
    const r = insertPart('Verse\n\nOutro', 6, 'Ch a\nCh b')
    expect(r.text).toBe('Verse\nCh a\nCh b\nOutro')
    expect(r.text.slice(r.selStart, r.selEnd)).toBe('Ch a\nCh b')
  })

  it('goes below a line with words on it', () => {
    expect(insertPart('Verse\nOutro', 2, 'Ch').text).toBe('Verse\nCh\nOutro')
  })

  it('does nothing without a part', () => {
    expect(insertPart('x', 0, '  ')).toBeNull()
  })
})

describe('partLabel', () => {
  it('is the first words, cut with an ellipsis', () => {
    expect(partLabel('\nHebu nieleze kwa sauti ya upole\nAkili')).toBe('Hebu nieleze kwa sauti ya…')
    expect(partLabel('Short')).toBe('Short')
  })
})
