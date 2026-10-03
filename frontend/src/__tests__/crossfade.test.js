import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'

// Crossfade and gapless, driven through the real player model with two decks
// and a stand-in for Web Audio. Each test gets a fresh copy of the module and
// fake timers, so what happens near the end of a song can be walked through
// second by second.

const api = vi.hoisted(() => ({
  downloadFileURL: (f) => `/downloads/${f}`,
  coverFileURL: (f) => `/cover/${f}`,
  streamURL: (id) => `/api/stream?id=${id}`,
  streamURLFromLink: (u) => `/api/stream?url=${u}`,
  getLyrics: null,
  getLyricVersions: null,
  getStreamInfo: null,
  getRadio: null,
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


// Two decks need Web Audio: a stand-in that does what the engine asks of it.
class Param {
  constructor(v = 1) {
    this.value = v
  }
  cancelScheduledValues() {}
  setTargetAtTime(v) {
    this.value = v
  }
  setValueAtTime(v) {
    this.value = v
  }
  linearRampToValueAtTime(v) {
    this.value = v
  }
  setValueCurveAtTime(curve) {
    this.value = curve[curve.length - 1]
  }
}
class Node {
  constructor() {
    this.gain = new Param(1)
    this.frequency = new Param(0)
    this.Q = new Param(1)
    this.threshold = new Param(0)
    this.knee = new Param(0)
    this.ratio = new Param(1)
    this.attack = new Param(0)
    this.release = new Param(0)
  }
  connect(n) {
    return n
  }
}
class FakeContext {
  constructor() {
    this.currentTime = 0
    this.state = 'running'
    this.destination = new Node()
  }
  createGain() {
    return new Node()
  }
  createBiquadFilter() {
    return new Node()
  }
  createDynamicsCompressor() {
    return new Node()
  }
  createMediaElementSource() {
    return new Node()
  }
  resume() {
    return Promise.resolve()
  }
}

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
    this.preload = ''
    this.playCalls = 0
    this.loads = 0
    FakeAudio.all.push(this)
  }
  addEventListener(type, fn) {
    ;(this.listeners[type] ||= []).push(fn)
  }
  removeEventListener() {}
  emit(type) {
    for (const fn of [...(this.listeners[type] || [])]) fn()
  }
  play() {
    this.playCalls += 1
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
  load() {
    this.loads += 1
  }
  removeAttribute(name) {
    if (name === 'src') this.src = ''
  }
}
FakeAudio.all = []

const store = new Map()
globalThis.Audio = FakeAudio
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
}
globalThis.window = {
  addEventListener: () => {},
  removeEventListener: () => {},
  location: { href: 'http://localhost/' },
  AudioContext: FakeContext,
}

const vid = (i) => `vid${String(i).padStart(8, '0')}`
const track = (i) => ({
  type: 'stream',
  url: `/api/stream?id=${vid(i)}`,
  video_id: vid(i),
  song_id: vid(i),
  title: `Song ${i}`,
  artist: 'Artist',
  duration: 200,
})
const tracks = (n) => Array.from({ length: n }, (_, i) => track(i))

let P
const title = () => P.currentTrack.value && P.currentTrack.value.title
const playing = () => FakeAudio.all.filter((a) => !a.paused && a.src)

// Move the playing song's clock to *t* seconds, as the element would.
function at(t) {
  const a = FakeAudio.all.find((x) => x.src === P.currentTrack.value.url && !x.paused)
  a.currentTime = t
  a.emit('timeupdate')
  return a
}

beforeEach(async () => {
  vi.useFakeTimers()
  store.clear()
  FakeAudio.all = []
  api.getLyrics = vi.fn(() => Promise.resolve({ data: {} }))
  api.getLyricVersions = vi.fn(() => Promise.resolve({ data: { versions: [] } }))
  api.getStreamInfo = vi.fn(() => Promise.resolve({ data: { loudness_db: 14 } }))
  api.getRadio = vi.fn(() => Promise.resolve({ data: { songs: [] } }))
  vi.resetModules()
  P = (await import('/src/model/player.js')).usePlayer()
})

afterEach(() => {
  vi.useRealTimers()
})

async function startQueue(n = 3) {
  P.setPlaylist(tracks(n), { startIndex: 0 })
  await vi.advanceTimersByTimeAsync(5)
  expect(P.hasEngine()).toBe(true)
}

describe('crossfade', () => {
  it('loads the next song on the other deck ahead of time, then fades across', async () => {
    P.setCrossfade(6)
    await startQueue()
    const first = at(170) // 30 s left: nothing yet
    expect(FakeAudio.all.filter((a) => a.src === track(1).url)).toHaveLength(0)
    at(185) // 15 s left: the next song is loaded, not played
    const second = FakeAudio.all.find((a) => a.src === track(1).url)
    expect(second).toBeTruthy()
    expect(second).not.toBe(first)
    expect(second.paused).toBe(true)
    at(193) // 7 s left: the change is set for 6 s before the end
    await vi.advanceTimersByTimeAsync(1100)
    expect(title()).toBe('Song 1')
    expect(second.paused).toBe(false)
    // Both are heard while one fades into the other...
    expect(playing()).toHaveLength(2)
    // ...and then the first one stops.
    await vi.advanceTimersByTimeAsync(6100)
    expect(playing()).toEqual([second])
    expect(first.src).toBe('')
  })

  it('does not move on twice when the faded song reaches its end', async () => {
    P.setCrossfade(4)
    await startQueue()
    const first = at(185)
    at(195)
    await vi.advanceTimersByTimeAsync(1100)
    expect(title()).toBe('Song 1')
    first.paused = true
    first.emit('ended') // the old deck's own end: not news any more
    expect(title()).toBe('Song 1')
  })

  it('a song picked by hand stops the last one quickly, without a long fade', async () => {
    P.setCrossfade(8)
    await startQueue()
    const first = at(30)
    P.next()
    await vi.advanceTimersByTimeAsync(10)
    expect(title()).toBe('Song 1')
    await vi.advanceTimersByTimeAsync(300)
    expect(first.src).toBe('')
    expect(playing()).toHaveLength(1)
  })

  it('pausing in the middle of a crossfade silences both', async () => {
    P.setCrossfade(6)
    await startQueue()
    at(185)
    at(193)
    await vi.advanceTimersByTimeAsync(1100)
    expect(playing()).toHaveLength(2)
    P.pause()
    expect(playing()).toHaveLength(0)
  })

  it('a short track is not faded over half its length', async () => {
    P.setCrossfade(12)
    P.setPlaylist([{ ...track(0), duration: 20 }, track(1)], { startIndex: 0 })
    await vi.advanceTimersByTimeAsync(5)
    at(10)
    await vi.advanceTimersByTimeAsync(5000)
    expect(title()).toBe('Song 0')
  })

  it('repeat one, the end of the queue and "stop after this song" are left alone', async () => {
    P.setCrossfade(6)
    P.setRepeat('one')
    await startQueue(2)
    at(185)
    at(194)
    await vi.advanceTimersByTimeAsync(3000)
    expect(title()).toBe('Song 0')
    P.setRepeat('off')
    P.setSleepAfterTrack()
    at(194.5)
    await vi.advanceTimersByTimeAsync(3000)
    expect(title()).toBe('Song 0')
  })
})

describe('gapless', () => {
  it('starts the next song a breath before this one ends, already loaded', async () => {
    P.setCrossfade(0)
    P.setGapless(true)
    await startQueue()
    at(190)
    const next = FakeAudio.all.find((a) => a.src === track(1).url)
    expect(next && next.paused).toBe(true)
    at(199.5)
    await vi.advanceTimersByTimeAsync(400)
    expect(title()).toBe('Song 1')
    expect(next.paused).toBe(false)
    // The song was already loaded: it was not pointed at it again.
    expect(next.src).toBe(track(1).url)
  })

  it('off means the old way: the next song starts when this one ends', async () => {
    P.setCrossfade(0)
    P.setGapless(false)
    await startQueue()
    const first = at(199.9)
    await vi.advanceTimersByTimeAsync(400)
    expect(title()).toBe('Song 0')
    first.paused = true
    first.emit('ended')
    await vi.advanceTimersByTimeAsync(10)
    expect(title()).toBe('Song 1')
  })
})
