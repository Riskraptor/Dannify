import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Small covers wait until they are near the screen (model/thumbs.js). One
// that comes in while its page is kept out of sight still waits, and is drawn
// when the page is shown again.

let observers
let T

class FakeObserver {
  constructor(callback) {
    this.callback = callback
    this.targets = new Set()
    observers.push(this)
  }
  observe(el) {
    this.targets.add(el)
  }
  unobserve(el) {
    this.targets.delete(el)
  }
  report(el, isIntersecting) {
    if (this.targets.has(el)) this.callback([{ target: el, isIntersecting }])
  }
}

function cover({ connected = true, top = 100 } = {}) {
  return {
    isConnected: connected,
    getBoundingClientRect: () => ({ top, bottom: top + 60, width: 60 }),
  }
}

beforeEach(async () => {
  vi.useFakeTimers()
  vi.resetModules()
  observers = []
  vi.stubGlobal('window', { innerHeight: 900, devicePixelRatio: 1 })
  vi.stubGlobal('document', { visibilityState: 'visible' })
  vi.stubGlobal('IntersectionObserver', FakeObserver)
  T = await import('/src/model/thumbs')
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('whenVisible()', () => {
  it('runs for a cover on screen even when the window reports nothing', () => {
    const run = vi.fn()
    T.whenVisible(cover(), run)
    vi.advanceTimersByTime(1500)
    expect(run).toHaveBeenCalledTimes(1)
  })

  it('keeps a cover waiting while its page is out of sight, and runs it when the page is back', () => {
    const el = cover({ connected: false })
    const run = vi.fn()
    T.whenVisible(el, run)
    vi.advanceTimersByTime(1500)
    expect(run).not.toHaveBeenCalled()

    // The page is shown again.
    el.isConnected = true
    T.checkSoon()
    vi.advanceTimersByTime(1500)
    expect(run).toHaveBeenCalledTimes(1)
  })

  it('also runs when the window reports it, after waiting out of sight', () => {
    const el = cover({ connected: false })
    const run = vi.fn()
    T.whenVisible(el, run)
    vi.advanceTimersByTime(1500)
    el.isConnected = true
    observers[0].report(el, true)
    expect(run).toHaveBeenCalledTimes(1)
    // Once only.
    T.checkSoon()
    vi.advanceTimersByTime(1500)
    expect(run).toHaveBeenCalledTimes(1)
  })

  it('never runs for a cover that has stopped waiting', () => {
    const el = cover({ connected: false })
    const run = vi.fn()
    const stop = T.whenVisible(el, run)
    stop()
    el.isConnected = true
    T.checkSoon()
    vi.advanceTimersByTime(1500)
    observers[0].report(el, true)
    expect(run).not.toHaveBeenCalled()
  })

  it('leaves one far down the page for later', () => {
    const el = cover({ top: 5000 })
    const run = vi.fn()
    T.whenVisible(el, run)
    vi.advanceTimersByTime(1500)
    expect(run).not.toHaveBeenCalled()
    observers[0].report(el, true)
    expect(run).toHaveBeenCalledTimes(1)
  })
})
