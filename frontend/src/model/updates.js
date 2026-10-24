import { ref, computed, watch } from 'vue'
import API from '/src/model/api'
import { desktop } from '/src/desktop/bridge'
import { toast } from '/src/model/toast'
import { confirmDialog } from '/src/model/dialog'
import { hasNotes, readNotes } from '/src/model/releaseNotes'
import { isBigRelease } from '/src/model/occasions'
import { t, currentLocale } from '/src/i18n'
import { restartKindly } from '/src/model/restart'

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
const NOTICES_KEY = 'dannify-notices-seen'

/**
 * How a version is said. A fix build has a fourth number (4.15.0.1): it is
 * the same release, put right, and reads that way ("4.15.0 · fix 1").
 */
export function versionLabel(version) {
  const parts = String(version || '').replace(/^v/i, '').split('.')
  if (parts.length === 4 && /^\d+$/.test(parts[3]) && Number(parts[3]) > 0) {
    return t('update.fixLabel', { version: parts.slice(0, 3).join('.'), n: Number(parts[3]) })
  }
  return String(version || '')
}

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
  () => info.value.site_url || 'https://github.com/Riskraptor/Dannify/releases'
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
// When a check last came back (ms), for "checked 2 minutes ago".
const checkedAt = ref(0)
// An important fix for this version, from the signed live file (live.py):
// { version, notes }. It is fetched and offered without waiting.
const emergency = ref(null)
// Whether a check has actually come back this session. Until one has, "up to
// date" is not something anybody knows: it was shown all the same, offline.
const checkedOk = ref(false)
const skipped = ref(read(SKIP_KEY, ''))

// Automatic downloading can be turned off for anyone who would rather decide
// for themselves. On by default: the whole point is that it is not a decision.
const autoUpdate = ref(read(AUTO_KEY, '1') !== '0')

function setAutoUpdate(on) {
  autoUpdate.value = !!on
  write(AUTO_KEY, autoUpdate.value ? '1' : '0')
}

// A copy that cannot install over itself (Linux or macOS run from source, an
// app somewhere it cannot be replaced) is pointed at the download page
// instead. The check says so up front; a download the backend turns down as
// 'manual_update' says it after the fact, and is believed just the same.
const manualOnly = ref(false)
const manual = computed(() => info.value.self_update === false || manualOnly.value)
const downloadPage = computed(() => info.value.url || siteUrl.value)

function openDownloadPage() {
  return desktop.openExternal(downloadPage.value)
}

function isManualRefusal(e) {
  const r = e && e.response
  return !!r && r.status === 409 && !!r.data && r.data.detail === 'manual_update'
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
    if (!fresh.error) {
      checkedOk.value = true
      checkedAt.value = Date.now()
    }
    // "Up to date" only after a check that was answered. Up to 4.14.1 a check
    // GitHub refused said it too, while About said it could not check.
    if (!quiet && !info.value.available) {
      if (fresh.error) {
        toast(navigator.onLine === false ? t('update.offline') : t('update.checkFailedLater'), { tone: 'error' })
      } else {
        toast(t('update.upToDate', { version: fresh.current || '' }), { icon: 'ph:check-circle' })
      }
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
  if (manual.value) {
    if (!quiet) openDownloadPage()
    return false
  }
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
    if (isManualRefusal(e)) {
      manualOnly.value = true
      stageCode.value = ''
      if (!quiet) openDownloadPage()
      return false
    }
    // A background attempt that fails says nothing: it will be retried, and
    // an error about work the user never asked for is just noise.
    console.warn('[update] download failed', e)
    if (!quiet) toast(t('update.downloadFailed'), { tone: 'error' })
    return false
  } finally {
    downloading.value = false
  }
}

// Which system the update installs on. The release names its own kind
// ('installer-linux-deb-amd64', 'app-macos-zip-arm64'); the shell is asked
// only when it does not.
function installSystem() {
  const kind = String(info.value.installer_kind || '')
  if (/android/.test(kind)) return 'android'
  if (/linux/.test(kind)) return 'linux'
  if (/macos/.test(kind)) return 'macos'
  return (desktop.platform && desktop.platform.value) || 'windows'
}

const INSTALL_MESSAGE = {
  windows: 'update.installMessage',
  linux: 'update.installMessageLinux',
  macos: 'update.installMessageMac',
  android: 'update.installMessageAndroid',
}

/** Apply the prepared update: restart into it. */
async function install({ ask = true } = {}) {
  if (!installerPath.value) return false
  if (updateKind.value === 'staged') return restartKindly(() => desktop.restart())
  // On Linux the package manager asks for the system password, and a
  // password prompt nobody was told about looks like something else asking.
  // So it is said first there, on macOS too, where the app reopens, and on
  // Android, which asks to confirm and closes the app to install it.
  const system = installSystem()
  if (!ask && system === 'windows') return restartKindly(() => desktop.installUpdate(installerPath.value))
  const ok = await confirmDialog({
    title: t('update.installTitle', { version: info.value.version }),
    message: t(INSTALL_MESSAGE[system] || INSTALL_MESSAGE.windows),
    confirmText: t('update.installNow'),
    icon: 'ph:download-simple',
  })
  if (!ok) return false
  const started = await restartKindly(() => desktop.installUpdate(installerPath.value))
  if (!started) toast(t('update.installFailed'), { tone: 'error' })
  return started
}

/** Download (if needed) and apply in one step: what "update now" does. */
async function downloadAndInstall() {
  if (manual.value) {
    openDownloadPage()
    return false
  }
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

/** The version Dannify just updated to, while its "What's new" is open. */
export const whatsNew = ref(null)

function showWhatsNew(version, notes, { celebrate = false } = {}) {
  whatsNew.value = { version, notes: String(notes || ''), celebrate }
}

let rollbackShown = false

async function loadStatus() {
  try {
    const { data } = await API.updateStatus()
    if (data && data.pending && data.pending.version) {
      updateKind.value = 'staged'
      installerPath.value = 'staged'
      info.value = { ...info.value, available: true, version: data.pending.version }
    }
    // The launcher took a new version back out because it would not start.
    // That used to happen without a word; say it once a session.
    if (data && data.rolled_back && data.rolled_back.version && !rollbackShown) {
      rollbackShown = true
      toast(
        t('update.rolledBack', {
          version: data.rolled_back.version,
          running: data.rolled_back.running || '',
        }),
        {
          icon: 'ph:arrow-counter-clockwise',
          tone: 'error',
          timeout: 15000,
        }
      )
    }
    if (data && data.just_updated && data.just_updated.version) {
      const { version, notes } = data.just_updated
      API.acknowledgeUpdate().catch(() => {})
      // A release with something new in it is welcomed: What's new opens on
      // its own, as a celebration. A fix is told in a line.
      if (isBigRelease(version) && hasNotes(readNotes(notes))) {
        showWhatsNew(version, notes, { celebrate: true })
        return
      }
      toast(t('update.updatedToast', { version }), {
        icon: 'ph:sparkle-fill',
        tone: 'success',
        timeout: 10000,
        action: hasNotes(readNotes(notes))
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
// When waiting on streaming music began, and the longest it waits.
let deferredSince = 0
const MAX_DEFER = 30 * 60_000
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
  if (!autoUpdate.value || !available.value || ready.value || downloading.value || manual.value) return
  // Wait for a quiet moment rather than fighting the stream for bandwidth.
  // Waiting while music streams keeps the connection for the music. A saved
  // song needs none, so it does not hold the update back; and someone who
  // streams all day still gets it within half an hour.
  let playing = false
  try {
    const { usePlayer } = await import('/src/model/player')
    const player = usePlayer()
    const track = player.currentTrack.value
    playing = !!player.isPlaying.value && !!track && track.type !== 'local'
  } catch {
    // Player not up yet; treat that as quiet.
  }
  // An important fix does not wait for the song to end.
  const urgent = !!emergency.value && emergency.value.version === info.value.version
  if (!urgent && playing && Date.now() - (deferredSince || (deferredSince = Date.now())) < MAX_DEFER) {
    autoTimer = setTimeout(tryAutoDownload, 90_000)
    return
  }
  deferredSince = 0
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

// --- Fixes that cannot wait, and notices -----------------------------------
//
// The signed live file (Backend/dannify/live.py) can say a fix build is out
// for this version. Then it is checked for at once rather than at the next
// six-hourly look, fetched even while music plays, and offered plainly: what
// it puts right, and Update now. "Later" asks again in two hours.

let emergencyAskedAt = 0
const ASK_AGAIN = 2 * 60 * 60 * 1000

function seenNotices() {
  try {
    return JSON.parse(read(NOTICES_KEY, '[]')) || []
  } catch {
    return []
  }
}

function inMyLanguage(texts) {
  const lang = String(currentLocale.value || 'en').split('-')[0]
  return (texts && (texts[lang] || texts.en || Object.values(texts)[0])) || ''
}

async function offerEmergency() {
  const em = emergency.value
  if (!em || ready.value || Date.now() - emergencyAskedAt < ASK_AGAIN) return
  if (!info.value.available || info.value.version !== em.version) return
  emergencyAskedAt = Date.now()
  const go = await confirmDialog({
    title: t('update.emergencyTitle'),
    message: inMyLanguage(em.notes) || t('update.emergencyFallback'),
    detail: t('update.emergencyDetail', { version: versionLabel(em.version) }),
    confirmText: t('update.emergencyGo'),
    cancelText: t('update.emergencyLater'),
    icon: 'ph:first-aid-kit',
  })
  if (go) downloadAndInstall()
}

async function loadLive() {
  let data
  try {
    data = (await API.getLive()).data || {}
  } catch {
    return
  }
  emergency.value = data.emergency || null
  if (emergency.value) {
    await check(true)
    offerEmergency()
  }
  const notice = data.notice
  if (notice && notice.id) {
    const seen = seenNotices()
    if (!seen.includes(notice.id)) {
      write(NOTICES_KEY, JSON.stringify([...seen.slice(-20), notice.id]))
      const text = inMyLanguage(notice.text)
      if (text) toast(text, { icon: 'ph:megaphone-simple', timeout: 15000, key: 'notice' })
    }
  }
}

if (typeof window !== 'undefined') {
  setTimeout(loadStatus, 2500)
  setTimeout(() => check(false), 8000)
  setInterval(() => check(false), 6 * 60 * 60 * 1000)
  setTimeout(loadLive, 6000)
  setInterval(loadLive, 60 * 60 * 1000)
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
    checkedOk,
    checkedAt,
    emergency,
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
    manual,
    openDownloadPage,
  }
}
