import { reactive, computed, ref } from 'vue'
import API from '/src/model/api'
import { desktop } from '/src/desktop/bridge'

// Supporting the app: one link (see Backend/dannify/support.py), reachable
// from a small button in the side bar at any time, and mentioned once in a
// while on Home, never as a pop-up. Only after someone has really used the
// app (a week, and a few dozen songs), and a "Not now" is honoured for two
// months. Before, it was a card at the bottom of Settings → About, which most
// people never open.

const FIRST_RUN_KEY = 'dn.firstRun'
const PLAYS_KEY = 'dn.plays'
const SNOOZE_KEY = 'dn.supportSnooze'

const DAY = 24 * 3600 * 1000
const AFTER_DAYS = 7
const AFTER_PLAYS = 40
const NOT_NOW_DAYS = 60
const AFTER_GIVING_DAYS = 180

const config = reactive({ configured: false, link: '', message: '' })
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

/** A song played to a point that counts (see player.js). */
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

export function openSupport() {
  if (!config.configured || !config.link) return
  desktop.openExternal(config.link)
  snooze(AFTER_GIVING_DAYS)
}

export function notNow() {
  snooze(NOT_NOW_DAYS)
}

export function useSupport() {
  loadSupport()
  return { config, due, openSupport, notNow }
}
