import { ref } from 'vue'
import API from '/src/model/api'
import { useLibrary } from '/src/model/library'
import { toast } from '/src/model/toast'
import { t } from '/src/i18n'

// Saved tracks that will not play, downloaded again where they were.
//
// The backend does the work and reports on it over the socket. This keeps
// the newest report for everything that shows it: the banner, the rows of
// the library, and the message after a track fails to play.

const status = ref({
  running: false,
  total: 0,
  done: 0,
  fixed: 0,
  failed: 0,
  fine: 0,
  items: {},
})
let seen = { epoch: '', seq: -1 }

// Files asked about one at a time. Each gets a message when it finishes,
// because nothing else on screen would say how it went.
const watching = new Set()

function apply(next) {
  if (!next || typeof next !== 'object' || !next.items) return
  // Two threads report on the backend and their messages can land out of
  // order. The newest wins, not the last to arrive: otherwise an old
  // "still repairing" could be the final word and the spinner never stops.
  if (next.epoch === seen.epoch && next.seq <= seen.seq) return
  seen = { epoch: next.epoch, seq: next.seq }
  status.value = next
  announce(next)
  poll(next.running)
}

function titleOf(file) {
  const found = useLibrary().tracks.value.find((tr) => tr.file === file)
  if (found && found.title) return found.title
  const name = String(file || '')
    .split('/')
    .pop()
    .replace(/\.dnf$/i, '')
  const cut = name.indexOf(' - ')
  return cut > 0 ? name.slice(cut + 3) : name
}

export function reasonText(reason) {
  return t(`repair.why.${reason || 'failed'}`)
}

function announce(next) {
  for (const file of [...watching]) {
    const item = next.items[file]
    if (!item || item.state === 'queued' || item.state === 'working') continue
    watching.delete(file)
    const title = titleOf(file)
    if (item.state === 'fixed') {
      toast(t('repair.fixedOne', { title }), { icon: 'ph:check-circle', tone: 'success' })
    } else if (item.state === 'fine') {
      toast(t('repair.fineOne', { title }), { icon: 'ph:check-circle' })
    } else {
      toast(t('repair.failedOne', { title, why: reasonText(item.reason) }), {
        tone: 'error',
        timeout: 9000,
        action: { label: t('repair.retry'), run: () => repairFiles([file]) },
      })
    }
  }
}

// The socket is the fast path, not the only one. If it drops halfway
// through, a banner that only listened would say "Repairing 3 of 12" for
// ever, so while anything is running the state is also asked for.
let timer = null
function poll(running) {
  if (running && !timer) {
    timer = setInterval(refreshStatus, 4000)
  } else if (!running && timer) {
    clearInterval(timer)
    timer = null
  }
}

async function refreshStatus() {
  try {
    apply((await API.repairStatus()).data)
  } catch {
    // The next report or poll will do.
  }
}

function failedToStart(err) {
  const noKey = err && err.response && err.response.status === 409
  toast(t(noKey ? 'repair.noKey' : 'repair.couldNotStart'), { tone: 'error' })
}

/** Repair these files (paths inside the music folder). */
export async function repairFiles(files, { force = false } = {}) {
  const list = [...new Set((files || []).filter(Boolean))]
  if (!list.length) return
  if (list.length === 1) watching.add(list[0])
  try {
    apply((await API.repairTracks({ files: list, force })).data)
  } catch (err) {
    list.forEach((f) => watching.delete(f))
    failedToStart(err)
  }
}

/** Repair every saved track the library finds a problem with. */
export async function repairAll() {
  try {
    const snapshot = (await API.repairTracks({ all: true })).data
    apply(snapshot)
    // The banner reports rounds of more than one. A round of one gets the
    // message a single row's repair gets, or it would finish in silence.
    const files = Object.keys((snapshot && snapshot.items) || {})
    if (files.length === 1) {
      watching.add(files[0])
      announce(status.value)
    }
  } catch (err) {
    failedToStart(err)
  }
}

export async function stopRepairs() {
  try {
    apply((await API.repairStop()).data)
  } catch {
    // Nothing to stop, or it stopped on its own.
  }
}

/** 'queued' | 'working' | 'fixed' | 'failed' | 'fine' | '' for one file. */
export function repairStateOf(file) {
  const item = file && status.value.items[file]
  return item ? item.state : ''
}

export function repairItemOf(file) {
  return (file && status.value.items[file]) || null
}

export function failedRepairs() {
  return Object.entries(status.value.items)
    .filter(([, item]) => item.state === 'failed')
    .map(([file]) => file)
}

if (typeof window !== 'undefined') {
  window.addEventListener('dannify:repair', (e) => apply(e.detail))
  refreshStatus()
}

export function useRepair() {
  return {
    status,
    repairFiles,
    repairAll,
    stopRepairs,
    repairStateOf,
    repairItemOf,
    failedRepairs,
    reasonText,
    refreshStatus,
  }
}
