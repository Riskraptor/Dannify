import { describe, expect, it } from 'vitest'
import { mixCovers, recentlyAdded } from '../model/mixRules'

describe('recentlyAdded', () => {
  it('lists the newest playable songs first', () => {
    const tracks = [
      { file: 'a.dnf', added: 10 },
      { file: 'b.dnf', added: 30 },
      { file: 'c.dnf', added: 20, problem: 'locked' },
      { file: '', added: 40 },
      { file: 'd.dnf', added: 25 },
    ]
    expect(recentlyAdded(tracks).map((t) => t.file)).toEqual(['b.dnf', 'd.dnf', 'a.dnf'])
  })

  it('keeps to the limit and leaves the library as it was', () => {
    const tracks = Array.from({ length: 50 }, (_, i) => ({ file: `${i}.dnf`, added: i }))
    const copy = [...tracks]
    expect(recentlyAdded(tracks, 5).map((t) => t.added)).toEqual([49, 48, 47, 46, 45])
    expect(tracks).toEqual(copy)
  })
})

describe('mixCovers', () => {
  it('takes one cover per album, in order', () => {
    const rows = [
      { cover: 'c1', album: 'Sauce', primaryArtist: 'Sauti Sol' },
      { cover: 'c2', album: 'Sauce', primaryArtist: 'Sauti Sol' },
      { cover: 'c3', album: 'Other', primaryArtist: 'Sauti Sol' },
      { cover: 'c4', album: '', primaryArtist: 'Nviiri' },
      { cover: 'c5', album: 'Sauce', primaryArtist: 'Someone Else' },
      { cover: 'c6', album: 'Late' },
    ]
    expect(mixCovers(rows)).toEqual(['c1', 'c3', 'c4', 'c5'])
    expect(mixCovers(rows, 2)).toEqual(['c1', 'c3'])
  })

  it('skips rows without a cover and copes with none', () => {
    expect(mixCovers([{ album: 'A' }, null, { cover: 'x' }])).toEqual(['x'])
    expect(mixCovers(null)).toEqual([])
  })
})
