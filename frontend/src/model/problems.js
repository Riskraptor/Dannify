import { reactive, ref } from 'vue'
import API from '/src/model/api'
import router from '/src/router'
import { ensureFullWindow } from '/src/desktop/fullWindow'

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

const status = reactive({ loaded: false, enabled: false, pending: 0 })
const dialogOpen = ref(false)
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

async function openReport() {
  await loadStatus()
  if (!status.enabled) return false
  await ensureFullWindow()
  dialogOpen.value = true
  return true
}

/** Send one. Resolves to {id, status: 'sent' | 'queued'}; rejects on failure. */
async function send(payload) {
  const res = await API.sendReport(payload)
  if (res.data && res.data.status === 'queued') status.pending += 1
  return res.data
}

export function useReporting() {
  if (!status.loaded) loadStatus()
  return { status, dialogOpen, loadStatus, openReport, send }
}
