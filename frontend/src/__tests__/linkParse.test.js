import { describe, expect, it } from 'vitest'
import { parseLink } from '../model/linkParse'

// Links as people paste them: from the Spotify app's Share button, from a
// browser's address bar, from YouTube and YouTube Music.

describe('Spotify links', () => {
  it('reads every kind, however it was shared', () => {
    expect(parseLink('https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=8f2c1a')).toEqual({
      source: 'spotify',
      kind: 'playlist',
      id: '37i9dQZF1DXcBWIGoYBM5M',
      url: 'https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M',
    })
    expect(parseLink('https://open.spotify.com/intl-fr/track/0kosUz0jePvjiz4ctmR6wL').kind).toBe('track')
    expect(parseLink('https://open.spotify.com/intl-pt-br/album/4yP0hdKOZPNshxUOjY0cZj').kind).toBe('album')
    expect(parseLink('open.spotify.com/artist/3wcj11K77LjEY1PkEazffa').kind).toBe('artist')
    expect(parseLink('spotify:track:4LPNkxES0zCGn6S2Y1vmJN')).toMatchObject({ kind: 'track', id: '4LPNkxES0zCGn6S2Y1vmJN' })
    expect(parseLink('  https://open.spotify.com/embed/playlist/37i9dQZF1DXcBWIGoYBM5M  ').kind).toBe('playlist')
  })

  it('knows a podcast when it sees one', () => {
    expect(parseLink('https://open.spotify.com/show/2MAi0BvDc6GTFvKFPXnkCL').kind).toBe('show')
  })

  it('is not fooled by a Spotify address inside another', () => {
    expect(parseLink('https://example.com/?next=open.spotify.com/track/0kosUz0jePvjiz4ctmR6wL')).toBe(null)
  })
})

describe('YouTube links', () => {
  it('plays a song from any of its addresses', () => {
    for (const url of [
      'https://music.youtube.com/watch?v=2cNFrajBk0k&si=x',
      'https://www.youtube.com/watch?v=2cNFrajBk0k&list=RD2cNFrajBk0k',
      'https://youtu.be/2cNFrajBk0k?t=30',
      'youtube.com/shorts/2cNFrajBk0k',
      'https://m.youtube.com/watch?v=2cNFrajBk0k',
    ]) {
      expect(parseLink(url)).toMatchObject({ source: 'youtube', kind: 'song', id: '2cNFrajBk0k' })
    }
  })

  it('opens playlists, albums and artists as pages', () => {
    expect(parseLink('https://music.youtube.com/playlist?list=RDCLAK5uy_m5qG4ExqLirXAM7qVrSJFgemYrNzuP4js')).toMatchObject({
      kind: 'playlist',
      id: 'RDCLAK5uy_m5qG4ExqLirXAM7qVrSJFgemYrNzuP4js',
    })
    expect(parseLink('https://music.youtube.com/browse/MPREb_mbf3ubmqUKB')).toMatchObject({ kind: 'album', id: 'MPREb_mbf3ubmqUKB' })
    expect(parseLink('https://music.youtube.com/browse/VLPLabc123')).toMatchObject({ kind: 'playlist', id: 'PLabc123' })
    expect(parseLink('https://music.youtube.com/channel/UCYQ9-fPNabcdefghijklmn')).toMatchObject({ kind: 'artist' })
  })
})

describe('what is not a link', () => {
  it('is searched for as words', () => {
    for (const text of ['sauti sol', 'spotify playlist afro', '', null, 'https://example.com/watch?v=2cNFrajBk0k', 'https://youtube.com/watch?v=short', 'https://open.spotify.com/user/someone']) {
      expect(parseLink(text)).toBe(null)
    }
  })
})
