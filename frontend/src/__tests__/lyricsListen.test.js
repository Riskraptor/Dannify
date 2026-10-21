import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { createListen, listenCommand, REPLAY, SKIP } from '../model/lyrics/listen'
import { syncCommand } from '../model/lyrics/keymap'

// Listening while typing the words, against a stand-in player whose
// playhead is moved by hand.

function fakePlayer() {
  const isPlaying = ref(false)
  const currentTime = ref(0)
  return {
    isPlaying,
    currentTime,
    play: vi.fn(() => (isPlaying.value = true)),
    pause: vi.fn(() => (isPlaying.value = false)),
  }
}

function setup({ replays = () => true } = {}) {
  const player = fakePlayer()
  const seekBy = vi.fn((d) => (player.currentTime.value = Math.max(0, player.currentTime.value + d)))
  const listen = createListen({ player, seekBy, replays })
  return { player, seekBy, listen }
}

function key(code, mods = {}) {
  return { code, preventDefault: vi.fn(), stopPropagation: vi.fn(), ...mods }
}

// Storage is an in-memory copy, fresh for every test.
beforeEach(() => {
  const storage = new Map()
  globalThis.localStorage = {
    getItem: (k) => (storage.has(k) ? storage.get(k) : null),
    setItem: (k, v) => storage.set(k, String(v)),
    removeItem: (k) => storage.delete(k),
  }
})
afterEach(() => {
  delete globalThis.localStorage
})

describe('the keys', () => {
  it('play and pause with Ctrl+Space, go back and on with Alt and the arrows', () => {
    expect(listenCommand(key('Space', { ctrlKey: true }))).toBe('toggle')
    expect(listenCommand(key('ArrowLeft', { altKey: true }))).toBe('back')
    expect(listenCommand(key('ArrowRight', { altKey: true }))).toBe('forward')
  })

  it('leave typing alone: plain keys, Ctrl+arrows (a word at a time) and Shift', () => {
    expect(listenCommand(key('Space'))).toBe(null)
    expect(listenCommand(key('ArrowLeft', { ctrlKey: true }))).toBe(null)
    expect(listenCommand(key('ArrowLeft'))).toBe(null)
    expect(listenCommand(key('Space', { ctrlKey: true, shiftKey: true }))).toBe(null)
    expect(listenCommand(key('ArrowLeft', { altKey: true, shiftKey: true }))).toBe(null)
    // AltGr is Ctrl+Alt on Windows: it types letters.
    expect(listenCommand(key('Space', { ctrlKey: true, altKey: true }))).toBe(null)
    // The system's search on a Mac.
    expect(listenCommand(key('Space', { metaKey: true }))).toBe(null)
  })

  it('are none of the timing step’s own', () => {
    for (const e of [key('Space', { ctrlKey: true }), key('ArrowLeft', { altKey: true }), key('ArrowRight', { altKey: true })]) {
      expect(syncCommand(e)).toBe(null)
    }
  })

  it('work inside the words box, and stop there', () => {
    const { player, listen } = setup()
    const e = key('Space', { ctrlKey: true, target: { tagName: 'TEXTAREA' } })
    expect(listen.handleKey(e)).toBe(true)
    expect(e.preventDefault).toHaveBeenCalled()
    expect(e.stopPropagation).toHaveBeenCalled()
    expect(player.play).toHaveBeenCalled()
  })

  it('let every other key through', () => {
    const { listen } = setup()
    const e = key('KeyA', { target: { tagName: 'TEXTAREA' } })
    expect(listen.handleKey(e)).toBe(false)
    expect(e.preventDefault).not.toHaveBeenCalled()
  })

  it('a held Ctrl+Space does not flicker the song on and off', () => {
    const { player, listen } = setup()
    listen.handleKey(key('Space', { ctrlKey: true }))
    listen.handleKey(key('Space', { ctrlKey: true, repeat: true }))
    expect(player.play).toHaveBeenCalledTimes(1)
    expect(player.pause).not.toHaveBeenCalled()
  })
})

describe('back and forward', () => {
  it(`move ${SKIP} seconds`, () => {
    const { seekBy, listen } = setup()
    listen.back()
    listen.forward()
    expect(seekBy.mock.calls).toEqual([[-SKIP], [SKIP]])
  })
})

describe('playing again after a pause', () => {
  it(`goes back ${REPLAY} seconds, so the last words are heard again`, () => {
    const { player, seekBy, listen } = setup()
    listen.toggle()
    player.currentTime.value = 30
    listen.toggle()
    expect(player.pause).toHaveBeenCalled()
    listen.toggle()
    expect(seekBy).toHaveBeenCalledWith(-REPLAY)
    expect(player.currentTime.value).toBe(30 - REPLAY)
    expect(player.isPlaying.value).toBe(true)
  })

  it('not the first time it plays', () => {
    const { seekBy, listen } = setup()
    listen.toggle()
    expect(seekBy).not.toHaveBeenCalled()
  })

  it('not when the song was put somewhere else while paused', () => {
    const { player, seekBy, listen } = setup()
    listen.toggle()
    player.currentTime.value = 30
    listen.toggle()
    player.currentTime.value = 80
    listen.toggle()
    expect(seekBy).not.toHaveBeenCalled()
  })

  it('not when paused somewhere else (the player bar, a media key)', () => {
    const { player, seekBy, listen } = setup()
    listen.toggle()
    player.currentTime.value = 30
    player.pause()
    listen.toggle()
    expect(seekBy).not.toHaveBeenCalled()
    expect(player.isPlaying.value).toBe(true)
  })

  it('not while lines are being tapped in', () => {
    const { player, seekBy, listen } = setup({ replays: () => false })
    listen.toggle()
    player.currentTime.value = 30
    listen.toggle()
    listen.toggle()
    expect(seekBy).not.toHaveBeenCalled()
  })

  it('can be turned off, and stays off', () => {
    const { player, seekBy, listen } = setup()
    listen.setReplay(false)
    listen.toggle()
    player.currentTime.value = 30
    listen.toggle()
    listen.toggle()
    expect(seekBy).not.toHaveBeenCalled()
    expect(setup().listen.replay.value).toBe(false)
    listen.setReplay(true)
    expect(setup().listen.replay.value).toBe(true)
  })
})
