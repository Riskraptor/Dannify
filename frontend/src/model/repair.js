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

// Set when somebody presses Stop, so the end of that round is reported as
// stopped rather than as a result.
let stopping = false

function apply(next) {
  if (!next || typeof next !== 'object' || !next.items) return
  // Two threads report on the backend and their messages can land out of
  // order. The newest wins, not the last to arrive: otherwise an old
  // "still repairing" could be the final word and the spinner never stops.
  if (next.epoch === seen.epoch && next.seq <= seen.seq) return
  seen = { epoch: next.epoch, seq: next.seq }
  const before = status.value
  status.value = next
  announce(next)
  if (before.running && !next.running) finished(next)
  poll(next.running)
}

// How a round of more than one went. A round of one is reported by
// announce(), next to the song it was about.
function finished(round) {
  if (stopping) {
    stopping = false
    return
  }
  if (round.total < 2) return
  if (!round.failed) {
    toast(t('repair.doneAll', { count: round.fixed || round.total }), {
      icon: 'ph:check-circle',
      tone: 'success',
      timeout: 6000,
    })
    return
  }
  let text = `${t('repair.doneSome', { fixed: round.fixed, total: round.total })} ${t(
    'repair.failedSome',
    { count: round.failed }
  )}`
  // One reason for all of them is worth saying: "no internet" is the fix.
  const reasons = new Set(
    Object.values(round.items || {})
      .filter((i) => i.state === 'failed')
      .map((i) => i.reason)
  )
  if (reasons.size === 1) text += ` ${reasonText([...reasons][0])}`
  const failed = failedRepairs()
  toast(text, {
    tone: 'error',
    timeout: 12000,
    action: { label: t('repair.retry'), run: () => repairFiles(failed) },
  })
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
  const unavailable = err && err.response && err.response.status === 409
  toast(t(unavailable ? 'repair.unavailable' : 'repair.couldNotStart'), { tone: 'error' })
}

// Said once, when a round of several starts here: the button that started
// it has just gone, and the ring that replaced it is small.
function started(snapshot) {
  const count = Object.keys((snapshot && snapshot.items) || {}).length
  if (count > 1 && snapshot.running) {
    stopping = false
    toast(t('repair.started', { count }), { icon: 'ph:wrench', timeout: 5000 })
  }
}

/** Repair these files (paths inside the music folder). */
export async function repairFiles(files, { force = false } = {}) {
  const list = [...new Set((files || []).filter(Boolean))]
  if (!list.length) return
  if (list.length === 1) watching.add(list[0])
  try {
    const snapshot = (await API.repairTracks({ files: list, force })).data
    apply(snapshot)
    if (list.length > 1) started(snapshot)
  } catch (err) {
    list.forEach((f) => watching.delete(f))
    failedToStart(err)
  }
}

/** Repair every saved song the library finds a problem with. */
export async function repairAll() {
  try {
    const snapshot = (await API.repairTracks({ all: true })).data
    apply(snapshot)
    // A round of one gets the message a single row's repair gets, or it
    // would finish in silence.
    const files = Object.keys((snapshot && snapshot.items) || {})
    if (files.length === 1) {
      watching.add(files[0])
      announce(status.value)
    } else {
      started(snapshot)
    }
  } catch (err) {
    failedToStart(err)
  }
}

export async function stopRepairs() {
  stopping = true
  try {
    apply((await API.repairStop()).data)
    toast(t('repair.stopped'), { icon: 'ph:stop-circle' })
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
