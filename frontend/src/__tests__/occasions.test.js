import { describe, expect, it, beforeEach, vi } from 'vitest'
import data from '/src/model/occasions.json'

// Special days (model/occasions.js), from the calendar packaging/
// make_occasions.py made: the splash (Backend/dannify/occasions.py) and the
// installer (installer/UI/Season.cs) read the same one and are tested on the
// same days.

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
const on = (iso, region) => {
  const found = O.occasionOn(day(iso), region, data)
  return found ? (found.id === 'national' ? `national:${found.names.en}` : found.id) : null
}

describe('where someone is', () => {
  const zones = data.zones
  it.each([
    // A region left at its default does not beat the time zone.
    [{ timeZone: 'Africa/Nairobi', system: 'US' }, 'KE'],
    // One of the countries sharing the zone, from the system or the language.
    [{ timeZone: 'Africa/Nairobi', system: 'TZ' }, 'TZ'],
    [{ timeZone: 'Africa/Nairobi', system: 'US', languages: ['sw-UG', 'en'] }, 'UG'],
    [{ timeZone: 'America/New_York', system: 'US' }, 'US'],
    [{ timeZone: 'Europe/Paris', system: 'US', languages: ['fr-FR'] }, 'FR'],
    // No zone known: whatever the computer says.
    [{ timeZone: 'Etc/UTC', system: 'de' }, 'DE'],
    [{ timeZone: '', system: '', languages: ['pt-BR'] }, 'BR'],
    [{}, ''],
  ])('%j is %s', (seen, want) => {
    expect(O.detectRegion({ ...seen, zones })).toBe(want)
  })

  it('a region picked in Settings is kept, and Automatic forgets it', () => {
    O.setRegion('GH')
    expect(O.regionChoice.value).toBe('GH')
    expect(store.get('dn.region')).toBe('GH')
    O.setRegion('auto')
    expect(O.regionChoice.value).toBe('auto')
    expect(store.has('dn.region')).toBe(false)
    O.setRegion('nonsense')
    expect(O.regionChoice.value).toBe('auto')
  })
})

describe('the days, all year, where they are kept', () => {
  it.each([
    // Kenya: its own three days, the Eids, Easter, Christmas, the New Year.
    ['2026-06-01', 'KE', 'national:Madaraka Day'],
    ['2026-10-20', 'KE', 'national:Mashujaa Day'],
    ['2026-12-12', 'KE', 'national:Jamhuri Day'],
    ['2026-10-21', 'KE', null],
    ['2026-03-20', 'KE', 'eid_fitr'],
    ['2026-05-27', 'KE', 'eid_adha'],
    ['2026-04-05', 'KE', 'easter'],
    ['2026-12-17', 'KE', null],
    ['2026-12-18', 'KE', 'christmas'],
    ['2026-12-26', 'KE', 'christmas'],
    ['2026-12-27', 'KE', null],
    ['2026-12-31', 'KE', 'newyear'],
    ['2027-01-02', 'KE', 'newyear'],
    ['2027-01-03', 'KE', null],
    ['2026-02-14', 'KE', 'valentines'],
    // Days kept in other places, on their dates there.
    ['2026-03-21', 'SG', 'eid_fitr'],
    ['2026-02-17', 'CN', 'lunar_new_year'],
    ['2026-11-08', 'IN', 'diwali'],
    ['2026-03-04', 'IN', 'holi'],
    ['2026-04-12', 'GR', 'orthodox_easter'],
    ['2026-07-04', 'US', 'national:Independence Day'],
    ['2026-11-26', 'US', 'thanksgiving'],
    ['2026-12-05', 'IL', 'hanukkah'],
    ['2026-10-31', 'US', 'halloween'],
    ['2026-03-17', 'IE', "national:Saint Patrick's Day"],
    ['2026-06-21', 'DE', 'world_music_day'],
    // A family's day is above one the whole world keeps.
    ['2026-06-21', 'KE', 'fathers_day'],
    ['2026-05-10', 'KE', 'mothers_day'],
    // Not greeted where it is not kept.
    ['2026-02-14', 'PK', null],
    ['2026-12-25', 'SA', null],
    ['2026-10-31', 'KE', null],
    // Nowhere known: only the days kept everywhere.
    ['2026-12-25', '', 'christmas'],
    ['2026-12-12', '', null],
  ])('%s in %s is %s', (iso, region, want) => {
    expect(on(iso, region)).toBe(want)
  })

  it('the New Year belongs to the year it opens; Lunar New Year has its animal', () => {
    const ny = O.occasionOn(day('2026-12-31'), 'KE', data)
    expect(O.occasionYear(ny)).toBe(2027)
    expect(O.occasionYear(O.occasionOn(day('2027-01-01'), 'KE', data))).toBe(2027)
    expect(O.occasionYear(O.occasionOn(day('2026-12-24'), 'KE', data))).toBe(2026)
    expect(O.zodiac(2026)).toBe('horse')
    expect(O.zodiac(2024)).toBe('dragon')
    expect(O.zodiac(2019)).toBe('pig')
  })

  it('each day has a look: a flag’s colours on a country’s own day', () => {
    const jamhuri = O.occasionOn(day('2026-12-12'), 'KE', data)
    expect(jamhuri.look).toMatchObject({ name: 'flag', shape: 'ribbon', motion: 'fall' })
    expect(jamhuri.look.palette).toEqual(data.flags.KE)
    expect(jamhuri.icon).toBe('ph:flag-banner-fill')
    expect(O.occasionOn(day('2026-12-25'), 'KE', data).look).toMatchObject({ shape: 'dot', motion: 'fall' })
    expect(O.occasionOn(day('2027-01-01'), 'KE', data).look.motion).toBe('burst')
    expect(O.occasionOn(day('2026-03-17'), 'IE', data).look.shape).toBe('clover')
  })

  it('the year ahead, in order, from today', () => {
    const coming = O.upcoming(day('2026-10-21'), 'KE', data, 6)
    expect(coming.map((o) => (o.id === 'national' ? o.names.en : o.id))).toEqual([
      'Jamhuri Day',
      'christmas',
      'newyear',
      'ramadan',
      'valentines',
      'womens_day',
    ])
    // A day under way counts as coming up.
    expect(O.upcoming(day('2026-12-24'), 'KE', data, 1)[0].id).toBe('christmas')
  })
})

describe('what is said', () => {
  const t = (key, params) => (params ? `${key} ${JSON.stringify(params)}` : key)

  it('a country’s day by its name in the language, its music by country', () => {
    const jamhuri = O.occasionOn(day('2026-12-12'), 'KE', data)
    expect(O.wordsFor(jamhuri, t, 'sw').title).toBe('occasion.national.title {"name":"Siku ya Jamhuri"}')
    expect(O.wordsFor(jamhuri, t, 'fr').title).toBe('occasion.national.title {"name":"Jamhuri Day"}')
    expect(O.wordsFor(jamhuri, t, 'en').music).toContain('"name":"Jamhuri Day"')
  })

  it('the animal of the year for Lunar New Year', () => {
    const lny = O.occasionOn(day('2026-02-17'), 'CN', data)
    expect(O.wordsFor(lny, t, 'en').text).toBe('occasion.lunar_new_year.text {"year":2026,"animal":"occasion.zodiac.horse"}')
  })
})

describe('greetings', () => {
  it('once for each day kept, and again the next time it comes', () => {
    const xmas = O.occasionOn(day('2026-12-24'), 'KE', data)
    expect(O.shouldGreet(xmas)).toBe(true)
    O.markGreeted(xmas)
    expect(O.shouldGreet(O.occasionOn(day('2026-12-25'), 'KE', data))).toBe(false)
    expect(O.shouldGreet(O.occasionOn(day('2027-12-24'), 'KE', data))).toBe(true)
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
