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

async function probe() {
  if (checking.value) return online.value
  checking.value = true
  try {
    // Our own backend proxies the reachability question: it is the thing
    // that actually needs the network, and it never caches this route.
    const res = await API.checkForUpdate(false)
    // A reachable GitHub means a reachable internet. `error` set means the
    // request completed but could not get out.
    setOnline(!(res.data && res.data.error))
  } catch {
    setOnline(false)
  } finally {
    checking.value = false
  }
  return online.value
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
  // Back off gently: a laptop that is asleep should not be hammered.
  let delay = 4000
  const tick = async () => {
    probeTimer = null
    if (await probe()) return
    delay = Math.min(delay * 1.6, 30000)
    probeTimer = setTimeout(tick, delay)
  }
  probeTimer = setTimeout(tick, delay)
}

function stopProbing() {
  clearTimeout(probeTimer)
  probeTimer = null
}

/** Something network-shaped failed. Verify, and tell the user once. */
export function reportNetworkFailure() {
  if (navigator.onLine === false) {
    setOnline(false)
  } else {
    probe()
  }
  if (!online.value && !announced) {
    announced = true
    toast(t('net.offline'), { tone: 'error', icon: 'ph:wifi-slash', timeout: 6000 })
  }
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
}

export function useConnectivity() {
  return { online, isOffline, checking, probe, reportNetworkFailure, whenOnline }
}
