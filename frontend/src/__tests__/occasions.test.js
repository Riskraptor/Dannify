import { describe, expect, it, beforeEach, vi } from 'vitest'

// Special days (model/occasions.js): the same dates as the splash
// (Backend/dannify/occasions.py) and the installer (installer/UI/Season.cs).

const store = new Map()
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
}

let O
beforeEach(async () => {
  store.clear()
  vi.resetModules()
  O = await import('/src/model/occasions')
})

const day = (iso) => {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d, 12)
}

describe('special days', () => {
  it.each([
    ['2026-12-17', null],
    ['2026-12-18', 'christmas'],
    ['2026-12-25', 'christmas'],
    ['2026-12-26', 'christmas'],
    ['2026-12-27', null],
    ['2026-12-31', 'newyear'],
    ['2027-01-01', 'newyear'],
    ['2027-01-02', 'newyear'],
    ['2027-01-03', null],
    ['2026-07-04', null],
  ])('%s is %s', (iso, id) => {
    const found = O.occasionOn(day(iso))
    expect(found ? found.id : null).toBe(id)
  })

  it('the New Year belongs to the year it opens', () => {
    const ny = O.occasionOn(day('2026-12-31'))
    expect(O.occasionYear(ny, day('2026-12-31'))).toBe(2027)
    expect(O.occasionYear(ny, day('2027-01-01'))).toBe(2027)
    const xmas = O.occasionOn(day('2026-12-24'))
    expect(O.occasionYear(xmas, day('2026-12-24'))).toBe(2026)
  })

  it('greets once a year, and not at all when turned off', () => {
    const xmas = O.occasionOn(day('2026-12-24'))
    expect(O.shouldGreet(xmas, day('2026-12-24'))).toBe(true)
    O.markGreeted(xmas, day('2026-12-24'))
    expect(O.shouldGreet(xmas, day('2026-12-25'))).toBe(false)
    expect(O.shouldGreet(xmas, day('2027-12-24'))).toBe(true)
    O.setSeasonal(false)
    expect(O.shouldGreet(xmas, day('2027-12-24'))).toBe(false)
    expect(store.get('dn.seasonal')).toBe('0')
    expect(O.shouldGreet(null)).toBe(false)
  })

  it('a release with something new in it is a big one; a fix is not', () => {
    expect(O.isBigRelease('4.12.0')).toBe(true)
    expect(O.isBigRelease('5.0.0')).toBe(true)
    expect(O.isBigRelease('4.12.1')).toBe(false)
    expect(O.isBigRelease('')).toBe(false)
    expect(O.isBigRelease('garbage')).toBe(false)
  })
})
