import { describe, expect, it, beforeEach, vi } from 'vitest'

// A saved song whose file has gone: deleted here, deleted in Explorer, or
// moved. The real player model runs against a fake library this file
// controls, the way player.test.js drives it against a fake <audio>.

const api = vi.hoisted(() => ({
  downloadFileURL: (f) => `/downloads/${f}`,
  coverFileURL: (f) => `/cover/${f}`,
  streamURL: (id) => `/api/stream?id=${id}`,
  streamURLFromLink: (u) => `/api/stream?url=${u}`,
  resolveStream: null,
  getLyrics: null,
  getLyricVersions: null,
  getStreamInfo: null,
  getRadio: null,
}))
const lib = vi.hoisted(() => ({ tracks: null, loaded: null, error: null }))
const toasts = vi.hoisted(() => [])

vi.mock('/src/model/api', () => ({ default: api }))
vi.mock('/src/model/library', async () => {
  const { ref, shallowRef } = await import('vue')
  lib.tracks = shallowRef([])
  lib.loaded = ref(false)
  lib.error = ref(false)
  return { useLibrary: () => ({ tracks: lib.tracks, loaded: lib.loaded, error: lib.error }) }
})
vi.mock('/src/model/libraryIndex', () => ({
  useLibraryIndex: () => ({ load: () => {}, localFileFor: () => null }),
}))
vi.mock('/src/model/ui', async () => {
  const { ref } = await import('vue')
  return {
    useUi: () => ({ autoOpenLyrics: ref(false), panel: ref(null), panelFloating: ref(false), openPanel: () => {} }),
  }
})
vi.mock('/src/model/recent', () => ({ rememberPlayed: () => {} }))
vi.mock('/src/model/connectivity', () => ({
  reportNetworkFailure: () => Promise.resolve(true),
  useConnectivity: () => ({}),
  whenOnline: () => {},
}))
vi.mock('/src/model/toast', () => ({ toast: (msg, opts) => toasts.push({ msg, ...opts }) }))
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
    this.playbackRate = 1
    this.error = null
    FakeAudio.last = this
  }
  get currentSrc() {
    return this.src
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
    this.paused = false
    this.emit('play')
    return Promise.resolve()
  }
  pause() {
    this.paused = true
  }
  load() {}
}

const store = new Map()
globalThis.Audio = FakeAudio
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
}
globalThis.window = { addEventListener: () => {}, removeEventListener: () => {}, location: { href: 'http://localhost/' } }

const vid = (i) => `vid${String(i).padStart(8, '0')}`
const fileOf = (i) => `Artist/Song ${i}.dnf`
const saved = (i, { online = true } = {}) => ({
  type: 'local',
  file: fileOf(i),
  url: `/downloads/${fileOf(i)}`,
  cover: `/cover/${fileOf(i)}`,
  title: `Song ${i}`,
  artist: 'Artist',
  duration: 200,
  video_id: online ? vid(i) : '',
})
const inLibrary = (...ids) => ids.map((i) => ({ file: fileOf(i), video_id: vid(i), title: `Song ${i}` }))
const flush = () => new Promise((r) => setTimeout(r, 0))

let P

beforeEach(async () => {
  store.clear()
  toasts.length = 0
  vi.resetModules()
  api.resolveStream = vi.fn(() => Promise.resolve({ data: { cover_url: 'https://art/cover.jpg' } }))
  api.getLyrics = vi.fn(() => Promise.resolve({ data: {} }))
  api.getLyricVersions = vi.fn(() => Promise.resolve({ data: { versions: [] } }))
  api.getStreamInfo = vi.fn(() => Promise.resolve({ data: {} }))
  api.getRadio = vi.fn(() => Promise.resolve({ data: { songs: [] } }))
  globalThis.fetch = vi.fn(() => Promise.resolve({ status: 404 }))
  P = (await import('/src/model/player.js')).usePlayer()
})

async function libraryReads(tracks) {
  lib.tracks.value = tracks
  lib.loaded.value = true
  await flush()
}

describe('the queue, when the library is read again', () => {
  it('plays a deleted song from YouTube Music instead', async () => {
    P.setPlaylist([saved(0), saved(1), saved(2)], { startIndex: 0 })
    await libraryReads(inLibrary(0, 2))
    const next = P.playlist.value[1]
    expect(next.type).toBe('stream')
    expect(next.url).toBe(`/api/stream?id=${vid(1)}`)
    expect(next.title).toBe('Song 1')
    expect(P.playlist.value[2].type).toBe('local')
  })

  it('takes a deleted song with nowhere else to play from out of the queue', async () => {
    P.setPlaylist([saved(0), saved(1, { online: false }), saved(2)], { startIndex: 2 })
    await libraryReads(inLibrary(0, 2))
    expect(P.playlist.value.map((t) => t.title)).toEqual(['Song 0', 'Song 2'])
    expect(P.currentTrack.value.title).toBe('Song 2')
  })

  it('follows a song that was only moved', async () => {
    P.setPlaylist([saved(0), saved(1)], { startIndex: 0 })
    await libraryReads([...inLibrary(0), { file: 'Elsewhere/Song 1.dnf', video_id: vid(1) }])
    expect(P.playlist.value[1].type).toBe('local')
    expect(P.playlist.value[1].file).toBe('Elsewhere/Song 1.dnf')
  })

  it('leaves the playing song alone', async () => {
    P.setPlaylist([saved(0), saved(1)], { startIndex: 0 })
    const playing = P.currentTrack.value
    await libraryReads(inLibrary(1))
    expect(P.currentTrack.value).toStrictEqual(playing)
  })

  it('does nothing with a library that failed to load', async () => {
    P.setPlaylist([saved(0), saved(1)], { startIndex: 0 })
    lib.error.value = true
    await libraryReads([])
    expect(P.playlist.value[1].type).toBe('local')
  })
})

describe('a saved song that turns out not to be there', () => {
  it('carries on from YouTube Music, where it was, without an error', async () => {
    P.setPlaylist([saved(0), saved(1)], { startIndex: 0 })
    const audio = FakeAudio.last
    audio.error = { code: 4 }
    audio.emit('error')
    await flush()
    await flush()
    expect(P.currentIndex.value).toBe(0)
    expect(P.currentTrack.value.type).toBe('stream')
    expect(FakeAudio.last.src).toBe(`/api/stream?id=${vid(0)}`)
    expect(toasts.filter((x) => x.tone === 'error')).toEqual([])
    expect(api.resolveStream).toHaveBeenCalledTimes(1)
  })

  it('says so once, moves on and drops it when it has no online copy', async () => {
    P.setPlaylist([saved(0, { online: false }), saved(1)], { startIndex: 0 })
    const audio = FakeAudio.last
    audio.error = { code: 4 }
    audio.emit('error')
    await flush()
    await flush()
    expect(P.playlist.value.map((t) => t.title)).toEqual(['Song 1'])
    expect(P.currentTrack.value.title).toBe('Song 1')
    expect(toasts.map((x) => x.msg)).toEqual(['player.fileGone'])
  })

  it('still offers a repair for a file that is there but will not play', async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ status: 200 }))
    P.setPlaylist([saved(0), saved(1)], { startIndex: 0 })
    const audio = FakeAudio.last
    audio.error = { code: 3 }
    audio.emit('error')
    await flush()
    await flush()
    expect(toasts.map((x) => x.msg)).toEqual(['player.fileUnreadable'])
    expect(P.currentTrack.value.title).toBe('Song 1')
    expect(P.playlist.value).toHaveLength(2)
  })
})
