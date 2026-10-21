import { reactive, ref } from 'vue'
import API from '/src/model/api'
import router from '/src/router'
import { ensureFullWindow } from '/src/desktop/fullWindow'
import { t } from '/src/i18n'
import { toast } from '/src/model/toast'
import { useConnectivity, whenOnline } from '/src/model/connectivity'

// Errors nobody caught, in the page: written to the app's log, where a
// problem report picks them up. They used to go to a console nobody can open
// in the desktop app, and were gone when it closed.

// Not problems: the browser saying a layout settled late, and requests the
// app cancelled on purpose.
const NOISE = /ResizeObserver loop|AbortError|CanceledError|canceled|The play\(\) request was interrupted|NotAllowedError: play\(\)/i

const sent = new Map() // message -> when, so one error on a loop is sent once
let windowStart = 0
let sentThisMinute = 0

function describe(err) {
  if (!err) return { message: 'error', stack: '' }
  if (err instanceof Error) return { message: `${err.name}: ${err.message}`, stack: err.stack || '' }
  if (typeof err === 'object' && err.message) return { message: String(err.message), stack: String(err.stack || '') }
  return { message: String(err), stack: '' }
}

export function reportError(err, where = '') {
  const { message, stack } = describe(err)
  if (NOISE.test(message)) return
  const now = Date.now()
  const last = sent.get(message)
  if (last && now - last < 60000) return
  if (now - windowStart > 60000) {
    windowStart = now
    sentThisMinute = 0
  }
  if (sentThisMinute >= 10) return
  sentThisMinute++
  sent.set(message, now)
  if (sent.size > 100) sent.delete(sent.keys().next().value)
  let route = ''
  try {
    route = router.currentRoute.value.fullPath
  } catch {
    // before the router is up
  }
  API.reportClientError({ message, stack: String(stack).slice(0, 4000), route: where ? `${route} (${where})` : route }).catch(() => {})
}

export function installErrorReporting(app) {
  const before = app.config.errorHandler
  app.config.errorHandler = (err, instance, info) => {
    reportError(err, info)
    if (before) before(err, instance, info)
    else console.error(err)
  }
  window.addEventListener('error', (e) => {
    // A picture or a script that did not load is not an error in the code.
    if (!e.error && e.target && e.target !== window) return
    reportError(e.error || e.message, 'window')
  })
  window.addEventListener('unhandledrejection', (e) => {
    const reason = e.reason
    // A failed request already says what went wrong where it was made.
    if (reason && reason.isAxiosError) return
    reportError(reason, 'promise')
  })
}

// --- the report ------------------------------------------------------------
// Written in the app and sent from it (Backend/dannify/report.py). Closed,
// and shown as coming soon, until the report server exists.

const status = reactive({ loaded: false, enabled: false, pending: 0, captcha: null })
const dialogOpen = ref(false)
const kind = ref('') // what the dialog opens on: 'idea' from "Share an idea"
// A report written while offline, opened again to be sent: {email, url}.
const held = ref(null)
let loading = null

function loadStatus() {
  if (!loading) {
    loading = API.getReportStatus()
      .then((res) => {
        Object.assign(status, res.data || {}, { loaded: true })
      })
      .catch(() => {})
      .finally(() => {
        loading = null
      })
  }
  return loading
}

async function openReport(on = '') {
  await loadStatus()
  if (!status.enabled) return false
  await ensureFullWindow()
  kind.value = on
  dialogOpen.value = true
  return true
}

// By email the window sends it (report.py): a free Web3Forms form takes
// submissions from a browser only, and this window is one.
async function emailIt(email, url) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(email),
  })
  let answer = {}
  try {
    answer = await res.json()
  } catch {
    // not JSON: the status says enough
  }
  if (!res.ok || !answer.success) {
    const err = new Error(answer.message || `Web3Forms answered ${res.status}`)
    err.status = res.status
    throw err
  }
}

/**
 * Send one. Resolves to {id, status: 'sent' | 'queued'}; rejects on failure.
 * *captcha* is the solved hCaptcha the form asks for, when it asks.
 */
async function send(payload, captcha = '') {
  const res = await API.sendReport(payload)
  const data = res.data || {}
  if (data.status === 'prepared' && data.email) {
    const email = captcha ? { ...data.email, 'h-captcha-response': captcha } : data.email
    try {
      await emailIt(email, data.url)
      return { id: data.id, status: 'sent' }
    } catch (err) {
      // Refused by the form: the dialog says so, and keeps what was written.
      if (err.status) throw err
      // Offline, most likely: kept. A solved check lasts minutes, so one the
      // form asks for is passed again then: Dannify asks once it is back
      // online, and the person sends it with a slide (offerHeld).
      console.warn('[report] not sent now, kept for later', err)
      const preview = String(payload.description || '').trim().slice(0, 400)
      await API.holdReport({ ...data.email, held_preview: preview, held_at: Date.now() }).catch(() => {})
      status.pending += 1
      if (captcha) offerWhenBack()
      return { id: data.id, status: 'queued', needsYou: !!captcha }
    }
  }
  if (data.status === 'queued') status.pending += 1
  return data
}

// What a kept email carries for Dannify's own use, not for the inbox.
function forInbox(email) {
  return Object.fromEntries(Object.entries(email || {}).filter(([k]) => !k.startsWith('held_')))
}

// Back online after a report was kept: asked about once the connection is.
let waitingToOffer = false
async function offerWhenBack() {
  if (waitingToOffer) return
  waitingToOffer = true
  const online = await useConnectivity().probe().catch(() => false)
  if (online) {
    // The connection is there and the send still failed: asked again at the
    // next start rather than at once.
    waitingToOffer = false
    return
  }
  whenOnline(() => {
    waitingToOffer = false
    sendHeldReports()
  })
}

/** "Your report is ready to send": a toast that opens it, for one slide. */
function offerHeld(list) {
  const email = list.emails[0]
  toast(t('problems.heldReady', { count: list.emails.length }), {
    icon: 'ph:paper-plane-tilt',
    timeout: 20000,
    key: 'held-report',
    action: {
      label: t('problems.heldSend'),
      run: () => {
        held.value = { email, url: list.url }
        openReport()
      },
    },
  })
}

/** Send the kept report the dialog has open, with the check just passed. */
async function sendHeld(captcha = '') {
  const { email, url } = held.value || {}
  if (!email) throw new Error('nothing kept')
  await emailIt(captcha ? { ...forInbox(email), 'h-captcha-response': captcha } : forInbox(email), url)
  await API.reportDone(email.report_id).catch(() => {})
  status.pending = Math.max(0, status.pending - 1)
  return { id: email.report_id, status: 'sent' }
}

/** What could not go before, sent now: once, a little after the app starts.
 * When the form asks for a check, they cannot go by themselves: Dannify asks. */
export async function sendHeldReports() {
  let list
  try {
    await loadStatus()
    list = (await API.heldReports()).data || {}
  } catch {
    return 0
  }
  if (!(list.emails || []).length) return 0
  if (status.captcha) {
    offerHeld(list)
    return 0
  }
  let sent = 0
  for (const email of list.emails || []) {
    try {
      await emailIt(forInbox(email), list.url)
    } catch (err) {
      // Refused (the form now wants a check it does not carry): let go,
      // or it would be tried at every start. Offline: the rest can wait too.
      if (!err.status) break
      console.warn('[report] a waiting report was refused, and let go', err)
      await API.reportDone(email.report_id).catch(() => {})
      status.pending = Math.max(0, status.pending - 1)
      continue
    }
    await API.reportDone(email.report_id).catch(() => {})
    status.pending = Math.max(0, status.pending - 1)
    sent++
  }
  return sent
}

export function useReporting() {
  if (!status.loaded) loadStatus()
  return { status, dialogOpen, kind, held, loadStatus, openReport, send, sendHeld }
}
