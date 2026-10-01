import { ref, computed } from 'vue'
import API from '/src/model/api'
import { toast } from '/src/model/toast'
import { t } from '/src/i18n'

// Is the machine actually able to reach YouTube, not merely "has an adapter"?
//
// navigator.onLine only tells you a cable is plugged in, so it says "online"
// on captive portals and dead Wi-Fi. What matters here is whether a stream
// can be resolved, so a failed play or search reports in and the app starts
// probing until the network genuinely comes back.

const online = ref(navigator.onLine !== false)
const checking = ref(false)
const waiters = new Set()
let probeTimer = null
let announced = false

const isOffline = computed(() => !online.value)

let inflight = null

// One check at a time, and everyone who asks while it runs gets its answer,
// not the value from before it started.
function probe() {
  if (inflight) return inflight
  checking.value = true
  inflight = (async () => {
    try {
      // Our own backend asks: it is the thing that actually needs the
      // network. Its own route for this, never cached. It used to be the
      // update check, which keeps a good answer for hours, so a connection
      // lost after a morning check went on looking fine.
      const res = await API.netCheck()
      setOnline(!!(res.data && res.data.online))
    } catch {
      setOnline(false)
    } finally {
      checking.value = false
      inflight = null
    }
    return online.value
  })()
  return inflight
}

function setOnline(value) {
  const was = online.value
  online.value = !!value
  if (was === online.value) return
  if (online.value) {
    stopProbing()
    if (announced) {
      announced = false
      toast(t('net.backOnline'), { tone: 'success', icon: 'ph:wifi-high' })
    }
    for (const fn of [...waiters]) {
      waiters.delete(fn)
      try {
        fn()
      } catch {
        /* a retry that throws is the caller's problem, not ours */
      }
    }
  } else {
    startProbing()
  }
}

function startProbing() {
  if (probeTimer) return
  // Back off gently: a laptop that is asleep should not be hammered. Not too
  // far, though: at half a minute between checks, a connection that came
  // back took most of a minute to be noticed. One small request every 15 s
  // is nothing.
  let delay = 4000
  const tick = async () => {
    probeTimer = null
    if (await probe()) return
    delay = Math.min(delay * 1.6, 15000)
    probeTimer = setTimeout(tick, delay)
  }
  probeTimer = setTimeout(tick, delay)
}

function stopProbing() {
  clearTimeout(probeTimer)
  probeTimer = null
}

/**
 * Something network-shaped failed. Verify, and tell the user once.
 * Resolves to whether the network is really there.
 */
export async function reportNetworkFailure() {
  if (navigator.onLine === false) {
    setOnline(false)
  } else {
    await probe()
  }
  if (!online.value && !announced) {
    announced = true
    toast(t('net.offline'), { tone: 'error', icon: 'ph:wifi-slash', timeout: 6000 })
  }
  return online.value
}

/**
 * A request failed: was it the connection? A server that answered with a
 * "not found" or "not allowed" is not the network. Anything else is checked
 * (and said, once). Resolves to true when the machine is offline.
 */
export async function failedForNetwork(err) {
  const status = err && err.response && err.response.status
  if (status && status < 500) return false
  return !(await reportNetworkFailure())
}

/** Run `fn` as soon as the network is back (or now, if it already is). */
export function whenOnline(fn) {
  if (online.value) {
    fn()
    return
  }
  waiters.add(fn)
  startProbing()
}

if (typeof window !== 'undefined') {
  window.addEventListener('online', () => probe())
  window.addEventListener('offline', () => setOnline(false))
  // Coming back to the window is a good moment to look again: the Wi-Fi was
  // often fixed somewhere else in the meantime.
  window.addEventListener('focus', () => {
    if (!online.value) probe()
  })
}

export function useConnectivity() {
  return { online, isOffline, checking, probe, reportNetworkFailure, whenOnline }
}
