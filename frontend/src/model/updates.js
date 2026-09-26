import { ref, computed, watch } from 'vue'
import API from '/src/model/api'
import { desktop } from '/src/desktop/bridge'
import { toast } from '/src/model/toast'
import { alertDialog, confirmDialog } from '/src/model/dialog'
import { t, currentLocale } from '/src/i18n'

// In-app updates.
//
// Nobody should have to manage this. The app checks on its own, gets a new
// version ready in the background, and then says once that it is ready.
// Restart and it is there; ignore it and it is there the next time Dannify
// opens. Nothing the running app uses is ever replaced while it runs: the
// new version is built beside it and swapped in by the launcher at start.
//
// The backend does the network work; this is the state the UI binds to.

const SKIP_KEY = 'dannify-skipped-update'
const AUTO_KEY = 'dannify-auto-update'

function read(key, fallback) {
  try {
    return localStorage.getItem(key) ?? fallback
  } catch {
    // Blocked storage: the default is fine.
    return fallback
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // The choice just will not survive a restart.
  }
}

const info = ref({ available: false, version: '', notes: '', url: '', size: 0, site_url: '' })
// The product page. Comes from the backend so a rebrand changes one config
// file rather than a hard-coded URL in here.
const siteUrl = computed(
  () => info.value.site_url || 'https://github.com/DANIELMWENDWA9451/dannify-releases/releases'
)
const checking = ref(false)
const downloading = ref(false)
const progress = ref(0)
// What the update is doing, as a stage name from the backend plus bytes, so
// it can be said in the user's language.
const stageCode = ref('')
const stageBytes = ref({ done: 0, total: 0 })
// Where the prepared update is, and what kind it is: 'staged' (an installed
// copy, applied by the launcher) or 'installer' (anything else).
const installerPath = ref('')
const updateKind = ref('installer')
const lastError = ref('')
const skipped = ref(read(SKIP_KEY, ''))

// Automatic downloading can be turned off for anyone who would rather decide
// for themselves. On by default: the whole point is that it is not a decision.
const autoUpdate = ref(read(AUTO_KEY, '1') !== '0')

function setAutoUpdate(on) {
  autoUpdate.value = !!on
  write(AUTO_KEY, autoUpdate.value ? '1' : '0')
}

const available = computed(
  () => !!info.value.available && info.value.version !== skipped.value
)
const ready = computed(() => !!installerPath.value)

function megabytes(bytes) {
  const mb = (Number(bytes) || 0) / 1048576
  const formatted = new Intl.NumberFormat(currentLocale.value || 'en', {
    maximumFractionDigits: mb < 10 ? 1 : 0,
  }).format(mb)
  return `${formatted} ${t('update.mb')}`
}

const stage = computed(() => {
  const code = stageCode.value
  if (!code) return ''
  const { done, total } = stageBytes.value
  if (code === 'downloading' && total > 0) {
    return t('update.stage.downloadingOf', { done: megabytes(done), total: megabytes(total) })
  }
  return t(`update.stage.${code}`)
})

if (typeof window !== 'undefined') {
  window.addEventListener('dannify:update-progress', (e) => {
    const d = e.detail || {}
    if (typeof d.progress === 'number') progress.value = d.progress
    if (typeof d.stage === 'string' && d.stage) {
      stageCode.value = d.stage
      stageBytes.value = { done: Number(d.done) || 0, total: Number(d.total) || 0 }
    }
  })
}

async function check(force = false, { quiet = true } = {}) {
  if (checking.value) return info.value
  checking.value = true
  lastError.value = ''
  try {
    const res = await API.checkForUpdate(force)
    const fresh = res.data || {}
    // An update already prepared stays prepared: a check that finds the
    // same version must not hide the "restart to update" button.
    info.value = { ...fresh, available: !!fresh.available || (ready.value && fresh.version === info.value.version) }
    lastError.value = fresh.error || ''
    if (!quiet && !info.value.available) {
      toast(t('update.upToDate', { version: fresh.current || '' }), {
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
  if (downloading.value) return false
  if (!info.value.package_url && !info.value.download_url) {
    if (!quiet) toast(t('update.downloadFailed'), { tone: 'error' })
    return false
  }
  downloading.value = true
  progress.value = 0
  stageCode.value = 'starting'
  try {
    const res = await API.downloadUpdate(info.value.download_url)
    const data = res.data || {}
    installerPath.value = data.path || ''
    updateKind.value = data.kind || 'installer'
    progress.value = 100
    stageCode.value = 'ready'
    // An installer (for a copy that cannot update itself in place) is run by
    // the shell when the app closes. A staged update needs nothing: the
    // launcher finds it at the next start.
    if (installerPath.value && updateKind.value === 'installer') {
      desktop.stageUpdate(installerPath.value)
    }
    return true
  } catch (e) {
    // A background attempt that fails says nothing: it will be retried, and
    // an error about work the user never asked for is just noise.
    console.warn('[update] download failed', e)
    if (!quiet) toast(t('update.downloadFailed'), { tone: 'error' })
    return false
  } finally {
    downloading.value = false
  }
}

/** Apply the prepared update: restart into it. */
async function install({ ask = true } = {}) {
  if (!installerPath.value) return false
  if (updateKind.value === 'staged') return desktop.restart()
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

/** Download (if needed) and apply in one step: what "update now" does. */
async function downloadAndInstall() {
  if (!ready.value && !(await download())) return false
  return install({ ask: false })
}

function skipVersion() {
  skipped.value = info.value.version || ''
  write(SKIP_KEY, skipped.value)
  if (updateKind.value === 'staged' && installerPath.value) {
    installerPath.value = ''
    API.discardUpdate().catch(() => {})
  } else {
    desktop.clearStagedUpdate?.()
    installerPath.value = ''
  }
}

// --- After a restart ---------------------------------------------------------
//
// Two things the launcher leaves behind for the interface: an update that is
// still waiting (the app was restarted before it could be swapped in), and
// the note that one just was, which is shown once.

function noteLines(notes) {
  return String(notes || '')
    .split(/\r?\n+/)
    .map((l) => l.replace(/^[#*\-\s]+/, '').trim())
    .filter(Boolean)
    .slice(0, 10)
}

async function showWhatsNew(version, notes) {
  const lines = noteLines(notes)
  await alertDialog({
    title: t('update.whatsNewTitle', { version }),
    message: lines.join('\n') || t('update.whatsNewEmpty'),
    confirmText: t('update.gotIt'),
    icon: 'ph:sparkle-fill',
  })
}

async function loadStatus() {
  try {
    const { data } = await API.updateStatus()
    if (data && data.pending && data.pending.version) {
      updateKind.value = 'staged'
      installerPath.value = 'staged'
      info.value = { ...info.value, available: true, version: data.pending.version }
    }
    if (data && data.just_updated && data.just_updated.version) {
      const { version, notes } = data.just_updated
      API.acknowledgeUpdate().catch(() => {})
      toast(t('update.updatedToast', { version }), {
        icon: 'ph:sparkle-fill',
        tone: 'success',
        timeout: 10000,
        action: noteLines(notes).length
          ? { label: t('update.whatsNew'), run: () => showWhatsNew(version, notes) }
          : undefined,
      })
    }
  } catch {
    // An older backend, or none yet: nothing to say.
  }
}

// --- The automatic part ---------------------------------------------------
//
// Check shortly after launch, then every six hours: the backend caches, so a
// repeat call inside that window costs nothing.
//
// When something is found, fetch it in the background. Two rules about when:
// not while a track is playing, because a download competing with the stream
// is a stutter the user will blame on the player; and not instantly on
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
  setTimeout(loadStatus, 2500)
  setTimeout(() => check(false), 8000)
  setInterval(() => check(false), 6 * 60 * 60 * 1000)
  // A found update starts getting ready by itself half a minute later.
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
    siteUrl,
    available,
    ready,
    checking,
    downloading,
    progress,
    stage,
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
