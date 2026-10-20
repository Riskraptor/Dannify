import { computed, ref, shallowRef } from 'vue'

// Special days, all year round and wherever someone is: the New Year and
// Christmas, Lunar New Year, Ramadan and the two Eids, Diwali, Holi, Easter,
// Hanukkah, Mother's Day, World Music Day, and each country's own days
// (Kenya's Madaraka, Mashujaa and Jamhuri Days, ...), from one calendar made
// by packaging/make_occasions.py. The splash (Backend/dannify/occasions.py)
// and the installer (installer/UI/Season.cs) read the same one.
//
// Always on: a greeting the first time Dannify opens on the day, and the
// day's weather at the top of Home. Someone whose system asks for less motion
// still gets them, drawn still.

const REGION_KEY = 'dn.region'
const GREETED_KEY = 'dn.greeted'

function read(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function write(key, value) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    // remembered for this run only
  }
}

// --- The calendar ----------------------------------------------------------------
/** The calendar, once read (src/model/occasions.json, a file of its own). */
export const calendar = shallowRef(null)
let loading = null
export function loadCalendar() {
  if (!loading) {
    loading = import('/src/model/occasions.json')
      .then((mod) => {
        calendar.value = mod.default || mod
        return calendar.value
      })
      .catch(() => {
        loading = null
        return null
      })
  }
  return loading
}

// --- Where someone is ------------------------------------------------------------
const CODE = /^[A-Z]{2}$/

/**
 * The country someone is in, from what the computer says. The time zone is
 * where they are; the region set in the system, or the one in their language
 * ("sw-TZ"), says which of the countries sharing that zone. A region left at
 * its default ("US" on a computer in Nairobi) is not believed over the zone.
 */
export function detectRegion({ timeZone = '', system = '', languages = [], zones = {} } = {}) {
  const sys = CODE.test(String(system || '').toUpperCase()) ? String(system).toUpperCase() : ''
  const fromLanguages = (languages || [])
    .map((l) => String(l || '').split(/[-_]/)[1] || '')
    .map((r) => r.toUpperCase())
    .filter((r) => CODE.test(r))
  const sharing = (zones && timeZone && zones[timeZone]) || []
  if (sharing.length) {
    if (sys && sharing.includes(sys)) return sys
    return fromLanguages.find((r) => sharing.includes(r)) || sharing[0]
  }
  return sys || fromLanguages[0] || ''
}

/** 'auto', or the country picked in Settings. */
export const regionChoice = ref(CODE.test(read(REGION_KEY) || '') ? read(REGION_KEY) : 'auto')
/** What the computer says, filled in by watchRegion. */
export const systemRegion = ref('')
const detected = computed(() => {
  if (!calendar.value) return ''
  let timeZone = ''
  try {
    timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || ''
  } catch {
    // no time zone known
  }
  const languages = typeof navigator !== 'undefined' ? navigator.languages || [navigator.language] : []
  return detectRegion({ timeZone, system: systemRegion.value, languages, zones: calendar.value.zones })
})
/** The country whose days are kept: the one picked, or the one detected. */
export const region = computed(() => (regionChoice.value !== 'auto' ? regionChoice.value : detected.value))
export const detectedRegion = detected

export function setRegion(code) {
  const value = CODE.test(String(code || '')) ? String(code) : 'auto'
  regionChoice.value = value
  write(REGION_KEY, value === 'auto' ? null : value)
}

// --- Which days ------------------------------------------------------------------
const ICONS = {
  newyear: 'ph:champagne',
  christmas: 'ph:tree-evergreen',
  orthodox_christmas: 'ph:tree-evergreen',
  lunar_new_year: 'ph:sparkle-fill',
  valentines: 'ph:heart-fill',
  womens_day: 'ph:flower-tulip',
  holi: 'ph:palette',
  nowruz: 'ph:flower',
  ramadan: 'ph:moon-stars-fill',
  eid_fitr: 'ph:moon-stars-fill',
  eid_adha: 'ph:moon-stars-fill',
  easter: 'ph:egg',
  orthodox_easter: 'ph:egg',
  vesak: 'ph:flower-lotus',
  world_music_day: 'ph:music-notes-fill',
  mid_autumn: 'ph:moon-stars',
  rosh_hashanah: 'ph:star-four-fill',
  diwali: 'ph:fire',
  halloween: 'ph:ghost',
  day_of_dead: 'ph:flower',
  thanksgiving: 'ph:leaf-fill',
  thanksgiving_ca: 'ph:leaf-fill',
  hanukkah: 'ph:star-four-fill',
  mothers_day: 'ph:heart-straight-fill',
  fathers_day: 'ph:heart-straight-fill',
  national: 'ph:flag-banner-fill',
}
// A few countries' days have a look of their own.
const NATIONAL_ICONS = { IE: 'ph:clover', NL: 'ph:crown' }
const NATIONAL_LOOKS = { IE: 'shamrock' }

const DAY = 86400000
function dayOf(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}
function startIn(row, year) {
  if (row.md) {
    const [m, d] = row.md.split('-').map(Number)
    return new Date(year, m - 1, d)
  }
  const iso = row.on && row.on[String(year)]
  if (!iso) return null
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}
function keptIn(row, code) {
  if (row.where === '*') return !(row.unless || []).includes(code)
  return !!code && Array.isArray(row.where) && row.where.includes(code)
}

/** Every row of the calendar that applies to a country, national days too. */
function rowsFor(data, code) {
  const rows = (data.occasions || []).filter((r) => keptIn(r, code))
  for (const n of (code && data.national && data.national[code]) || []) {
    rows.push({ ...n, kind: 'national', country: code, look: NATIONAL_LOOKS[code] || 'flag', priority: 40, days: 1, day: 0 })
  }
  return rows
}

function resolve(row, start, data) {
  const first = new Date(start)
  const day = new Date(first.getTime() + (row.day || 0) * DAY)
  const end = new Date(first.getTime() + (row.days || 1) * DAY)
  const look = lookOf(row, data)
  return {
    id: row.kind === 'national' ? 'national' : row.id,
    rowId: row.id,
    kind: row.kind,
    country: row.country || '',
    names: row.names || null,
    priority: row.priority || 0,
    start: first,
    day,
    end,
    look,
    icon: (row.kind === 'national' && NATIONAL_ICONS[row.country]) || ICONS[row.kind === 'national' ? 'national' : row.id] || 'ph:sparkle-fill',
    // Greeted once for this one, this year.
    tag: `${row.id}-${day.getFullYear()}-${day.getMonth() + 1}`,
  }
}

/** How a day looks: what falls, how it moves, in which colours. */
export function lookOf(row, data = calendar.value) {
  if (row.look === 'flag') {
    const flag = (data && data.flags && data.flags[row.country]) || ['#1ed760', '#ffd166', '#ffffff']
    return { name: 'flag', shape: 'ribbon', motion: 'fall', palette: flag }
  }
  const look = (data && data.looks && data.looks[row.look]) || { shape: 'ribbon', motion: 'fall', palette: ['#1ed760', '#ffd166'] }
  return { name: row.look, ...look }
}

/** The days kept on *date* in *code*, the most particular first. */
export function occasionsOn(date = new Date(), code = region.value, data = calendar.value) {
  if (!data) return []
  const today = dayOf(date).getTime()
  const out = []
  for (const row of rowsFor(data, code)) {
    // Last year's start as well: the New Year begins on 31 December.
    for (const year of [date.getFullYear() - 1, date.getFullYear()]) {
      const start = startIn(row, year)
      if (!start) continue
      const from = start.getTime()
      if (today >= from && today < from + (row.days || 1) * DAY) out.push(resolve(row, start, data))
    }
  }
  // The day itself above the days around it, then the more particular.
  out.sort((a, b) => {
    const onA = dayOf(a.day).getTime() === today ? 1 : 0
    const onB = dayOf(b.day).getTime() === today ? 1 : 0
    return onB - onA || b.priority - a.priority
  })
  return out
}

/** The day to dress for on *date*, or null. */
export function occasionOn(date = new Date(), code = region.value, data = calendar.value) {
  return occasionsOn(date, code, data)[0] || null
}

/** The days to come in the next year, in order. */
export function upcoming(from = new Date(), code = region.value, data = calendar.value, count = 12) {
  if (!data) return []
  const today = dayOf(from).getTime()
  const out = []
  const seen = new Set()
  for (const row of rowsFor(data, code)) {
    for (const year of [from.getFullYear() - 1, from.getFullYear(), from.getFullYear() + 1]) {
      const start = startIn(row, year)
      if (!start) continue
      const found = resolve(row, start, data)
      if (found.end.getTime() <= today || found.day.getTime() - today > 366 * DAY) continue
      const key = `${found.rowId}-${found.day.toDateString()}`
      if (seen.has(key)) continue
      seen.add(key)
      out.push(found)
    }
  }
  out.sort((a, b) => a.day - b.day || b.priority - a.priority)
  return out.slice(0, count)
}

// The clock moves on: a page left open overnight finds the new day.
const clock = ref(Date.now())
if (typeof window !== 'undefined') {
  setInterval(() => {
    if (new Date(clock.value).getDate() !== new Date().getDate()) clock.value = Date.now()
  }, 60_000)
}
/** Today's day to dress for, or null; follows the clock and the region. */
export const today = computed(() => (calendar.value ? occasionOn(new Date(clock.value), region.value) : null))

/** The year an occasion belongs to: the New Year's is the one it opens. */
export function occasionYear(occasion, date = new Date()) {
  if (occasion && occasion.id === 'newyear') {
    const at = occasion.day || date
    return at.getMonth() === 11 ? at.getFullYear() + 1 : at.getFullYear()
  }
  return (occasion && occasion.day ? occasion.day : date).getFullYear()
}

// The animals of the Chinese zodiac, the Rat's year being 2020.
const ZODIAC = ['rat', 'ox', 'tiger', 'rabbit', 'dragon', 'snake', 'horse', 'goat', 'monkey', 'rooster', 'dog', 'pig']
export function zodiac(year) {
  return ZODIAC[(((year - 2020) % 12) + 12) % 12]
}

/** The country's own name for its day, in the language Dannify speaks. */
export function nationalName(occasion, locale = 'en') {
  const names = (occasion && occasion.names) || {}
  return names[locale] || names.en || ''
}

/**
 * What to say on a day: its title ("Happy Jamhuri Day!"), a line under it,
 * and what to look for on YouTube Music to play for it.
 */
export function wordsFor(occasion, t, locale = 'en') {
  if (!occasion) return { name: '', title: '', text: '', music: '' }
  if (occasion.id === 'national') {
    const name = nationalName(occasion, locale)
    const country = countryName(occasion.country, locale)
    return {
      name,
      title: t('occasion.national.title', { name }),
      text: t('occasion.national.text', { country }),
      music: t('occasion.national.music', { country: countryName(occasion.country, 'en'), name: nationalName(occasion, 'en') }),
    }
  }
  const year = occasionYear(occasion)
  const params = { year, animal: t(`occasion.zodiac.${zodiac(year)}`) }
  return {
    name: t(`occasion.${occasion.id}.name`, params),
    title: t(`occasion.${occasion.id}.title`, params),
    text: t(`occasion.${occasion.id}.text`, params),
    music: t(`occasion.${occasion.id}.music`, params),
  }
}

/**
 * The day's own colour, for a card, a chip or a mark: the first of its
 * colours that is neither near black nor near white (Kenya's flag starts
 * with black, which would make its day look like any other).
 */
export function toneOf(occasion, fallback = 'rgb(var(--c-accent))') {
  const palette = (occasion && occasion.look && occasion.look.palette) || []
  return toneList(palette)[0] || fallback
}
/** All of a palette's colours that are neither near black nor near white. */
export function toneList(palette) {
  return (palette || []).filter((hex) => {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || ''))
    if (!m) return false
    const n = parseInt(m[1], 16)
    const lum = (0.2126 * (n >> 16) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255
    return lum > 0.08 && lum < 0.86
  })
}

/** A country's name, in a language, from the system's own list. */
export function countryName(code, locale = 'en') {
  if (!code) return ''
  try {
    return new Intl.DisplayNames([locale], { type: 'region' }).of(code) || code
  } catch {
    return code
  }
}

/**
 * A release with something new in it (4.12.0) gets a welcome of its own when
 * Dannify arrives on it; a fix (4.12.1) is told in a line.
 */
export function isBigRelease(version) {
  const found = /^(\d+)\.(\d+)\.(\d+)/.exec(String(version || ''))
  return !!found && found[3] === '0'
}

/** Whether this day's greeting is still to be given (once per day kept). */
export function shouldGreet(occasion) {
  return !!occasion && read(GREETED_KEY) !== occasion.tag
}
export function markGreeted(occasion) {
  if (occasion) write(GREETED_KEY, occasion.tag)
}

/** Whether the system asked for less motion: the day is drawn still. */
export function prefersStill() {
  try {
    return !!window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}
