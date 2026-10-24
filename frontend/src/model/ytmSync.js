import { ref, watch } from 'vue'
import API from './api'
import { keeping, listensEpoch } from './listens'
import { useAccount } from './account'

// YouTube Music's history in Dannify's (Backend/dannify/ytm_history.py): for
// anyone signed in with Google, what they played there, on their phone or on
// the web, counts in History, Your stats and Your Soundtrack. A copy
// installed today starts from all of it, and keeps up by itself: a little
// after start, every few hours, as soon as someone signs in, and whenever a
// page that shows listening is opened (Your stats, History, Your year in
// music). There is nothing to press. Nothing for anyone whose history is
// paused, or who turned this off in Settings, Accounts.

const KEY = 'dn.ytmSync'
const EVERY = 3 * 3600 * 1000
// A page opened again within this long does not ask again.
const FRESH = 2 * 60 * 1000

function read() {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

/** Whether YouTube Music's history is brought in. On unless turned off. */
export const ytmSyncOn = ref(read() !== '0')
/** { last, total }: when it was last brought in, and how many plays so far. */
export const ytmStatus = ref({ last: 0, total: 0 })
export const ytmSyncing = ref(false)

const account = useAccount()

export async function syncFromYouTube() {
  if (!ytmSyncOn.value || !keeping.value || !account.signedIn.value || ytmSyncing.value) return null
  ytmSyncing.value = true
  try {
    const res = await API.syncYouTubeHistory()
    const data = res.data || {}
    ytmStatus.value = { last: data.last || Math.round(Date.now() / 1000), total: data.total || 0 }
    if (data.brought > 0) listensEpoch.value++
    return data
  } catch {
    // Offline, or signed out meanwhile: next time.
    return null
  } finally {
    ytmSyncing.value = false
  }
}

let lastAsked = 0

/**
 * A page that shows listening was opened: bring in what YouTube Music has
 * that Dannify has not, unless that was done a moment ago. The page redraws
 * by itself when anything new arrives (listensEpoch).
 */
export function syncSoon(now = Date.now()) {
  if (now - lastAsked < FRESH) return null
  lastAsked = now
  return syncFromYouTube()
}

/** "1,234 plays from YouTube Music · up to date 5 minutes ago", or what is happening. */
export function syncLine(t, locale) {
  if (ytmSyncing.value) return t('account.syncing')
  const { last, total } = ytmStatus.value
  if (!last) return t('account.syncSoon')
  const plays = t('account.syncedPlays', { count: new Intl.NumberFormat(locale).format(total || 0) })
  return `${plays} · ${t('account.syncedAgo', { when: agoText(last, locale) })}`
}

function agoText(seconds, locale) {
  const diff = Math.max(0, Date.now() / 1000 - seconds)
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  if (diff < 60) return rtf.format(0, 'second')
  if (diff < 3600) return rtf.format(-Math.round(diff / 60), 'minute')
  if (diff < 86400) return rtf.format(-Math.round(diff / 3600), 'hour')
  return rtf.format(-Math.round(diff / 86400), 'day')
}

export async function loadYtmStatus() {
  try {
    const res = await API.youTubeHistoryStatus()
    ytmStatus.value = { last: res.data.last || 0, total: res.data.total || 0 }
  } catch {
    // shown as never
  }
}

export function setYtmSync(on) {
  ytmSyncOn.value = !!on
  try {
    localStorage.setItem(KEY, on ? '1' : '0')
  } catch {
    // for this run only
  }
  if (on) syncFromYouTube()
}

let started = false
/** Once, from App.vue. */
export function startYtmSync() {
  if (started || typeof window === 'undefined') return
  started = true
  loadYtmStatus()
  setTimeout(syncSoon, 20000)
  setInterval(syncFromYouTube, EVERY)
  watch(
    () => account.signedIn.value,
    (on, was) => {
      if (on && !was) setTimeout(syncFromYouTube, 3000)
    }
  )
}
