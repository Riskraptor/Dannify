import { ref, computed } from 'vue'
import API from '/src/model/api'
import { desktop } from '/src/desktop/bridge'
import { toast } from '/src/model/toast'
import { confirmDialog } from '/src/model/dialog'
import { t } from '/src/i18n'

// In-app updates from GitHub releases: check → download the installer (with
// live progress over the websocket) → run it. The backend does the network
// work; this is the state the UI binds to.

const SKIP_KEY = 'dannify-skipped-update'
const info = ref({ available: false, version: '', notes: '', url: '', size: 0 })
const checking = ref(false)
const downloading = ref(false)
const progress = ref(0)
const installerPath = ref('')
const lastError = ref('')
const skipped = ref(localStorage.getItem(SKIP_KEY) || '')

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

async function download() {
  if (downloading.value || !info.value.download_url) {
    if (!info.value.download_url) {
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
    return true
  } catch (e) {
    const detail = (e.response && e.response.data && e.response.data.detail) || ''
    toast(detail || t('update.downloadFailed'), { tone: 'error' })
    return false
  } finally {
    downloading.value = false
  }
}

/** Run the downloaded installer. Dannify closes so it can replace itself. */
async function install() {
  if (!installerPath.value) return false
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

// Check shortly after launch, then every six hours: the backend caches, so
// a repeat call inside that window costs nothing.
if (typeof window !== 'undefined') {
  setTimeout(() => check(false), 8000)
  setInterval(() => check(false), 6 * 60 * 60 * 1000)
}

export function useUpdates() {
  return {
    info,
    available,
    ready,
    checking,
    downloading,
    progress,
    lastError,
    check,
    download,
    install,
    downloadAndInstall,
    skipVersion,
  }
}
