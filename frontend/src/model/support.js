import { reactive, computed, ref } from 'vue'
import API from '/src/model/api'
import { desktop } from '/src/desktop/bridge'

// Supporting the app: Ko-fi, M-Pesa and PayPal (see Backend/dannify/
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

const config = reactive({ configured: false, link: '', message: '', mpesa: {}, paypal_link: '' })
/** PayPal's checkout is open in its window (the button says so). */
export const checkingOut = ref(false)
/** When someone last gave through the app: the page says thank you. */
export const thankedAt = ref(0)
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

// Each way out to give, and the nudge on Home rests a good while after.
export function giveByKofi() {
  if (!config.configured || !config.link) return
  desktop.openExternal(config.link)
  snooze(AFTER_GIVING_DAYS)
}
/**
 * PayPal, in a window of Dannify's own (Windows), so giving does not mean
 * leaving the app; in the browser where there is no such window. A payment
 * that went through is thanked for, there and then.
 */
export async function giveByPaypal({ inBrowser = false } = {}) {
  if (!config.paypal_link) return
  if (inBrowser || !desktop.isDesktop) {
    desktop.openExternal(config.paypal_link)
    snooze(AFTER_GIVING_DAYS)
    return
  }
  if (checkingOut.value) {
    desktop.checkout(config.paypal_link) // brings the open window forward
    return
  }
  checkingOut.value = true
  let result
  try {
    const { t } = await import('/src/i18n')
    result = await desktop.checkout(config.paypal_link, t('support.checkoutTitle'))
  } finally {
    checkingOut.value = false
  }
  if (!result || !result.opened) {
    // No window of our own here (another system, or WebView2 failed): the browser.
    desktop.openExternal(config.paypal_link)
    snooze(AFTER_GIVING_DAYS)
    return
  }
  if (result.paid) await thank()
}

/** Thank you, said where it shows: on the page, and in a note. */
export async function thank() {
  thankedAt.value = Date.now()
  snooze(AFTER_GIVING_DAYS)
  const [{ toast }, { t }] = await Promise.all([import('/src/model/toast'), import('/src/i18n')])
  toast(t('support.thanksToast'), { icon: 'ph:heart-fill', tone: 'success', timeout: 9000 })
}
export function gaveByMpesa() {
  snooze(AFTER_GIVING_DAYS)
}

export function notNow() {
  snooze(NOT_NOW_DAYS)
}

export function useSupport() {
  loadSupport()
  return { config, due, openSupport, notNow, giveByKofi, giveByPaypal, gaveByMpesa }
}
