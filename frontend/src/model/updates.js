import { ref, computed, watch } from 'vue'
import API from '/src/model/api'
import { desktop } from '/src/desktop/bridge'
import { toast } from '/src/model/toast'
import { confirmDialog } from '/src/model/dialog'
import { t } from '/src/i18n'

// In-app updates from GitHub releases.
//
// Nobody should have to manage this. The app checks on its own, downloads a
// new version quietly in the background, and then says once that it is ready.
// Press restart and it applies now; ignore it and it applies the next time
// the app closes, which is how a browser does it and why browser updates
// never feel like a chore.
//
// The backend does the network work; this is the state the UI binds to.

const SKIP_KEY = 'dannify-skipped-update'
const info = ref({ available: false, version: '', notes: '', url: '', size: 0, repo_url: '' })
// Where this build's source lives. Comes from the backend so a fork
// changes one config file rather than hunting for a hard-coded URL.
const repoUrl = computed(
  () => info.value.repo_url || 'https://github.com/DANIELMWENDWA9451/Dannify'
)
const checking = ref(false)
const downloading = ref(false)
const progress = ref(0)
const installerPath = ref('')
const lastError = ref('')
const skipped = ref(localStorage.getItem(SKIP_KEY) || '')

// Automatic downloading can be turned off for anyone who would rather decide
// for themselves. On by default: the whole point is that it is not a decision.
const AUTO_KEY = 'dannify-auto-update'
const autoUpdate = ref(localStorage.getItem(AUTO_KEY) !== '0')

function setAutoUpdate(on) {
  autoUpdate.value = !!on
  try {
    localStorage.setItem(AUTO_KEY, autoUpdate.value ? '1' : '0')
  } catch {
    // The choice just will not survive a restart.
  }
}

const available = computed(
  () => !!info.value.available && info.value.version !== skipped.value
)
const ready = computed(() => !!installerPath.value)

if (typeof window !== 'undefined') {
  window.addEventListener('dannify:update-progress', (e) => {
    const value = e.detail && e.detail.progress
    if (typeof value === 'number') progress.value = value
  })
}

async function check(force = false, { quiet = true } = {}) {
  if (checking.value) return info.value
  checking.value = true
  lastError.value = ''
  try {
    const res = await API.checkForUpdate(force)
    info.value = res.data || {}
    lastError.value = info.value.error || ''
    if (!quiet && !info.value.available) {
      toast(t('update.upToDate', { version: info.value.current || '' }), {
        icon: 'ph:check-circle',
      })
    }
  } catch (e) {
    lastError.value = e.message || 'error'
    if (!quiet) toast(t('update.checkFailed'), { tone: 'error' })
  } finally {
    checking.value = false
  }
  return info.value
}

async function download({ quiet = false } = {}) {
  if (downloading.value || !info.value.download_url) {
    if (!info.value.download_url && !quiet) {
      // No installer asset on the release: send them to the release page.
      desktop.openExternal(info.value.url || '')
    }
    return false
  }
  downloading.value = true
  progress.value = 0
  try {
    const res = await API.downloadUpdate(info.value.download_url)
    installerPath.value = (res.data && res.data.path) || ''
    progress.value = 100
    // Tell the shell about it so closing the app is enough to apply it.
    if (installerPath.value) desktop.stageUpdate(installerPath.value)
    return true
  } catch (e) {
    const detail = (e.response && e.response.data && e.response.data.detail) || ''
    // A background attempt that fails says nothing: it will be retried, and
    // an error about work the user never asked for is just noise.
    if (!quiet) toast(detail || t('update.downloadFailed'), { tone: 'error' })
    return false
  } finally {
    downloading.value = false
  }
}

/** Run the downloaded installer. Dannify closes so it can replace itself. */
async function install({ ask = true } = {}) {
  if (!installerPath.value) return false
  if (!ask) return desktop.installUpdate(installerPath.value)
  const ok = await confirmDialog({
    title: t('update.installTitle', { version: info.value.version }),
    message: t('update.installMessage'),
    confirmText: t('update.installNow'),
    icon: 'ph:download-simple',
  })
  if (!ok) return false
  const started = await desktop.installUpdate(installerPath.value)
  if (!started) toast(t('update.installFailed'), { tone: 'error' })
  return started
}

/** Download and install in one step: what the update button does. */
async function downloadAndInstall() {
  if (!ready.value && !(await download())) return false
  return install()
}

function skipVersion() {
  skipped.value = info.value.version || ''
  try {
    localStorage.setItem(SKIP_KEY, skipped.value)
  } catch {
    // ignore
  }
}

// --- The automatic part ---------------------------------------------------
//
// Check shortly after launch, then every six hours: the backend caches, so a
// repeat call inside that window costs nothing.
//
// When something is found, fetch it in the background. Two rules about when:
// not while a track is playing, because a 48 MB download competing with the
// stream is a stutter the user will blame on the player; and not instantly on
// launch, because the first seconds belong to whatever they opened the app to
// do. Failures retry with a widening gap rather than hammering.

let autoTimer = null
let autoAttempts = 0
const RETRY_STEPS = [60_000, 5 * 60_000, 20 * 60_000, 60 * 60_000]

function announceReady() {
  toast(t('update.readyToast', { version: info.value.version }), {
    icon: 'ph:sparkle-fill',
    tone: 'success',
    timeout: 9000,
    action: { label: t('update.restartNow'), run: () => install({ ask: false }) },
  })
}

async function tryAutoDownload() {
  clearTimeout(autoTimer)
  if (!autoUpdate.value || !available.value || ready.value || downloading.value) return
  // Wait for a quiet moment rather than fighting the stream for bandwidth.
  let playing = false
  try {
    const { usePlayer } = await import('/src/model/player')
    playing = !!usePlayer().isPlaying.value
  } catch {
    // Player not up yet; treat that as quiet.
  }
  if (playing) {
    autoTimer = setTimeout(tryAutoDownload, 90_000)
    return
  }
  const ok = await download({ quiet: true })
  if (ok) {
    autoAttempts = 0
    announceReady()
    return
  }
  const wait = RETRY_STEPS[Math.min(autoAttempts, RETRY_STEPS.length - 1)]
  autoAttempts += 1
  autoTimer = setTimeout(tryAutoDownload, wait)
}

if (typeof window !== 'undefined') {
  setTimeout(() => check(false), 8000)
  setInterval(() => check(false), 6 * 60 * 60 * 1000)
  // A found update starts downloading itself half a minute later.
  watch(available, (yes) => {
    if (yes) {
      autoAttempts = 0
      clearTimeout(autoTimer)
      autoTimer = setTimeout(tryAutoDownload, 30_000)
    } else {
      clearTimeout(autoTimer)
    }
  })
}

export function useUpdates() {
  return {
    info,
    repoUrl,
    available,
    ready,
    checking,
    downloading,
    progress,
    lastError,
    check,
    download,
    install,
    autoUpdate,
    setAutoUpdate,
    downloadAndInstall,
    skipVersion,
  }
}
