import { describe, expect, it, beforeEach } from 'vitest'

const store = new Map()
globalThis.sessionStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
}
globalThis.localStorage = { getItem: () => null, setItem: () => {} }

const { pageIsStale } = await import('/src/model/staleness.js')

describe('reloading after an update', () => {
  beforeEach(() => store.clear())

  it('does not reload a page that is already the new version', () => {
    // First start after 4.0.0 -> 4.1.0: the page is 4.1.0 already.
    expect(pageIsStale('4.0.0', '4.1.0', '4.1.0')).toBe(false)
  })

  it('reloads a page older than the app, once', () => {
    expect(pageIsStale('4.0.0', '4.1.0', '4.0.0')).toBe(true)
    expect(pageIsStale('4.0.0', '4.1.0', '4.0.0')).toBe(false)
  })

  it('never reloads on a first run or without an answer', () => {
    expect(pageIsStale(null, '4.1.0', '4.1.0')).toBe(false)
    expect(pageIsStale('4.1.0', '', '4.1.0')).toBe(false)
  })

  it('built this version: the version is baked in', () => {
    // eslint-disable-next-line no-undef
    expect(__APP_VERSION__).toMatch(/^\d+\.\d+\.\d+/)
  })
})
