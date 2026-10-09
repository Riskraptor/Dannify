// The lyrics editor's state from opening to publishing: the song's details,
// the words, which step is showing, the draft kept along the way, and the
// publishing itself.
//
// The player is passed in rather than imported, so the whole flow can be
// driven in a test with a stand-in for it.

import { ref, computed, watch } from 'vue'
import { mergeTimes, wordsOf, outText, BREAK } from '/src/model/lyricsMerge'
import { hasStamps, parseLrc, splitWords, toSynced, toPlain } from './lrc'
import { enoughTimed, minTimed, nextIssue } from './timing'
import { createLineEditor } from './lineEditor'
import { draftKey, loadDraft, saveDraft, clearDraft } from './draft'
import { sendLyrics, announcePublished } from './publish'

export const WORDS = 0
export const SYNC = 1
export const REVIEW = 2

/** What the editor's parts inject to reach the open session. */
export const LYRICS_EDITOR = Symbol('lyrics-editor')

const SAVE_DELAY = 500

function emptyForm() {
  return { track: '', artist: '', album: '', duration: 0, raw: '' }
}

export function useLyricsSubmit({ player }) {
  const editor = createLineEditor()
  const form = ref(emptyForm())
  const phase = ref(WORDS)
  // The song the editor was opened on, for its header: steady while the
  // details below it are being corrected.
  const song = ref({ title: '', artist: '' })
  const cover = ref('')
  // The details are opened only to correct them.
  const detailsOpen = ref(false)
  // The timing the lyrics had when the editor opened, when they had any: the
  // words are edited as words, and keep it (see lyricsMerge.js).
  const seedTimes = ref([])
  // A draft from an earlier visit was picked up.
  const restored = ref(false)
  // idle | sending | done | failed
  const status = ref('idle')
  const failure = ref(null)

  let isOpen = false
  let openedTrack = null
  let key = ''
  // The draft a fresh start would make: matching it means there is nothing
  // worth keeping, so an editor opened and closed leaves no draft behind.
  let baseline = ''
  let saveTimer = null
  // What the line list was last built from, so words changed on the first
  // step reach the timing step.
  let linesFrom = null

  // ─── The words ───
  const detectedSynced = computed(() => hasStamps(form.value.raw))
  const syncedCount = computed(() =>
    detectedSynced.value ? parseLrc(form.value.raw).filter((l) => l.time != null).length : 0
  )
  const plainCount = computed(() => (detectedSynced.value ? 0 : splitWords(form.value.raw).length))

  const missing = computed(() => ({
    details: !form.value.track.trim() || !form.value.artist.trim(),
    duration: !(form.value.duration > 0),
    words: !form.value.raw.trim(),
  }))
  const canLeaveWords = computed(() => !missing.value.details && !missing.value.duration && !missing.value.words)
  const showDetails = computed(() => detailsOpen.value || missing.value.details)

  // The timing as it stands: the lines' own once there are lines (they may
  // have been worked on since), what the lyrics came with before that.
  function timingSoFar() {
    const lines = editor.lines.value
    return lines.length ? lines.map((l) => ({ text: l.text, time: l.time })) : seedTimes.value
  }

  function linesFromWords() {
    if (detectedSynced.value) return parseLrc(form.value.raw)
    return mergeTimes(splitWords(form.value.raw), timingSoFar())
  }

  function buildLines() {
    if (editor.lines.value.length && linesFrom === form.value.raw) return
    editor.load(linesFromWords())
    linesFrom = form.value.raw
  }

  // How many lines the words would leave untimed, for the button's label.
  // -1 when there is no timing to keep.
  const untimedAfterWords = computed(() => {
    const timed = timingSoFar()
    if (detectedSynced.value || !timed.some((l) => l.time != null)) return -1
    return mergeTimes(splitWords(form.value.raw), timed).filter((l) => l.time == null).length
  })

  // ─── What goes out ───
  const canReview = computed(() => enoughTimed(editor.lines.value))
  const needTimed = computed(() => minTimed(editor.lines.value.length))
  const syncedOutput = computed(() => (canReview.value ? toSynced(editor.lines.value) : ''))
  const plainOutput = computed(() => toPlain(editor.lines.value))
  // What people will see, as they will see it.
  const previewLines = computed(() => {
    const lines = editor.lines.value
    if (syncedOutput.value) {
      return lines
        .filter((l) => l.time != null)
        .slice()
        .sort((a, b) => a.time - b.time)
        .map((l) => ({ time: l.time, text: outText(l.text) }))
    }
    return lines.map((l) => ({ time: null, text: outText(l.text) }))
  })
  // Lines out of order would be published in the wrong order.
  const blockedByOrder = computed(() => !!syncedOutput.value && editor.issues.value.length > 0)
  const canSubmit = computed(
    () =>
      status.value !== 'sending' &&
      status.value !== 'done' &&
      !blockedByOrder.value &&
      !!(plainOutput.value || syncedOutput.value)
  )

  // ─── Steps ───
  function goPhase(p) {
    if (p === SYNC || (p === REVIEW && phase.value === WORDS)) buildLines()
    phase.value = p
  }

  /** Where "Next" leads from the words: review when nothing is left to time. */
  function nextFromWords() {
    if (!canLeaveWords.value) return
    if (detectedSynced.value) return goPhase(REVIEW)
    buildLines()
    const lines = editor.lines.value
    goPhase(lines.length && lines.every((l) => l.time != null) ? REVIEW : SYNC)
  }

  /** From the review: back to the timing, on the first line out of order. */
  function fixOrder() {
    goPhase(SYNC)
    const at = nextIssue(editor.issues.value, -1)
    if (at >= 0) editor.setActive(at)
  }

  /** The step before this one: the review of words alone goes to the words. */
  function back() {
    if (phase.value === REVIEW) goPhase(syncedOutput.value ? SYNC : WORDS)
    else if (phase.value === SYNC) goPhase(WORDS)
  }

  // ─── Opening, drafts ───
  function seedFrom(track) {
    // The words as words. Lyrics already in time used to arrive as the file
    // format, a [00:10.53] in front of every line, to be edited around; the
    // timing is kept aside instead and goes back on every line left as it was.
    let raw = ''
    let seed = []
    const synced = player.lyricsLines.value || []
    if (synced.length) {
      raw = wordsOf(synced)
      seed = synced
        .filter((l) => l.time != null)
        .map((l) => ({ text: String(l.text || '').trim() ? l.text : BREAK, time: l.time }))
    } else if (player.lyricsPlain.value) {
      raw = player.lyricsPlain.value
    }
    return {
      form: {
        track: track.title || '',
        artist: track.artist || '',
        album: track.album || '',
        duration: track.duration || player.duration.value || 0,
        raw,
      },
      seed,
    }
  }

  function serialise() {
    return JSON.stringify({
      form: form.value,
      lines: editor.lines.value.map((l) => ({ text: l.text, time: l.time })),
      phase: phase.value,
      seed: seedTimes.value,
      from: linesFrom,
    })
  }

  function applyFresh(fresh) {
    form.value = { ...fresh.form }
    seedTimes.value = fresh.seed
    linesFrom = null
    editor.load([])
    phase.value = WORDS
  }

  function applyDraft(draft, fresh) {
    form.value = draft.form
    if (!(form.value.duration > 0)) form.value.duration = fresh.form.duration
    seedTimes.value = draft.seed
    linesFrom = draft.from
    editor.load(draft.lines)
    // A later step with no lines to show cannot be shown.
    phase.value = editor.lines.value.length ? draft.phase : WORDS
  }

  /** Fill the editor for the song that is playing. False when nothing is. */
  function open() {
    isOpen = true
    status.value = 'idle'
    failure.value = null
    detailsOpen.value = false
    restored.value = false
    const track = player.currentTrack.value
    if (!track) return false
    openedTrack = track
    song.value = { title: track.title || '', artist: track.artist || '' }
    cover.value = track.cover || ''
    const fresh = seedFrom(track)
    key = draftKey(fresh.form.track, fresh.form.artist)
    applyFresh(fresh)
    baseline = serialise()
    const draft = loadDraft(key)
    if (draft) {
      applyDraft(draft, fresh)
      restored.value = serialise() !== baseline
    }
    return true
  }

  /** Throw the draft away and begin again from the lyrics as they are. */
  function startOver() {
    if (!openedTrack) return
    clearTimeout(saveTimer)
    clearDraft(key)
    applyFresh(seedFrom(openedTrack))
    baseline = serialise()
    restored.value = false
    detailsOpen.value = false
  }

  function flushDraft() {
    clearTimeout(saveTimer)
    saveTimer = null
    if (!key || status.value === 'done') return
    const now = serialise()
    if (now === baseline) clearDraft(key)
    else saveDraft(key, JSON.parse(now))
  }

  watch([form, editor.lines, phase], () => {
    if (!isOpen || !key || status.value === 'done') return
    clearTimeout(saveTimer)
    saveTimer = setTimeout(flushDraft, SAVE_DELAY)
  }, { deep: true })

  // A stream's length is often not known yet the moment the editor opens,
  // and publishing needs it. It is filled in when the player learns it.
  watch(
    () => player.duration.value,
    (d) => {
      if (!isOpen || !(d > 0) || form.value.duration > 0) return
      if (player.currentTrack.value !== openedTrack) return
      form.value.duration = d
    }
  )

  function close() {
    if (!isOpen) return
    flushDraft()
    isOpen = false
  }

  // ─── Publishing ───
  async function submit() {
    if (!canSubmit.value) return false
    status.value = 'sending'
    failure.value = null
    const payload = {
      track: form.value.track.trim(),
      artist: form.value.artist.trim(),
      album: form.value.album.trim(),
      duration: form.value.duration,
      plain: plainOutput.value,
      synced: syncedOutput.value,
    }
    const result = await sendLyrics(payload)
    if (!result.ok) {
      status.value = 'failed'
      failure.value = result
      return false
    }
    status.value = 'done'
    clearTimeout(saveTimer)
    clearDraft(key)
    announcePublished(payload.track, payload.artist)
    return true
  }

  return {
    editor,
    form,
    phase,
    song,
    cover,
    detailsOpen,
    showDetails,
    seedTimes,
    restored,
    status,
    failure,
    detectedSynced,
    syncedCount,
    plainCount,
    missing,
    canLeaveWords,
    untimedAfterWords,
    canReview,
    needTimed,
    syncedOutput,
    plainOutput,
    previewLines,
    blockedByOrder,
    canSubmit,
    goPhase,
    nextFromWords,
    fixOrder,
    back,
    open,
    close,
    startOver,
    flushDraft,
    submit,
  }
}
