import API from '/src/model/api'
import router from '/src/router'
import { toast } from '/src/model/toast'
import { desktop } from '/src/desktop/bridge'
import { t } from '/src/i18n'

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

const busy = { value: false }

/** Save the logs and details in one file and show it. Resolves to its path. */
export async function saveProblemReport() {
  if (busy.value) return ''
  busy.value = true
  try {
    const res = await API.makeProblemReport()
    const path = res.data && res.data.path
    if (desktop.isDesktop && path) desktop.revealReport(path)
    toast(t('problems.saved', { name: res.data.name }), { icon: 'ph:file-zip', timeout: 9000 })
    return path || ''
  } catch {
    toast(t('problems.failed'), { tone: 'error', icon: 'ph:warning' })
    return ''
  } finally {
    busy.value = false
  }
}
