import { describe, expect, it, beforeEach, vi } from 'vitest'

// The queue saved on the way out and resumed on the next start. Each test
// drives the real player model, "restarts" by loading a fresh copy of it over
// the same storage, and checks the resumed queue against what was saved.

const api = vi.hoisted(() => ({
  downloadFileURL: (f) => `/downloads/${f}`,
  coverFileURL: (f) => `/cover/${f}`,
  streamURL: (id) => `/api/stream?video_id=${id}`,
  streamURLFromLink: (u) => `/api/stream?url=${u}`,
  getLyrics: null,
  getLyricVersions: null,
  getStreamInfo: null,
  getRadio: null,
  resolveStream: null,
  saveLyricsOffset: null,
  download: null,
}))

vi.mock('/src/model/api', () => ({ default: api }))
vi.mock('/src/model/libraryIndex', () => ({
  useLibraryIndex: () => ({ load: () => {}, localFileFor: () => null }),
}))
vi.mock('/src/model/ui', async () => {
  const { ref } = await import('vue')
  return {
    useUi: () => ({
      autoOpenLyrics: ref(false),
      panel: ref(null),
      panelFloating: ref(false),
      openPanel: () => {},
    }),
  }
})
vi.mock('/src/model/recent', () => ({ rememberPlayed: () => {} }))
vi.mock('/src/model/connectivity', () => ({
  reportNetworkFailure: () => Promise.resolve(true),
  useConnectivity: () => ({}),
  whenOnline: () => {},
}))
vi.mock('/src/model/toast', () => ({ toast: () => {} }))
vi.mock('/src/model/repair', () => ({ repairFiles: () => {} }))
vi.mock('/src/i18n', () => ({ t: (k) => k }))

class FakeAudio {
  constructor() {
    this.listeners = {}
    this.paused = true
    this.src = ''
    this.currentTime = 0
    this.duration = NaN
    this.volume = 1
    this.muted = false
    this.playbackRate = 1
    FakeAudio.last = this
  }
  addEventListener(type, fn) {
    ;(this.listeners[type] ||= []).push(fn)
  }
  removeEventListener(type, fn) {
    this.listeners[type] = (this.listeners[type] || []).filter((f) => f !== fn)
  }
  emit(type) {
    for (const fn of [...(this.listeners[type] || [])]) fn()
  }
  play() {
    if (this.paused) {
      this.paused = false
      this.emit('play')
    }
    return Promise.resolve()
  }
  pause() {
    if (!this.paused) {
      this.paused = true
      this.emit('pause')
    }
  }
  removeAttribute() {}
  load() {}
}

const store = new Map()
const winListeners = {}
globalThis.Audio = FakeAudio
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
}
class FakeMetadata {
  constructor(init) {
    Object.assign(this, init)
  }
}
globalThis.window = {
  addEventListener: (type, fn) => (winListeners[type] ||= []).push(fn),
  removeEventListener: () => {},
  dispatchEvent: () => true,
  location: { href: 'http://localhost/' },
  MediaMetadata: FakeMetadata,
}
const mediaSession = { metadata: null, playbackState: 'none', setActionHandler: () => {} }
Object.defineProperty(globalThis, 'navigator', {
  value: { mediaSession },
  configurable: true,
  writable: true,
})

const flush = () => new Promise((r) => setTimeout(r, 0))

// A song as YouTube Music search hands it over: everything the queue, the
// play bar and the artist links read.
const vid = (i) => `yt${String(i).padStart(9, '0')}`
const song = (i, extra = {}) => ({
  song_id: vid(i),
  video_id: vid(i),
  name: `Song ${i}`,
  artists: ['Lead Artist', `Guest ${i}`],
  album_name: `Album ${i}`,
  album_id: `MPREb_album${i}`,
  cover_url: `https://yt3.googleusercontent.com/cover-${i}=w600-h600-l90-rj`,
  duration: 200 + i,
  url: `https://music.youtube.com/watch?v=${vid(i)}`,
  explicit: i % 2 === 0,
  like_status: i === 1 ? 'LIKE' : '',
  year: '2021',
  release_date: '',
  source: 'youtube',
  artist_ids: [
    { name: 'Lead Artist', id: 'UClead' },
    { name: `Guest ${i}`, id: `UCguest${i}` },
  ],
  ...extra,
})

let P
let mod

async function load() {
  for (const k of Object.keys(winListeners)) delete winListeners[k]
  vi.resetModules()
  mod = await import('/src/model/player.js')
  P = mod.usePlayer()
}

// What the window does as it closes.
function closeWindow() {
  for (const fn of winListeners.pagehide || []) fn()
}

// Close, and come back as the next launch does.
async function restart() {
  closeWindow()
  mediaSession.metadata = null
  await load()
  const ok = P.restoreSession()
  await flush()
  return ok
}

// What every view reads off a queue entry. Loudness and gain are measured
// again, so they are not part of what a restart has to bring back, and an
// empty detail on the song reads the same as one that is not there.
function shape(track) {
  if (!track) return track
  const { gain, loudness, ...rest } = track // eslint-disable-line no-unused-vars
  const out = JSON.parse(JSON.stringify(rest))
  if (out._song) {
    for (const [k, v] of Object.entries(out._song)) if (v === '') delete out._song[k]
  }
  return out
}

beforeEach(async () => {
  store.clear()
  api.getLyrics = vi.fn(() => Promise.resolve({ data: {} }))
  api.getLyricVersions = vi.fn(() => Promise.resolve({ data: { versions: [] } }))
  api.getStreamInfo = vi.fn(() => Promise.resolve({ data: { loudness_db: 2 } }))
  api.getRadio = vi.fn(() => Promise.resolve({ data: { songs: [] } }))
  api.resolveStream = vi.fn(() => Promise.reject(new Error('offline')))
  api.saveLyricsOffset = vi.fn(() => Promise.resolve())
  api.download = vi.fn(() => Promise.resolve())
  await load()
})

describe('a resumed queue is as rich as the one that was saved', () => {
  it('brings back every YouTube detail of every track, and where it was', async () => {
    P.playStreamSongs([song(0), song(1), song(2)], 1)
    await flush()
    P.seek(42)
    const before = P.playlist.value.map(shape)

    expect(await restart()).toBe(true)

    expect(P.playlist.value.map(shape)).toEqual(before)
    expect(P.currentIndex.value).toBe(1)
    expect(P.currentTime.value).toBe(42)
    const cur = P.currentTrack.value
    expect(cur._song.artist_ids).toEqual(song(1).artist_ids)
    expect(cur._song.album_id).toBe('MPREb_album1')
    expect(cur._song.like_status).toBe('LIKE')
    expect(cur.url).toBe(`/api/stream?video_id=${vid(1)}`)
  })

  it('tells the lyrics lookup and the system media controls about the resumed track', async () => {
    P.playStreamSongs([song(0), song(1)], 1)
    await flush()

    await restart()

    expect(api.getLyrics).toHaveBeenLastCalledWith({
      title: 'Song 1',
      artist: 'Lead Artist, Guest 1',
      album: 'Album 1',
      duration: 201,
    })
    expect(mediaSession.metadata.title).toBe('Song 1')
    expect(mediaSession.metadata.artist).toBe('Lead Artist, Guest 1')
    expect(mediaSession.metadata.artwork[0].src).toBe(song(1).cover_url)
  })

  it('keeps a saved song saved, with its picture rebuilt from its path', async () => {
    P.setPlaylist(['Artist - Title.m4a'], { startIndex: 0 })
    await flush()

    await restart()

    const cur = P.currentTrack.value
    expect(cur.type).toBe('local')
    expect(cur.file).toBe('Artist - Title.m4a')
    expect(cur.url).toBe('/downloads/Artist - Title.m4a')
    expect(cur.cover).toBe('/cover/Artist - Title.m4a')
    expect(cur.title).toBe('Title')
    expect(cur.artist).toBe('Artist')
  })

  it('keeps an artist whose own name has a comma in it whole', async () => {
    const odd = song(3, {
      artists: ['Tyler, The Creator'],
      artist_ids: [{ name: 'Tyler, The Creator', id: 'UCtyler' }],
    })
    P.playStreamSongs([odd], 0)
    await flush()

    await restart()

    expect(P.currentTrack.value._song.artists).toEqual(['Tyler, The Creator'])
  })
})

describe('the saved queue stays small', () => {
  it('stores each detail once, and nothing measured again on the next start', async () => {
    P.playStreamSongs([song(0), song(1), song(2)], 0)
    await flush()
    closeWindow()

    const raw = [...store.entries()].find(([k]) => k.startsWith('dannify.session'))[1]
    // The picture was on the track and on the song: written twice, it was a
    // third of everything stored.
    expect(raw.split(song(1).cover_url).length - 1).toBe(1)
    expect(raw).not.toMatch(/"gain"/)
    expect(raw).not.toMatch(/"loudness"/)
    // The address is rebuilt from the id on the way back in.
    expect(raw).not.toContain('/api/stream?')
    // Against the whole tracks that used to be written.
    const whole = JSON.stringify(P.playlist.value)
    expect(raw.length).toBeLessThan(whole.length * 0.6)
  })

  it('cuts down what would not fit, and leaves out pictures held in the address itself', async () => {
    P.playStreamSongs([song(0, { name: 'x'.repeat(5000), cover_url: `data:image/png;base64,${'A'.repeat(50000)}` })], 0)
    await flush()

    await restart()

    const cur = P.currentTrack.value
    expect(cur.title.length).toBeLessThanOrEqual(500)
    expect(cur.cover).toBe('')
  })

  it('a long queue resumes on the track that was playing, not on the 200th', async () => {
    const songs = Array.from({ length: 300 }, (_, i) => song(i))
    P.playStreamSongs(songs, 250)
    await flush()

    await restart()

    expect(P.currentTrack.value.title).toBe('Song 250')
    expect(P.playlist.value.length).toBe(200)
    // All of what was still to come, and as much as fits of what played.
    expect(P.playlist.value[199].title).toBe('Song 299')
  })

  it('a cut queue keeps more of what is to come than of what has played', async () => {
    const songs = Array.from({ length: 300 }, (_, i) => song(i))
    P.playStreamSongs(songs, 100)
    await flush()

    await restart()

    expect(P.currentTrack.value.title).toBe('Song 100')
    expect(P.playlist.value[0].title).toBe('Song 50')
    expect(P.playlist.value[199].title).toBe('Song 249')
  })
})

describe('a queue saved by an older version', () => {
  function writeOld(tracks, index = 0) {
    store.set(
      'dannify.session.v1',
      JSON.stringify({ tracks, index, time: 7, ts: Date.now() })
    )
  }

  it('comes back as it was, and is written in the new form', async () => {
    P.playStreamSongs([song(0), song(1)], 1)
    await flush()
    const before = P.playlist.value.map(shape)
    // What the old version wrote: every track whole, gain and all.
    writeOld(P.playlist.value.map((t) => JSON.parse(JSON.stringify(t))), 1)
    for (const k of [...store.keys()]) if (k.startsWith('dannify.session') && k !== 'dannify.session.v1') store.delete(k)

    await load()
    expect(P.restoreSession()).toBe(true)
    await flush()

    expect(P.playlist.value.map(shape)).toEqual(before)
    expect(P.currentTime.value).toBe(7)
    closeWindow()
    expect(store.has('dannify.session.v1')).toBe(false)
  })

  it('fills in the details an old entry never had, for the track in the player', async () => {
    writeOld([
      { type: 'stream', url: `/api/stream?video_id=${vid(5)}`, video_id: vid(5), song_id: vid(5), title: '', artist: '' },
      { type: 'stream', url: `/api/stream?video_id=${vid(6)}`, video_id: vid(6), song_id: vid(6), title: '', artist: '' },
    ])
    api.resolveStream = vi.fn((url) => {
      const id = url.split('v=')[1]
      const n = Number(id.slice(2))
      const { artist_ids, album_id, ...plain } = song(n) // eslint-disable-line no-unused-vars
      return Promise.resolve({ data: { ...plain, album_name: '' } })
    })

    // Counted per song: a copy of the player from an earlier test can still
    // have a timer running that reaches the same stand-in.
    const asked = (n) =>
      api.resolveStream.mock.calls.filter(([url]) => url === `https://music.youtube.com/watch?v=${vid(n)}`).length

    await load()
    P.restoreSession()
    await flush()
    await flush()

    // Asked for the one on screen only: the rest wait until they come up.
    expect(asked(5)).toBe(1)
    expect(asked(6)).toBe(0)
    const cur = P.currentTrack.value
    expect(cur.title).toBe('Song 5')
    expect(cur.artist).toBe('Lead Artist, Guest 5')
    expect(cur.cover).toBe(song(5).cover_url)
    expect(cur._song.name).toBe('Song 5')
    expect(cur._song.artists).toEqual(['Lead Artist', 'Guest 5'])
    expect(mediaSession.metadata.title).toBe('Song 5')
    // Looked up once there was something to look up by.
    const lookups = api.getLyrics.mock.calls.map((c) => c[0]).filter((p) => !p.title || p.title === 'Song 5')
    expect(lookups).toEqual([expect.objectContaining({ title: 'Song 5', artist: 'Lead Artist, Guest 5' })])

    P.next()
    await flush()
    await flush()
    expect(asked(6)).toBe(1)
    expect(P.currentTrack.value.title).toBe('Song 6')
    // And the filled-in details are what is saved next time.
    await restart()
    expect(P.playlist.value[0].title).toBe('Song 5')
    expect(P.playlist.value[0].cover).toBe(song(5).cover_url)
  })

  it('still plays an old entry when its details cannot be had', async () => {
    writeOld([{ type: 'stream', url: `/api/stream?video_id=${vid(8)}`, video_id: vid(8), title: 'Kept', artist: '' }])

    await load()
    expect(P.restoreSession()).toBe(true)
    await flush()

    expect(P.currentTrack.value.title).toBe('Kept')
    expect(P.currentTrack.value.url).toBe(`/api/stream?video_id=${vid(8)}`)
  })
})
