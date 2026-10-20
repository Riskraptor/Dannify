import { ref, watch } from 'vue'
import API from './api'
import { keeping, listensEpoch } from './listens'
import { useAccount } from './account'
import { currentLocale } from '/src/i18n'

// YouTube Music's history in Dannify's (Backend/dannify/ytm_history.py): for
// anyone signed in with Google, what they played there, on their phone or on
// the web, counts in History, Your stats and Your year in music. A copy
// installed today starts from all of it, and keeps up: a little after start,
// every few hours, and as soon as someone signs in. Nothing for anyone whose
// history is paused, or who turned this off in Settings, Accounts.

const KEY = 'dn.ytmSync'
const EVERY = 3 * 3600 * 1000

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

/** "a few minutes ago", in the language Dannify speaks. */
export function syncedAgo(last, now = Date.now()) {
  if (!last) return ''
  const minutes = Math.round((last * 1000 - now) / 60000)
  const rtf = new Intl.RelativeTimeFormat(currentLocale.value, { numeric: 'auto' })
  // "now", not "this minute".
  if (minutes > -1) return rtf.format(0, 'second')
  if (minutes > -60) return rtf.format(minutes, 'minute')
  const hours = Math.round(minutes / 60)
  if (hours > -24) return rtf.format(hours, 'hour')
  return rtf.format(Math.round(hours / 24), 'day')
}

let started = false
/** Once, from App.vue. */
export function startYtmSync() {
  if (started || typeof window === 'undefined') return
  started = true
  loadYtmStatus()
  setTimeout(syncFromYouTube, 20000)
  setInterval(syncFromYouTube, EVERY)
  watch(
    () => account.signedIn.value,
    (on, was) => {
      if (on && !was) setTimeout(syncFromYouTube, 3000)
    }
  )
}
