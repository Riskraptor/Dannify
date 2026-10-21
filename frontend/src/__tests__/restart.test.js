import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Restarting into an update: the note left for the app that comes back, and
// what that app does with it.
const player = {
  isPlaying: { value: true },
  currentTrack: { value: { title: 'Melanin' } },
  play: vi.fn(),
}
const toasts = []
const ramps = []
vi.mock('/src/model/player', () => ({ usePlayer: () => player }))
vi.mock('/src/model/player/decks', () => ({ engine: { rampVolume: (v, s) => ramps.push([v, s]) }, audio: null }))
vi.mock('/src/model/player/sound', () => ({ applyVolume: vi.fn() }))
vi.mock('/src/model/player/session', () => ({ saveSession: vi.fn() }))
vi.mock('/src/model/toast', () => ({ toast: (msg, opts) => toasts.push({ msg, opts }) }))
vi.mock('/src/i18n', () => ({ t: (key, args) => (args ? `${key} ${JSON.stringify(args)}` : key) }))

function memoryStorage() {
  const items = new Map()
  return {
    getItem: (k) => (items.has(k) ? items.get(k) : null),
    setItem: (k, v) => items.set(k, String(v)),
    removeItem: (k) => items.delete(k),
  }
}

let restart
beforeEach(async () => {
  vi.useFakeTimers()
  vi.resetModules()
  vi.stubGlobal('localStorage', memoryStorage())
  toasts.length = 0
  ramps.length = 0
  player.play.mockClear()
  player.isPlaying.value = true
  restart = await import('../model/restart.js')
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('restarting into an update', () => {
  it('fades the music, says sorry, then restarts; the next start plays on', async () => {
    const run = vi.fn(() => true)
    const done = restart.restartKindly(run)
    await vi.advanceTimersByTimeAsync(100)
    expect(restart.restarting.value).toEqual({ playing: true, title: 'Melanin' })
    expect(ramps[0][0]).toBe(0)
    expect(run).not.toHaveBeenCalled() // the screen is read first
    await vi.advanceTimersByTimeAsync(2000)
    expect(await done).toBe(true)
    expect(run).toHaveBeenCalledTimes(1)

    // The app that comes back
    vi.resetModules()
    restart = await import('../model/restart.js')
    expect(await restart.welcomeBack()).toBe(true)
    expect(player.play).toHaveBeenCalledTimes(1)
    expect(toasts[0].msg).toMatch(/^brb\.welcome[ABC] .*Melanin/)
    // Once only
    expect(await restart.welcomeBack()).toBe(false)
  })

  it('a restart that did not happen leaves everything as it was', async () => {
    const done = restart.restartKindly(() => false)
    await vi.advanceTimersByTimeAsync(2000)
    expect(await done).toBe(false)
    expect(restart.restarting.value).toBe(null)
    expect(await restart.welcomeBack()).toBe(false)
  })

  it('paused before, paused after: only a hello', async () => {
    player.isPlaying.value = false
    const done = restart.restartKindly(() => true)
    await vi.advanceTimersByTimeAsync(2000)
    await done
    expect(await restart.welcomeBack()).toBe(true)
    expect(player.play).not.toHaveBeenCalled()
    expect(toasts[0].msg).toBe('brb.welcomeIdle')
  })

  it('a note from long ago starts nothing', async () => {
    localStorage.setItem('dn.afterRestart', JSON.stringify({ playing: true, when: Date.now() - 60 * 60 * 1000 }))
    expect(await restart.welcomeBack()).toBe(false)
    expect(player.play).not.toHaveBeenCalled()
  })
})
