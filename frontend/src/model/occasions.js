import { ref } from 'vue'

// Special days, when Dannify dresses up a little: snow at Christmas, confetti
// for the New Year. The same days as the splash (Backend/dannify/
// occasions.py) and the installer (installer/UI/Season.cs).
//
// It stays a touch: a greeting once, the first time Dannify opens on the
// day, a little weather at the top of Home, and nothing for anyone who
// turned it off or asked their system for less motion.

export const OCCASIONS = [
  { id: 'christmas', from: [12, 18], to: [12, 26], effect: 'snow', icon: 'ph:snowflake-bold' },
  { id: 'newyear', from: [12, 31], to: [1, 2], effect: 'confetti', icon: 'ph:confetti' },
]

function compare(a, b) {
  return a[0] - b[0] || a[1] - b[1]
}

/** The occasion on *date* (today), or null. */
export function occasionOn(date = new Date()) {
  const md = [date.getMonth() + 1, date.getDate()]
  return (
    OCCASIONS.find((o) =>
      compare(o.from, o.to) <= 0
        ? compare(md, o.from) >= 0 && compare(md, o.to) <= 0
        : compare(md, o.from) >= 0 || compare(md, o.to) <= 0
    ) || null
  )
}

/** The year an occasion belongs to: the New Year's is the one it opens. */
export function occasionYear(occasion, date = new Date()) {
  const year = date.getFullYear()
  return occasion && occasion.id === 'newyear' && date.getMonth() === 11 ? year + 1 : year
}

/**
 * A release with something new in it (4.12.0) gets a welcome of its own when
 * Dannify arrives on it; a fix (4.12.1) is told in a line.
 */
export function isBigRelease(version) {
  const found = /^(\d+)\.(\d+)\.(\d+)/.exec(String(version || ''))
  return !!found && found[3] === '0'
}

function read(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function write(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // remembered for this run only
  }
}

const SEASONAL_KEY = 'dn.seasonal'
/** Whether special days and big updates are celebrated at all. */
export const seasonal = ref(read(SEASONAL_KEY) !== '0')
export function setSeasonal(on) {
  seasonal.value = !!on
  write(SEASONAL_KEY, on ? '1' : '0')
}

const GREETED_KEY = 'dn.greeted'
function greetTag(occasion, date) {
  return `${occasion.id}-${occasionYear(occasion, date)}`
}
/** Whether today's greeting is still to be given (once a year per occasion). */
export function shouldGreet(occasion, date = new Date()) {
  return !!occasion && seasonal.value && read(GREETED_KEY) !== greetTag(occasion, date)
}
export function markGreeted(occasion, date = new Date()) {
  if (occasion) write(GREETED_KEY, greetTag(occasion, date))
}

/** Whether the system asked for less motion. */
export function prefersStill() {
  try {
    return !!window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}
