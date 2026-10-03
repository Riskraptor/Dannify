import { describe, expect, it, beforeEach, vi } from 'vitest'

// These tests drive the real player model (src/model/player.js) with the
// browser pieces it touches replaced by small fakes: an <audio> element that
// records what it was told, a window that collects listeners, and in-memory
// storage. Every test gets a fresh copy of the module, so queue and shuffle
// state never leak from one test into the next.

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
globalThis.window = {
  addEventListener: (type, fn) => (winListeners[type] ||= []).push(fn),
  removeEventListener: () => {},
  location: { href: 'http://localhost/' },
}

// A seeded Math.random, so a shuffle is the same on every run.
function seeded(seed) {
  let s = seed >>> 0
  return () => {
    s = (s + 0x6d2b79f5) >>> 0
    let t = s
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const vid = (i) => `vid${String(i).padStart(8, '0')}` // 11 chars, like a YouTube id
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
const flush = () => new Promise((r) => setTimeout(r, 0))

let P
let audio
const titleAt = (i) => P.playlist.value[i] && P.playlist.value[i].title
const currentTitle = () => P.currentTrack.value && P.currentTrack.value.title

// A fresh copy of the player module, with Math.random seeded so that two
// copies given the same steps deal the same shuffle. That is how a test can
// know the order a queue edit must leave alone: play it out on a copy that
// was not edited.
async function freshPlayer() {
  Math.random.mockImplementation(seeded(12345))
  store.clear()
  vi.resetModules()
  const mod = await import('/src/model/player.js')
  return mod.usePlayer()
}

beforeEach(async () => {
  vi.restoreAllMocks()
  vi.spyOn(Math, 'random')
  for (const k of Object.keys(winListeners)) delete winListeners[k]
  api.getLyrics = vi.fn(() => Promise.resolve({ data: {} }))
  api.getLyricVersions = vi.fn(() => Promise.resolve({ data: { versions: [] } }))
  api.getStreamInfo = vi.fn(() => Promise.resolve({ data: {} }))
  api.getRadio = vi.fn(() => Promise.resolve({ data: { songs: [] } }))
  api.saveLyricsOffset = vi.fn(() => Promise.resolve())
  api.download = vi.fn(() => Promise.resolve())
  P = await freshPlayer()
})

function start(n, { shuffle = false, repeat = 'off', at = 0 } = {}) {
  P.setRepeat(repeat)
  P.setShuffle(shuffle)
  P.setPlaylist(tracks(n), { startIndex: at })
  audio = FakeAudio.last
}

// Press Next *n* times and say what played.
function playThrough(n) {
  const out = []
  for (let k = 0; k < n; k++) {
    P.next()
    out.push(currentTitle())
  }
  return out
}

describe('shuffle respects repeat (item 2)', () => {
  it('with repeat off the shuffled queue ends after every track has played once', () => {
    start(6, { shuffle: true, at: 2 })
    const played = [currentTitle()]
    for (let k = 0; k < 5; k++) {
      P.next()
      played.push(currentTitle())
    }
    expect([...played].sort()).toEqual(tracks(6).map((t) => t.title).sort())
    const last = currentTitle()
    const calls = audio.playCalls
    P.next()
    expect(currentTitle()).toBe(last)
    expect(audio.playCalls).toBe(calls)
  })

  it('autoplay radio starts at the end of a shuffled queue, as it does in order', async () => {
    start(4, { shuffle: true, at: 0 })
    for (let k = 0; k < 3; k++) P.next()
    const lastId = P.currentTrack.value.video_id
    api.getRadio = vi.fn(() =>
      Promise.resolve({ data: { songs: [{ song_id: vid(90), name: 'Radio 90', artists: ['R'] }] } })
    )
    P.next()
    expect(api.getRadio).toHaveBeenCalledWith(lastId)
    await flush()
    expect(currentTitle()).toBe('Radio 90')
  })

  it('Previous on the first shuffled track with repeat off does not wrap to the end', () => {
    start(5, { shuffle: true, at: 1 })
    P.prev()
    expect(currentTitle()).toBe('Song 1')
  })

  it('with repeat all the shuffled queue still goes around', () => {
    start(4, { shuffle: true, repeat: 'all', at: 0 })
    const first = currentTitle()
    for (let k = 0; k < 4; k++) P.next()
    expect(currentTitle()).toBe(first)
  })
})

describe('Up next and Clear follow the play order (item 3)', () => {
  it('Up next lists exactly what next() goes on to play under shuffle', () => {
    start(8, { shuffle: true, at: 3 })
    P.next()
    P.next()
    const shown = P.upcoming.value.map(titleAt)
    expect(shown).toHaveLength(5)
    expect(playThrough(shown.length)).toEqual(shown)
  })

  it('Up next follows queue edits under shuffle', () => {
    start(6, { shuffle: true, at: 1 })
    const before = P.upcoming.value.map(titleAt)
    P.enqueue([track(80)], { next: true })
    P.enqueue([track(81)])
    P.removeFromQueue(P.upcoming.value[3])
    const shown = P.upcoming.value.map(titleAt)
    expect(shown).toEqual(['Song 80', ...before.filter((_, i) => i !== 2), 'Song 81'])
    expect(playThrough(shown.length)).toEqual(shown)
  })

  it('Up next is the rest of the list when shuffle is off', () => {
    start(5, { at: 1 })
    expect(P.upcoming.value.map(titleAt)).toEqual(['Song 2', 'Song 3', 'Song 4'])
  })

  it('clearUpcoming under shuffle removes what would play next and keeps what played', () => {
    start(8, { shuffle: true, at: 5 })
    const played = [currentTitle()]
    P.next()
    played.push(currentTitle())
    P.next()
    played.push(currentTitle())
    const now = currentTitle()
    P.clearUpcoming()
    expect(currentTitle()).toBe(now)
    expect(P.playlist.value.map((t) => t.title).sort()).toEqual([...played].sort())
    const calls = audio.playCalls
    P.next()
    expect(currentTitle()).toBe(now)
    expect(audio.playCalls).toBe(calls)
  })
})

describe('dragging a song in Up next (4.3)', () => {
  it('moves it in the list when shuffle is off, and that is the order played', () => {
    start(6, { at: 1 })
    // Up next: 2 3 4 5. Song 2 dragged to the end, then Song 5 to the top.
    P.moveUpcoming(0, 3)
    expect(P.upcoming.value.map(titleAt)).toEqual(['Song 3', 'Song 4', 'Song 5', 'Song 2'])
    P.moveUpcoming(2, 0)
    const shown = P.upcoming.value.map(titleAt)
    expect(shown).toEqual(['Song 5', 'Song 3', 'Song 4', 'Song 2'])
    expect(currentTitle()).toBe('Song 1')
    expect(playThrough(shown.length)).toEqual(shown)
  })

  it('moves it in the play order under shuffle, leaving the list alone', () => {
    start(7, { shuffle: true, at: 2 })
    const listed = P.playlist.value.map((t) => t.title)
    const before = P.upcoming.value.map(titleAt)
    P.moveUpcoming(0, before.length - 1)
    const shown = P.upcoming.value.map(titleAt)
    expect(shown).toEqual([...before.slice(1), before[0]])
    expect(P.playlist.value.map((t) => t.title)).toEqual(listed)
    expect(playThrough(shown.length)).toEqual(shown)
  })

  it('ignores a drop where it started, or out of range', () => {
    start(4, { at: 0 })
    const before = P.upcoming.value.map(titleAt)
    P.moveUpcoming(1, 1)
    P.moveUpcoming(0, 9)
    P.moveUpcoming(-1, 0)
    expect(P.upcoming.value.map(titleAt)).toEqual(before)
  })
})

describe('queue edits keep the shuffle order (item 4)', () => {
  it('"Play next" under shuffle is actually next', () => {
    start(8, { shuffle: true, at: 0 })
    P.next()
    P.enqueue([track(50)], { next: true })
    P.next()
    expect(currentTitle()).toBe('Song 50')
  })

  it('"Add to queue" goes after the rest of the shuffled order, which stays as it was', async () => {
    const setup = () => {
      start(6, { shuffle: true, at: 4 })
      P.next()
    }
    setup()
    const before = playThrough(4)
    P = await freshPlayer()
    setup()
    const played = [titleAt(4), currentTitle()]
    P.enqueue([track(60)])
    const rest = playThrough(5)
    expect(rest).toEqual([...before, 'Song 60'])
    // Nothing that already played comes round again, and then it ends.
    for (const title of played) expect(rest).not.toContain(title)
    const calls = audio.playCalls
    P.next()
    expect(currentTitle()).toBe('Song 60')
    expect(audio.playCalls).toBe(calls)
  })

  it('removing a track still to come takes it out of the order and changes nothing else', async () => {
    const setup = () => {
      start(7, { shuffle: true, at: 2 })
      P.next()
    }
    setup()
    const before = playThrough(5)
    P = await freshPlayer()
    setup()
    P.removeFromQueue(P.playlist.value.findIndex((t) => t.title === before[1]))
    expect(playThrough(4)).toEqual(before.filter((_, i) => i !== 1))
  })

  it('Previous goes back to what actually played, after queue edits', () => {
    start(8, { shuffle: true, at: 6 })
    const a = currentTitle()
    P.next()
    const b = currentTitle()
    P.next()
    const c = currentTitle()
    P.enqueue([track(70)])
    P.enqueue([track(71)], { next: true })
    P.removeFromQueue(
      P.playlist.value.findIndex((t) => ![a, b, c, 'Song 70', 'Song 71'].includes(t.title))
    )
    P.moveInQueue(0, 5)
    expect(currentTitle()).toBe(c)
    P.prev()
    expect(currentTitle()).toBe(b)
    P.prev()
    expect(currentTitle()).toBe(a)
  })
})

describe('removing the playing track (item 5)', () => {
  it('keeps a paused player paused: the next track is loaded, not started', () => {
    start(4, { at: 1 })
    P.pause()
    expect(P.isPlaying.value).toBe(false)
    const calls = audio.playCalls
    P.removeFromQueue(1)
    expect(currentTitle()).toBe('Song 2')
    expect(audio.src).toBe(track(2).url)
    expect(audio.playCalls).toBe(calls)
    expect(P.isPlaying.value).toBe(false)
  })

  it('keeps a playing player playing, on the next track', async () => {
    start(4, { at: 1 })
    await flush()
    const calls = audio.playCalls
    P.removeFromQueue(1)
    await flush() // the next song's level is looked up before it starts
    expect(currentTitle()).toBe('Song 2')
    expect(audio.playCalls).toBe(calls + 1)
    expect(P.isPlaying.value).toBe(true)
  })

  it('does not go back to the track before and start it when the last one is removed', () => {
    start(3, { at: 2 })
    const calls = audio.playCalls
    P.removeFromQueue(2)
    expect(P.currentTrack.value).toBe(null)
    expect(audio.playCalls).toBe(calls)
    expect(P.isPlaying.value).toBe(false)
    expect(P.playlist.value.map((t) => t.title)).toEqual(['Song 0', 'Song 1'])
  })

  it('under shuffle the next track in the shuffled order takes over', async () => {
    start(6, { shuffle: true, at: 0 })
    const [expected] = playThrough(1)
    P = await freshPlayer()
    start(6, { shuffle: true, at: 0 })
    P.removeFromQueue(P.currentIndex.value)
    expect(currentTitle()).toBe(expected)
  })
})

describe('seeking before the length is known (item 6)', () => {
  it('moves the playhead instead of going back to the start', () => {
    P.setPlaylist([{ ...track(1), duration: 0 }], { startIndex: 0 })
    audio = FakeAudio.last
    expect(P.duration.value).toBe(0)
    P.seek(42)
    expect(audio.currentTime).toBe(42)
    expect(P.currentTime.value).toBe(42)
  })

  it('still clamps to a known length', () => {
    start(1)
    P.seek(500)
    expect(audio.currentTime).toBe(200)
    P.seek(-5)
    expect(audio.currentTime).toBe(0)
  })
})

describe('the global Space shortcut (item 7)', () => {
  const keydown = () => winListeners.keydown[winListeners.keydown.length - 1]
  const el = (tagName, role = null) => ({
    tagName,
    isContentEditable: false,
    getAttribute: (name) => (name === 'role' ? role : null),
  })
  const press = (target) => {
    const e = {
      code: 'Space',
      key: ' ',
      target,
      defaultPrevented: false,
      metaKey: false,
      ctrlKey: false,
      altKey: false,
      shiftKey: false,
      preventDefault: vi.fn(),
    }
    keydown()(e)
    return e
  }

  it('leaves Space to a focused button, link, checkbox or slider', async () => {
    start(2)
    await flush()
    for (const target of [
      el('BUTTON'),
      el('A'),
      el('SUMMARY'),
      el('DIV', 'button'),
      el('DIV', 'checkbox'),
      el('DIV', 'slider'),
      el('SPAN', 'switch'),
    ]) {
      const e = press(target)
      expect(e.preventDefault).not.toHaveBeenCalled()
      expect(P.isPlaying.value).toBe(true)
    }
  })

  it('still toggles playback when nothing in particular has focus', async () => {
    start(2)
    await flush()
    const e = press(el('BODY'))
    expect(e.preventDefault).toHaveBeenCalled()
    expect(P.isPlaying.value).toBe(false)
  })
})

describe('switching lyric versions (item 8)', () => {
  it('drops a version list that arrives after the track changed', async () => {
    api.getLyrics = vi.fn((params) =>
      Promise.resolve({
        data: { synced: [{ time: 0, text: `lyrics of ${params.title}` }], version_count: 2 },
      })
    )
    start(2)
    await flush()
    let deliver
    api.getLyricVersions = vi.fn(() => new Promise((r) => (deliver = r)))
    const switching = P.switchLyricVersion(1)
    P.next()
    await flush()
    expect(P.lyricsLines.value.map((l) => l.text)).toEqual(['lyrics of Song 1'])
    deliver({
      data: {
        versions: [
          { synced: [{ time: 0, text: 'old song, version 1' }] },
          { synced: [{ time: 0, text: 'old song, version 2' }] },
        ],
      },
    })
    await switching
    expect(P.lyricsLines.value.map((l) => l.text)).toEqual(['lyrics of Song 1'])
    // And the new song fetches its own versions next time, not the old list.
    api.getLyricVersions = vi.fn(() => Promise.resolve({ data: { versions: [] } }))
    await P.switchLyricVersion(1)
    expect(api.getLyricVersions).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Song 1' })
    )
  })
})


describe('each song starts at its own level (4.3)', () => {
  it('waits for the song measurement before the first note, briefly', async () => {
    let answer
    api.getStreamInfo = vi.fn(() => new Promise((r) => (answer = r)))
    P.setPlaylist(tracks(2), { startIndex: 0 })
    audio = FakeAudio.last
    expect(audio.playCalls).toBe(0) // not at full level first
    answer({ data: { loudness_db: 20 } }) // 6 dB over: turned down
    await flush()
    expect(audio.playCalls).toBe(1)
    expect(audio.volume).toBeLessThan(P.volume.value)
  })

  it('does not hold a song back for long when the network is slow', async () => {
    vi.useFakeTimers()
    try {
      api.getStreamInfo = vi.fn(() => new Promise(() => {}))
      P.setPlaylist(tracks(1), { startIndex: 0 })
      audio = FakeAudio.last
      expect(audio.playCalls).toBe(0)
      await vi.advanceTimersByTimeAsync(750)
      expect(audio.playCalls).toBe(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('starts at once when the level is already known', async () => {
    api.getStreamInfo = vi.fn(() => Promise.resolve({ data: { loudness_db: 20 } }))
    P.setPlaylist(tracks(2), { startIndex: 0 })
    await flush()
    P.next()
    P.prev()
    // Song 0 was measured when it first played: known now, no wait.
    expect(FakeAudio.last.playCalls).toBeGreaterThan(0)
    expect(currentTitle()).toBe('Song 0')
  })

  it('only turns songs down without the sound engine (no limiter to catch a boost)', async () => {
    api.getStreamInfo = vi.fn(() => Promise.resolve({ data: { loudness_db: 2 } })) // quiet
    P.setPlaylist(tracks(1), { startIndex: 0 })
    audio = FakeAudio.last
    await flush()
    expect(audio.volume).toBeCloseTo(P.volume.value, 5)
  })
})

describe('the sleep timer (4.3)', () => {
  it('stops after this song instead of going on to the next', async () => {
    start(3)
    await flush()
    P.setSleepAfterTrack()
    expect(P.sleepMode.value).toBe('track')
    audio.paused = true
    audio.emit('ended')
    expect(currentTitle()).toBe('Song 0')
    expect(P.isPlaying.value).toBe(false)
    expect(P.sleepMode.value).toBe('off')
  })

  it('fades out and pauses when the time is up', async () => {
    vi.useFakeTimers()
    try {
      api.getStreamInfo = vi.fn(() => Promise.resolve({ data: {} }))
      start(2)
      await vi.advanceTimersByTimeAsync(10)
      expect(P.isPlaying.value).toBe(true)
      P.setSleepTimer(1)
      await vi.advanceTimersByTimeAsync(55000)
      expect(P.isPlaying.value).toBe(true) // still going, fading from 50 s
      await vi.advanceTimersByTimeAsync(6000)
      expect(P.isPlaying.value).toBe(false)
      expect(P.sleepMode.value).toBe('off')
      // The level comes back for the next time someone presses play.
      expect(audio.volume).toBeGreaterThan(0)
    } finally {
      vi.useRealTimers()
    }
  })

  it('pressing play while it fades out cancels it', async () => {
    vi.useFakeTimers()
    try {
      api.getStreamInfo = vi.fn(() => Promise.resolve({ data: {} }))
      start(2)
      await vi.advanceTimersByTimeAsync(10)
      P.setSleepTimer(1)
      await vi.advanceTimersByTimeAsync(52000)
      P.pause()
      P.play()
      expect(P.sleepMode.value).toBe('off')
      await vi.advanceTimersByTimeAsync(20000)
      expect(P.isPlaying.value).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })
})
