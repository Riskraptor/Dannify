import { describe, expect, it } from 'vitest'
import { personaOf } from '../model/recapPersona'

const hours = (at, seconds) => {
  const h = Array(24).fill(0)
  for (const [hour, s] of at) h[hour] = s
  return seconds ? h : h
}

const base = {
  seconds: 1000,
  hours: hours([[14, 1000]]),
  top_artists: [{ name: 'Sauti Sol', seconds: 200 }],
  top_songs: [{ plays: 5, title: 'Suzanna' }],
  new_artists: 2,
  longest_streak: 3,
  songs: 40,
  artists: 12,
}

describe('your listening personality', () => {
  it('a night owl plays most of it late', () => {
    expect(personaOf({ ...base, hours: hours([[23, 300], [1, 100], [14, 600]]) }).id).toBe('nightOwl')
  })

  it('an early riser plays most of it in the morning', () => {
    expect(personaOf({ ...base, hours: hours([[7, 400], [14, 600]]) }).id).toBe('earlyBird')
  })

  it('a devoted fan gives one artist a big share, and is told how big', () => {
    const p = personaOf({ ...base, top_artists: [{ name: 'Tems', seconds: 400 }] })
    expect(p).toMatchObject({ id: 'devoted', params: { artist: 'Tems', percent: 40 } })
  })

  it('a repeater plays one song over and over', () => {
    const p = personaOf({ ...base, top_songs: [{ plays: 30, title: 'Suzanna' }] }, [{ title: 'Suzanna' }])
    expect(p).toMatchObject({ id: 'repeater', params: { title: 'Suzanna', count: 30 } })
  })

  it('an explorer, a daily listener, and otherwise a music lover', () => {
    expect(personaOf({ ...base, new_artists: 20 }).id).toBe('explorer')
    expect(personaOf({ ...base, longest_streak: 21 }).id).toBe('daily')
    expect(personaOf(base)).toMatchObject({ id: 'lover', params: { count: 40, artists: 12 } })
  })

  it('a year with nothing in it is still a music lover', () => {
    expect(personaOf(null).id).toBe('lover')
  })
})
