import { describe, expect, it } from 'vitest'
import { songKey } from '../model/songKey'

describe('songKey', () => {
  it('treats the versions of one song as that song', () => {
    const key = songKey('Commando')
    expect(songKey('Commando (Official Music Video)')).toBe(key)
    expect(songKey('Mavokali - Commando (Lyrics)')).toBe(key)
    expect(songKey('Commando ( Lyrics Video )')).toBe(key)
    expect(songKey('Commando [Official Audio]')).toBe(key)
    expect(songKey('Commando (feat. Rayvanny)')).toBe(key)
    expect(songKey('Commando ft. Rayvanny')).toBe(key)
    expect(songKey('COMMANDO')).toBe(key)
  })

  it('keeps a remix, a live take or another version apart', () => {
    const key = songKey('Commando')
    expect(songKey('Commando (Remix)')).not.toBe(key)
    expect(songKey('Commando (Official Remix)')).not.toBe(key)
    expect(songKey('Commando (Live)')).not.toBe(key)
    expect(songKey('Kuliko Jana (Acapella version)')).not.toBe(songKey('Kuliko Jana'))
    expect(songKey('Commando (Mapopo) (Rawi Beat - Slow Remix)')).not.toBe(songKey('Commando (Mapopo)'))
  })

  it('does not cut a title that only has a dash in it', () => {
    expect(songKey('Up - Down')).toBe('up down')
    expect(songKey('Sauti Sol - Suzanna', 'Sauti Sol')).toBe(songKey('Suzanna'))
  })

  it('reads titles in any script', () => {
    expect(songKey('夜に駆ける (Official Music Video)')).toBe(songKey('夜に駆ける'))
    expect(songKey('Beyoncé')).toBe(songKey('beyonce'))
  })
})
