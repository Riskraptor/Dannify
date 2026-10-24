import { reactive, computed, ref } from 'vue'
import API from '/src/model/api'
import { desktop } from '/src/desktop/bridge'

// Supporting the app: GitHub Sponsors (see Backend/dannify/
// support.py), on a page of their own in Settings, reachable from a small
// button in the side bar at any time, and mentioned once in a while on Home,
// never as a pop-up. Only after someone has really used the app (a week, and
// a few dozen songs), and a "Not now" is honoured for two months.

const FIRST_RUN_KEY = 'dn.firstRun'
const PLAYS_KEY = 'dn.plays'
const SNOOZE_KEY = 'dn.supportSnooze'

const DAY = 24 * 3600 * 1000
const AFTER_DAYS = 7
const AFTER_PLAYS = 40
const NOT_NOW_DAYS = 60
const AFTER_GIVING_DAYS = 180

// GitHub Sponsors only: PayPal, Ko-fi (4.14.0) and M-Pesa are gone, whatever
// a copy is told about them.
const config = reactive({ configured: false, message: '', sponsors_link: '' })
let loading = null

function read(key, fallback = 0) {
  try {
    const v = Number(localStorage.getItem(key))
    return Number.isFinite(v) && v > 0 ? v : fallback
  } catch {
    return fallback
  }
}
function write(key, value) {
  try {
    localStorage.setItem(key, String(value))
  } catch {
    // Storage blocked: the nudge just comes back sooner.
  }
}

if (!read(FIRST_RUN_KEY)) write(FIRST_RUN_KEY, Date.now())
const plays = ref(read(PLAYS_KEY))
const snoozedUntil = ref(read(SNOOZE_KEY))

export function loadSupport() {
  if (!loading) {
    loading = API.getSupportConfig()
      .then((res) => Object.assign(config, res.data || {}))
      .catch(() => {
        loading = null
      })
  }
  return loading
}

/** Read again: the details can change between releases (support.py). */
export function refreshSupport() {
  loading = null
  return loadSupport()
}

/**
 * A song listened to for long enough to count: the same rule as History and
 * Stats (see listenMeter.js). Counting every song that started counted every
 * skip, and the note asking for support came round far too soon.
 */
export function notePlayed() {
  plays.value += 1
  write(PLAYS_KEY, plays.value)
}

const due = computed(
  () =>
    config.configured &&
    Date.now() - read(FIRST_RUN_KEY, Date.now()) > AFTER_DAYS * DAY &&
    plays.value >= AFTER_PLAYS &&
    Date.now() > snoozedUntil.value
)

function snooze(days) {
  snoozedUntil.value = Date.now() + days * DAY
  write(SNOOZE_KEY, snoozedUntil.value)
}

/** The ways to give, on their page in Settings. */
export async function openSupport() {
  const { default: router } = await import('/src/router')
  router.push({ name: 'Settings', query: { pane: 'support' } })
}

// Giving, and the nudge on Home rests a good while after.
/**
 * GitHub Sponsors, in the browser: sponsoring needs a GitHub sign-in, and the
 * browser is where people are already signed in.
 */
export function giveBySponsors() {
  if (!config.sponsors_link) return
  desktop.openExternal(config.sponsors_link)
  snooze(AFTER_GIVING_DAYS)
}
export function notNow() {
  snooze(NOT_NOW_DAYS)
}

export function useSupport() {
  loadSupport()
  return { config, due, openSupport, notNow }
}
