import { describe, expect, it } from 'vitest'
import { PERIODS, momentIcon, momentText } from '../model/moments.js'
import enCore from '../i18n/locales/en.js'
import enMore from '../i18n/locales/en-more.js'
import fr from '../i18n/locales/fr.js'
import es from '../i18n/locales/es.js'
import pt from '../i18n/locales/pt.js'
import de from '../i18n/locales/de.js'
import sw from '../i18n/locales/sw.js'

// English is in two files (i18n/locales/en-more.js): whole here.
const en = { ...enCore, ...enMore }

// Every moment Backend listens._insights can find, said in every language:
// a sentence with its numbers and names in it, never a key or a {gap}.

const SONG = { title: 'Calm Down', artists: ['Rema'] }
const MOMENTS = [
  { kind: 'more', percent: 40 },
  { kind: 'record_day', date: '2026-03-04', minutes: 210 },
  { kind: 'record_day', date: new Date().toISOString().slice(0, 10), minutes: 210 },
  { kind: 'streak', days: 9 },
  { kind: 'every_day', days: 7 },
  { kind: 'milestone_hours', hours: 100 },
  { kind: 'milestone_plays', plays: 1000 },
  { kind: 'new_in_top', artist: 'Zuchu', rank: 2 },
  { kind: 'climber', artist: 'Bensoul', from: 9, rank: 1 },
  { kind: 'comeback', song: SONG, days: 45 },
  { kind: 'new_artists', count: 1, artist: 'Nviiri' },
  { kind: 'new_artists', count: 6, artist: 'Nviiri' },
  { kind: 'top_song', song: SONG, plays: 12 },
  { kind: 'repeat', song: SONG, plays: 5 },
  { kind: 'loyal', artist: 'Sauti Sol', percent: 44 },
  { kind: 'night', percent: 61 },
  { kind: 'morning', percent: 52 },
  { kind: 'variety', songs: 80, artists: 31 },
  { kind: 'minutes', minutes: 1 },
  { kind: 'minutes', minutes: 95 },
]

function translator(messages) {
  return (key, params = {}) => {
    let msg = key.split('.').reduce((node, part) => (node == null ? node : node[part]), messages)
    if (typeof msg !== 'string') return key
    if (typeof params.count === 'number' && msg.includes(' | ')) {
      const [one, other] = msg.split(' | ')
      msg = params.count === 1 ? one : other
    }
    return msg.replace(/\{(\w+)\}/g, (all, name) => (name in params ? String(params[name]) : all))
  }
}

describe.each(Object.entries({ en, fr, es, pt, de, sw }))('moments in %s', (_code, messages) => {
  const t = translator(messages)
  it.each(PERIODS)('every kind, for %s', (period) => {
    for (const m of MOMENTS) {
      const text = momentText(m, period, t)
      expect(text, m.kind).not.toMatch(/^story\./)
      expect(text, m.kind).not.toMatch(/[{}]/)
      expect(text.length, m.kind).toBeGreaterThan(8)
    }
  })
  it('says last week against the week before it', () => {
    for (const period of ['day', 'week', 'month']) {
      const text = momentText({ kind: 'more', percent: 40 }, period, t, { ago: 1 })
      expect(text).not.toMatch(/[{}]|^story\./)
      expect(text).not.toBe(momentText({ kind: 'more', percent: 40 }, period, t))
    }
  })

  it('names the song, the artist and the numbers', () => {
    expect(momentText({ kind: 'repeat', song: SONG, plays: 5 }, 'day', t)).toContain('Calm Down')
    expect(momentText({ kind: 'climber', artist: 'Bensoul', from: 9, rank: 1 }, 'week', t)).toContain('Bensoul')
    expect(momentText({ kind: 'streak', days: 9 }, 'week', t)).toContain('9')
  })
  it('has the words the stories and the tiles use', () => {
    for (const p of PERIODS) {
      expect(messages.story.period[p]).toBeTruthy()
      expect(messages.story.startNow[p]).toBeTruthy()
    }
    for (const p of ['day', 'week', 'month']) {
      for (const group of ['intro', 'began', 'empty', 'more', 'less', 'topSong', 'partsTitle', 'summary', 'playlist']) {
        expect(messages.story[group][p], `${group}.${p}`).toBeTruthy()
      }
    }
    for (const part of ['night', 'morning', 'afternoon', 'evening']) expect(messages.story.part[part]).toBeTruthy()
  })
})

describe('moment icons', () => {
  it('every kind has one, and anything else the headphones', () => {
    for (const m of MOMENTS.filter((x) => x.kind !== 'minutes')) expect(momentIcon(m)).not.toBe('ph:headphones')
    expect(momentIcon({ kind: 'minutes' })).toBe('ph:headphones')
    expect(momentIcon(null)).toBe('ph:headphones')
  })
})
