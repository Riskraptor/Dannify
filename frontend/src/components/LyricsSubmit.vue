<template>
  <Teleport to="body">
    <transition name="ls-modal">
      <div
        v-if="open"
        class="ls-backdrop"
        @click.self="confirmClose"
      >
        <div class="ls-shell">
          <!-- Header -->
          <header class="ls-head">
            <CoverImage :src="cover" radius="sm" :size="48" class="ls-head-art" />
            <div class="ls-head-titles">
              <p class="ls-eyebrow">{{ t('publish.contributeTo') }}</p>
              <h2 class="ls-title">{{ song.title }}</h2>
              <p class="ls-by">{{ song.artist }}</p>
            </div>
            <button class="ls-x press" @click="confirmClose" :title="t('common.close')">
              <Icon icon="ph:x-bold" class="h-4 w-4" />
            </button>
          </header>

          <!-- Stepper: numbered beads on a rail, the way a wizard should read.
               Each step says what it is for, because "Paste / Sync / Review"
               on its own does not tell a first-time contributor anything. -->
          <ol class="ls-steps" :aria-label="t('publish.contributeTo')">
            <li
              v-for="(label, idx) in stepLabels"
              :key="idx"
              class="ls-step"
              :class="{ active: phase === idx, done: phase > idx }"
              :aria-current="phase === idx ? 'step' : undefined"
            >
              <span class="ls-step-bead">
                <Icon v-if="phase > idx" icon="ph:check-bold" class="h-3 w-3" />
                <template v-else>{{ idx + 1 }}</template>
              </span>
              <span class="ls-step-label">{{ label }}</span>
            </li>
          </ol>
          <p class="ls-step-why">
            <Icon icon="ph:info" class="h-3.5 w-3.5 shrink-0" />
            <span>{{ stepWhy }}</span>
          </p>

          <!-- ─── Phase 1: paste / detect ─── -->
          <section v-if="phase === 0" class="ls-body">
            <p class="ls-intro">
              <Icon icon="ph:sparkle-fill" class="h-4 w-4 shrink-0 text-accent" />
              <span>{{ t('publish.intro') }}</span>
            </p>
            <p class="ls-help">
              {{ t('publish.pasteHelp') }}
            </p>

            <div class="ls-meta">
              <label class="ls-field">
                <span>{{ t('publish.title') }}</span>
                <input v-model="form.track" type="text" />
              </label>
              <label class="ls-field">
                <span>{{ t('publish.artist') }}</span>
                <input v-model="form.artist" type="text" />
              </label>
              <label class="ls-field">
                <span>{{ t('publish.album') }}</span>
                <input
                  v-model="form.album"
                  type="text"
                  :placeholder="t('publish.albumOptional')"
                />
              </label>
              <label class="ls-field">
                <span>{{ t('publish.duration') }}</span>
                <div class="ls-dur">
                  <input
                    :value="formatTime(form.duration)"
                    type="text"
                    readonly
                  />
                  <span class="ls-dur-hint">{{ form.duration.toFixed(1) }}s</span>
                </div>
              </label>
            </div>

            <textarea
              v-model="form.raw"
              class="ls-paste"
              :placeholder="t('publish.pastePlaceholder')"
              spellcheck="false"
            ></textarea>

            <transition name="ls-fade">
              <p v-if="detectedSynced" class="ls-detected synced">
                <Icon icon="ph:check-circle-fill" class="h-4 w-4" />
                {{ t('publish.detectedSynced', { count: detectedSyncedCount }) }}
              </p>
              <p v-else-if="detectedPlain" class="ls-detected">
                <Icon icon="ph:info-fill" class="h-4 w-4" />
                {{ t('publish.detectedPlain', { count: detectedPlainCount }) }}
              </p>
            </transition>

            <div class="ls-actions">
              <button class="ls-btn ghost" @click="confirmClose">
                {{ t('common.cancel') }}
              </button>
              <button
                class="ls-btn primary"
                @click="goPhase(detectedSynced ? 2 : 1)"
                :disabled="!canLeavePhase0"
              >
                {{
                  detectedSynced
                    ? t('publish.next.review')
                    : t('publish.next.sync')
                }}
                <Icon icon="ph:arrow-right-bold" class="h-4 w-4" />
              </button>
            </div>
          </section>

          <!-- ─── Phase 2: Pro sync editor ─── -->
          <section v-else-if="phase === 1" class="ls-body sync" tabindex="-1" ref="syncRoot">
            <!-- Transport rail: scrubbable bar w/ stamps as ticks -->
            <div class="ls-rail">
              <button
                class="ls-rail-play"
                @click="player.toggle()"
                :title="player.isPlaying.value ? t('player.pause') : t('player.play')"
              >
                <Icon
                  :icon="player.isPlaying.value ? 'ph:pause-fill' : 'ph:play-fill'"
                  class="h-5 w-5"
                />
              </button>
              <div
                class="ls-rail-scrub"
                ref="scrubEl"
                @pointerdown="onScrubDown"
              >
                <div
                  class="ls-rail-track"
                  :style="{ '--p': scrubProgress + '%' }"
                />
                <!-- Loop region (when set) -->
                <div
                  v-if="loopVisible"
                  class="ls-rail-loop"
                  :style="loopStyle"
                />
                <!-- Stamp ticks -->
                <span
                  v-for="(ln, i) in stampedTicks"
                  :key="i"
                  class="ls-rail-tick"
                  :class="{ error: ln.error }"
                  :style="{ left: ln.left + '%' }"
                  :title="formatLrcTime(ln.time) + '  ' + ln.text"
                />
                <div class="ls-rail-thumb" :style="{ left: scrubProgress + '%' }" />
              </div>
              <div class="ls-rail-time">
                <span class="now">{{ formatHMS(player.currentTime.value) }}</span>
                <span class="sep">/</span>
                <span class="total">{{ formatHMS(player.duration.value) }}</span>
              </div>
            </div>

            <!-- Transport controls + speed. Grouped and labelled: eleven
                 bare buttons in a row is a puzzle, three named groups is a
                 toolbar you can read at a glance. -->
            <div class="ls-trans">
              <span class="ls-trans-label">{{ t('publish.groupSeek') }}</span>
              <button class="ls-tbtn" @click="player.seek(player.currentTime.value - 10)" :title="t('publish.back10')">
                <Icon icon="ph:rewind-fill" class="h-4 w-4" />
                <span>10s</span>
              </button>
              <button class="ls-tbtn" @click="player.seek(player.currentTime.value - 2)" :title="t('publish.back2')">
                <Icon icon="ph:skip-back-fill" class="h-4 w-4" />
                <span>2s</span>
              </button>
              <button class="ls-tbtn" @click="player.seek(player.currentTime.value + 2)" :title="t('publish.fwd2')">
                <Icon icon="ph:skip-forward-fill" class="h-4 w-4" />
                <span>2s</span>
              </button>
              <button class="ls-tbtn" @click="player.seek(player.currentTime.value + 10)" :title="t('publish.fwd10')">
                <Icon icon="ph:fast-forward-fill" class="h-4 w-4" />
                <span>10s</span>
              </button>
              <div class="ls-trans-sep" />
              <span class="ls-trans-label">{{ t('publish.groupSpeed') }}</span>
              <div class="ls-speed" :title="t('publish.playbackSpeed')">
                <button
                  v-for="r in [0.5, 0.75, 1.0, 1.25, 1.5]"
                  :key="r"
                  class="ls-speed-btn"
                  :class="{ on: Math.abs(player.playbackRate.value - r) < 0.01 }"
                  @click="player.setPlaybackRate(r)"
                >{{ r }}×</button>
              </div>
              <div class="ls-trans-sep" />
              <span class="ls-trans-label">{{ t('publish.groupEdit') }}</span>
              <button
                class="ls-tbtn"
                :disabled="!undoStack.length"
                @click="undo"
                :title="t('publish.undoHint')"
              >
                <Icon icon="ph:arrow-counter-clockwise-bold" class="h-4 w-4" />
              </button>
              <button
                class="ls-tbtn"
                :disabled="!redoStack.length"
                @click="redo"
                :title="t('publish.redoHint')"
              >
                <Icon icon="ph:arrow-clockwise-bold" class="h-4 w-4" />
              </button>
              <button
                class="ls-tbtn danger"
                @click="resetStamps"
                :title="t('publish.reset')"
              >
                <Icon icon="ph:trash-bold" class="h-4 w-4" />
              </button>
            </div>

            <!-- Sticky "now syncing" hero card -->
            <div class="ls-hero">
              <div class="ls-hero-meta">
                <span class="ls-hero-num">{{ activeLineDisplay }}</span>
                <span class="ls-hero-time">
                  <Icon icon="ph:timer-bold" class="h-3.5 w-3.5" />
                  {{ activeLineStampDisplay }}
                </span>
              </div>
              <p class="ls-hero-text">{{ activeLineText || t('publish.emptyLine') }}</p>
              <p class="ls-hero-hint">
                <kbd>Space</kbd> {{ t('publish.stampNow') }} ·
                <kbd>L</kbd> {{ t('publish.loopLine') }} ·
                <kbd>Enter</kbd> {{ t('publish.insertBelow') }}
              </p>
              <p class="ls-hero-tip">
                <Icon icon="ph:plus-circle-bold" class="h-3.5 w-3.5" />
                {{ t('publish.addLineTip') }}
              </p>
            </div>

            <!-- Lines list (with inline ＋ buttons between rows) -->
            <div class="ls-lines2" ref="linesEl">
              <!-- Top add button -->
              <button class="ls-insert top" @click="addLineAt(0)" :title="t('publish.addLineHere')">
                <Icon icon="ph:plus-bold" class="h-3.5 w-3.5" />
                <span>{{ t('publish.addLineHere') }}</span>
              </button>

              <template v-for="(line, idx) in lines" :key="line._id">
                <div
                  :ref="(el) => setLineRef(el, idx)"
                  class="ls-row"
                  :class="{
                    active: idx === activeLine,
                    stamped: line.time != null,
                    error: !!stampQuality[idx]?.error,
                    warn: !!stampQuality[idx]?.warn,
                  }"
                  @click="setActive(idx)"
                >
                  <span class="ls-row-num">{{ idx + 1 }}</span>
                  <button
                    class="ls-row-stamp"
                    :class="{
                      filled: line.time != null,
                      error: !!stampQuality[idx]?.error,
                      warn: !!stampQuality[idx]?.warn,
                    }"
                    @click.stop="stampLine(idx)"
                    :title="t('publish.stampLine')"
                  >
                    <Icon
                      :icon="line.time != null ? 'ph:timer-fill' : 'ph:timer-bold'"
                      class="h-3.5 w-3.5"
                    />
                    {{ line.time != null ? formatLrcTime(line.time) : blankStamp }}
                  </button>
                  <input
                    v-if="editingIndex === idx"
                    :ref="(el) => setEditRef(el, idx)"
                    v-model="line.text"
                    class="ls-row-edit"
                    @keydown.enter.prevent="editingIndex = -1"
                    @keydown.escape.prevent="editingIndex = -1"
                    @blur="editingIndex = -1"
                  />
                  <span v-else class="ls-row-text">{{ line.text || '♪' }}</span>
                  <div class="ls-row-acts">
                    <button
                      class="ls-row-act"
                      :title="t('publish.playFromHere')"
                      :disabled="line.time == null"
                      @click.stop="playFromLine(idx)"
                    >
                      <Icon icon="ph:play-fill" class="h-3.5 w-3.5" />
                    </button>
                    <button
                      class="ls-row-act"
                      :class="{ on: loopLineIdx === idx }"
                      :title="t('publish.loopLine')"
                      @click.stop="toggleLoopLine(idx)"
                    >
                      <Icon icon="ph:repeat-bold" class="h-3.5 w-3.5" />
                    </button>
                    <button class="ls-row-act" :title="t('publish.editText')" @click.stop="editLine(idx)">
                      <Icon icon="ph:pencil-simple-bold" class="h-3.5 w-3.5" />
                    </button>
                    <button
                      class="ls-row-act"
                      :title="t('publish.addLineBelow')"
                      @click.stop="addLineAt(idx + 1)"
                    >
                      <Icon icon="ph:plus-bold" class="h-3.5 w-3.5" />
                    </button>
                    <button class="ls-row-act danger" :title="t('publish.deleteLine')" @click.stop="deleteLine(idx)">
                      <Icon icon="ph:x-bold" class="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                <!-- Inline add-between -->
                <button
                  class="ls-insert"
                  @click="addLineAt(idx + 1)"
                  :title="t('publish.addLineHere')"
                >
                  <Icon icon="ph:plus-bold" class="h-3 w-3" />
                </button>
              </template>
            </div>

            <!-- How far along, then what is wrong. "Partially timed" never
                 answered the question the user is actually asking. -->
            <div class="ls-progress">
              <div class="ls-progress-head">
                <span class="ls-progress-count">
                  {{ t('publish.timedOf', { done: stampedCount, total: lines.length }) }}
                </span>
                <span class="ls-progress-state" :class="qualityClass">{{ qualityText }}</span>
              </div>
              <div class="ls-progress-track">
                <div
                  class="ls-progress-fill"
                  :class="qualityClass"
                  :style="{ width: stampedPercent + '%' }"
                />
              </div>
            </div>

            <!-- Sync quality + actions -->
            <div class="ls-quality">
              <button
                v-if="qualityErrors.length"
                class="ls-quality-fix"
                @click="jumpToNextError"
              >
                <Icon icon="ph:warning-fill" class="h-3.5 w-3.5" />
                {{ t('publish.fixIssues') }}
              </button>
            </div>

            <div class="ls-actions">
              <button class="ls-btn ghost" @click="goPhase(0)">
                <Icon icon="ph:arrow-left-bold" class="h-4 w-4" />
                {{ t('publish.back') }}
              </button>
              <button
                class="ls-btn primary"
                @click="goPhase(2)"
                :disabled="!canReview"
              >
                {{ t('publish.next.review') }}
                <Icon icon="ph:arrow-right-bold" class="h-4 w-4" />
              </button>
            </div>
          </section>

          <!-- ─── Phase 3: review + submit ─── -->
          <section v-else-if="phase === 2" class="ls-body review">
            <div class="ls-review-stats">
              <div class="ls-stat">
                <span class="ls-stat-num">{{ stampedCount }}</span>
                <span class="ls-stat-label">{{ t('publish.linesStamped') }}</span>
              </div>
              <div class="ls-stat">
                <span class="ls-stat-num">{{ lines.length }}</span>
                <span class="ls-stat-label">{{ t('publish.linesTotal') }}</span>
              </div>
              <div class="ls-stat">
                <span class="ls-stat-num">{{ form.duration.toFixed(0) }}s</span>
                <span class="ls-stat-label">{{ t('publish.duration') }}</span>
              </div>
            </div>

            <div class="ls-preview">
              <pre>{{ syncedOutput || plainOutput }}</pre>
            </div>

            <transition name="ls-fade">
              <p v-if="submitState.message" :class="['ls-msg', submitState.kind]">
                <Icon
                  :icon="submitState.kind === 'error' ? 'ph:warning-fill' : 'ph:check-circle-fill'"
                  class="h-4 w-4"
                />
                {{ submitState.message }}
              </p>
            </transition>

            <transition name="ls-fade">
              <div v-if="submitting" class="ls-submitting">
                <span class="spinner h-5 w-5 shrink-0 text-accent"></span>
                <div>
                  <p class="ls-submit-step">{{ submitState.step }}</p>
                  <p class="ls-submit-sub">{{ t('publish.powSlow') }}</p>
                </div>
              </div>
            </transition>

            <div class="ls-actions">
              <button
                class="ls-btn ghost"
                @click="goPhase(syncedOutput ? 1 : 0)"
                :disabled="submitting || submitState.kind === 'ok'"
              >
                <Icon icon="ph:arrow-left-bold" class="h-4 w-4" />
                {{ t('publish.back') }}
              </button>
              <button
                v-if="submitState.kind === 'ok'"
                class="ls-btn primary"
                @click="finishAndClose"
              >
                <Icon icon="ph:check-bold" class="h-4 w-4" />
                {{ t('common.close') }}
              </button>
              <button
                v-else
                class="ls-btn primary"
                @click="doSubmit"
                :disabled="submitting"
              >
                <Icon icon="ph:paper-plane-tilt-fill" class="h-4 w-4" />
                {{ t('publish.submit') }}
              </button>
            </div>
          </section>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { Icon } from '@iconify/vue'
import { usePlayer, formatTime } from '/src/model/player'
import API from '/src/model/api'
import CoverImage from '/src/components/ui/CoverImage.vue'
import { useI18n } from '/src/i18n'

const props = defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])

const { t } = useI18n()
const player = usePlayer()

// Header data: kept reactive to the player so the modal always
// shows the song that was playing when it opened.
const song = computed(() => {
  const cur = player.currentTrack.value
  return {
    title: cur?.title || form.value.track || '',
    artist: cur?.artist || form.value.artist || '',
  }
})
const cover = computed(() => player.currentTrack.value?.cover || '')

const phase = ref(0)
const form = ref({
  track: '',
  artist: '',
  album: '',
  duration: 0,
  raw: '',
})

// ─── Line model ───
// Each line: { _id, text, time }  (time is seconds or null)
// ``_id`` is a monotonically-incrementing local key so Vue's keyed v-for
// stays stable across inserts/deletes (text/time can change freely).
let _nextId = 1
function makeLine(text = '', time = null) {
  return { _id: _nextId++, text: String(text || ''), time: time }
}
const lines = ref([])
const activeLine = ref(0)
const editingIndex = ref(-1)
const linesEl = ref(null)
const syncRoot = ref(null)
const lineRefs = ref({})
const editRefs = ref({})

// ─── Undo/redo ───
// State op log. Each entry is a SNAPSHOT of {lines, activeLine}. Snapshots
// are cheap (lines are small POJOs) and let us implement undo/redo
// uniformly across text edits / stamps / inserts / deletes / clears.
const undoStack = ref([])
const redoStack = ref([])
const UNDO_CAP = 200

function cloneLines() {
  return lines.value.map((l) => ({ _id: l._id, text: l.text, time: l.time }))
}
function pushUndo() {
  undoStack.value.push({
    lines: cloneLines(),
    activeLine: activeLine.value,
  })
  if (undoStack.value.length > UNDO_CAP) undoStack.value.shift()
  // Any new mutation invalidates the redo stack.
  redoStack.value = []
}
function undo() {
  if (!undoStack.value.length) return
  redoStack.value.push({
    lines: cloneLines(),
    activeLine: activeLine.value,
  })
  const snap = undoStack.value.pop()
  lines.value = snap.lines
  activeLine.value = snap.activeLine
}
function redo() {
  if (!redoStack.value.length) return
  undoStack.value.push({
    lines: cloneLines(),
    activeLine: activeLine.value,
  })
  const snap = redoStack.value.pop()
  lines.value = snap.lines
  activeLine.value = snap.activeLine
}

const submitting = ref(false)
const submitState = ref({ kind: null, message: '', step: '' })

const stepLabels = computed(() => [
  t('publish.step.paste'),
  t('publish.step.sync'),
  t('publish.step.review'),
])

// What the current step is actually for. Shown under the rail so it is read
// once, where the user already is, rather than hidden behind a tooltip.
const stepWhy = computed(
  () =>
    [
      t('publish.stepWhy.paste'),
      t('publish.stepWhy.sync'),
      t('publish.stepWhy.review'),
    ][phase.value] || ''
)

const DRAFT_KEY = computed(() => {
  const k = `${form.value.track}|${form.value.artist}`.toLowerCase()
  return `dannify-lyric-draft|${k}`
})

// ─── LRC parsing / detection ───
const LRC_RE = /\[(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\]/
const LRC_RE_G = /\[(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\]/g

function parseLrc(text) {
  const out = []
  for (const raw of (text || '').split('\n')) {
    const stamps = [...raw.matchAll(LRC_RE_G)]
    const body = raw.replace(LRC_RE_G, '').trim()
    if (!stamps.length && !body) continue
    if (!stamps.length) {
      out.push({ time: null, text: body })
      continue
    }
    for (const m of stamps) {
      out.push({
        time: parseInt(m[1], 10) * 60 + parseFloat(m[2]),
        text: body,
      })
    }
  }
  return out
}

const detectedSynced = computed(
  () => LRC_RE.test(form.value.raw) && form.value.raw.trim().length > 0
)
const detectedSyncedCount = computed(() =>
  detectedSynced.value
    ? parseLrc(form.value.raw).filter((l) => l.time != null).length
    : 0
)
const detectedPlain = computed(
  () => !detectedSynced.value && form.value.raw.trim().length > 0
)
const detectedPlainCount = computed(() =>
  detectedPlain.value
    ? form.value.raw.split('\n').filter((l) => l.trim()).length
    : 0
)
const canLeavePhase0 = computed(
  () =>
    !!form.value.track.trim() &&
    !!form.value.artist.trim() &&
    form.value.duration > 0 &&
    form.value.raw.trim().length > 0
)

// ─── Editor: refs ───
function setLineRef(el, idx) {
  if (el) lineRefs.value[idx] = el
  else delete lineRefs.value[idx]
}
function setEditRef(el, idx) {
  if (el) {
    editRefs.value[idx] = el
    nextTick(() => el.focus && el.focus())
  } else delete editRefs.value[idx]
}

// ─── Editor: stamping ───
function stampLine(idx, { advance = true } = {}) {
  if (idx < 0 || idx >= lines.value.length) return
  markManual()
  pushUndo()
  lines.value[idx].time = Number(player.currentTime.value.toFixed(3))
  if (advance && idx < lines.value.length - 1) {
    activeLine.value = idx + 1
    scrollActiveIntoView()
  }
}

function clearStamp(idx) {
  if (idx < 0 || idx >= lines.value.length) return
  if (lines.value[idx].time == null) return
  pushUndo()
  lines.value[idx].time = null
}

function resetStamps() {
  if (!lines.value.some((l) => l.time != null)) return
  pushUndo()
  for (const l of lines.value) l.time = null
  player.clipUnloop()
  loopLineIdx.value = -1
}

// ─── Editor: insert / delete / edit ───
function addLineAt(idx) {
  pushUndo()
  const ln = makeLine('', null)
  lines.value.splice(idx, 0, ln)
  activeLine.value = idx
  editingIndex.value = idx
}

function deleteLine(idx) {
  if (idx < 0 || idx >= lines.value.length) return
  pushUndo()
  lines.value.splice(idx, 1)
  if (lines.value.length === 0) {
    activeLine.value = 0
  } else if (activeLine.value >= lines.value.length) {
    activeLine.value = lines.value.length - 1
  }
}

function editLine(idx) {
  activeLine.value = idx
  editingIndex.value = idx
}

function setActive(idx) {
  markManual()
  activeLine.value = idx
  // Clicking outside the edit input commits it.
  if (editingIndex.value !== idx) editingIndex.value = -1
}

function scrollActiveIntoView() {
  nextTick(() => {
    const el = lineRefs.value[activeLine.value]
    if (el && el.scrollIntoView) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  })
}

// ─── Editor: play / loop ───
function playFromLine(idx) {
  const ln = lines.value[idx]
  if (!ln || ln.time == null) return
  player.clipUnloop()
  loopLineIdx.value = -1
  player.seek(ln.time)
  if (!player.isPlaying.value) player.play()
}

const loopLineIdx = ref(-1)

// ─── Auto-follow the playhead ───
// As the song plays, predict which line is "current" based on the
// stamped timestamps + linear interpolation for unstamped neighbours,
// and move ``activeLine`` there so the user just hits Space at the
// right moment. A short "manual override" window after every user
// action lets the user click around / nudge without the auto-follow
// fighting them.
let lastManualAt = 0  // performance.now() of the most recent user action
function markManual() {
  lastManualAt = performance.now()
}
function predictedLineForTime(t) {
  if (!lines.value.length) return -1
  // Find the line whose stamp is the latest <= t (small look-ahead so
  // the highlight reaches the line ~250ms before its stamp).
  let best = -1
  let bestTime = -Infinity
  for (let i = 0; i < lines.value.length; i++) {
    const lt = lines.value[i].time
    if (lt != null && lt <= t + 0.25 && lt > bestTime) {
      bestTime = lt
      best = i
    }
  }
  // If we have stamps, the line right AFTER the latest one is what the
  // user is "about to sing": that's the one to highlight for Space.
  if (best >= 0 && best < lines.value.length - 1) return best + 1
  return best
}
watch(
  [() => player.currentTime.value, () => player.isPlaying.value],
  ([t, playing]) => {
    if (phase.value !== 1) return
    if (!playing) return
    if (editingIndex.value !== -1) return
    // Honour a recent manual action: the user just clicked somewhere
    // or stamped; don't yank them away for ~800 ms.
    if (performance.now() - lastManualAt < 800) return
    const target = predictedLineForTime(t)
    if (target < 0) return
    if (target === activeLine.value) return
    activeLine.value = target
    scrollActiveIntoView()
  }
)
function toggleLoopLine(idx) {
  const ln = lines.value[idx]
  if (!ln) return
  if (loopLineIdx.value === idx) {
    player.clipUnloop()
    loopLineIdx.value = -1
    return
  }
  // Use the stamped time when present, otherwise predict from neighbors.
  let t = ln.time
  if (t == null) {
    // Interpolate from surrounding stamps if possible
    const prev = [...lines.value.slice(0, idx)].reverse().find((l) => l.time != null)
    const next = lines.value.slice(idx + 1).find((l) => l.time != null)
    if (prev && next) t = (prev.time + next.time) / 2
    else if (prev) t = prev.time + 1.5
    else if (next) t = Math.max(0, next.time - 1.5)
    else t = player.currentTime.value
  }
  const start = Math.max(0, t - 1.5)
  const end = Math.min(player.duration.value || t + 2, t + 2)
  loopLineIdx.value = idx
  activeLine.value = idx
  player.clipLoop(start, end)
}

// ─── Editor: nudge ───
function nudgeActive(delta) {
  const idx = activeLine.value
  const ln = lines.value[idx]
  if (!ln || ln.time == null) return
  pushUndo()
  ln.time = Math.max(0, Number((ln.time + delta).toFixed(3)))
}

// ─── Editor: keyboard ───
function onKey(e) {
  // Only handle keys when we're in the sync phase.
  if (phase.value !== 1) return
  // Don't hijack typing in the inline text editor.
  if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return
  // OS shortcuts (copy/paste/cut/select-all/undo/redo) always win.
  // We handle Ctrl+Z/Y ourselves below for the editor's undo stack, but
  // every OTHER modifier combo passes straight through.
  if ((e.ctrlKey || e.metaKey) && e.code !== 'KeyZ' && e.code !== 'KeyY') return
  if (e.altKey) return
  if (e.code === 'Space') {
    e.preventDefault()
    stampLine(activeLine.value, { advance: !e.shiftKey })
  } else if (e.code === 'Enter') {
    e.preventDefault()
    addLineAt(activeLine.value + 1)
  } else if (e.code === 'ArrowDown' || e.code === 'KeyJ') {
    e.preventDefault()
    if (activeLine.value < lines.value.length - 1) {
      activeLine.value++
      scrollActiveIntoView()
    }
  } else if (e.code === 'ArrowUp' || e.code === 'KeyK') {
    e.preventDefault()
    if (activeLine.value > 0) {
      activeLine.value--
      scrollActiveIntoView()
    }
  } else if (e.code === 'KeyZ' && !e.ctrlKey && !e.metaKey) {
    e.preventDefault()
    // Quick "clear last stamp": searches back for the most recent stamp
    for (let i = lines.value.length - 1; i >= 0; i--) {
      if (lines.value[i].time != null) {
        clearStamp(i)
        return
      }
    }
  } else if ((e.code === 'KeyZ' || e.code === 'KeyY') && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    if (e.shiftKey || e.code === 'KeyY') redo()
    else undo()
  } else if (e.code === 'ArrowLeft') {
    e.preventDefault()
    nudgeActive(-0.1)
  } else if (e.code === 'ArrowRight') {
    e.preventDefault()
    nudgeActive(0.1)
  } else if (e.code === 'KeyL') {
    e.preventDefault()
    toggleLoopLine(activeLine.value)
  } else if (e.code === 'Comma') {
    e.preventDefault()
    player.setPlaybackRate(player.playbackRate.value - 0.25)
  } else if (e.code === 'Period') {
    e.preventDefault()
    player.setPlaybackRate(player.playbackRate.value + 0.25)
  } else if (e.code === 'Delete' || e.code === 'Backspace') {
    if (e.shiftKey) {
      e.preventDefault()
      deleteLine(activeLine.value)
    }
  }
}

// ─── Quality / validation ───
// Each line gets {error, warn} based on monotonicity + proximity:
//   error -- the timestamp is BEFORE the previous stamped line (definitely wrong)
//   warn  -- the timestamp is within 0.2s of the previous (too close to read)
const stampQuality = computed(() => {
  const out = {}
  let prevTime = -Infinity
  for (let i = 0; i < lines.value.length; i++) {
    const t = lines.value[i].time
    if (t == null) continue
    if (t < prevTime) out[i] = { error: true }
    else if (t - prevTime < 0.2) out[i] = { warn: true }
    prevTime = t
  }
  return out
})
const qualityErrors = computed(() =>
  Object.entries(stampQuality.value)
    .filter(([, q]) => q.error)
    .map(([i]) => Number(i))
)
const stampedCount = computed(
  () => lines.value.filter((l) => l.time != null).length
)
const stampedPercent = computed(() =>
  lines.value.length
    ? Math.round((stampedCount.value / lines.value.length) * 100)
    : 0
)
const canReview = computed(
  () => stampedCount.value >= Math.max(2, Math.ceil(lines.value.length * 0.5))
)
const qualityClass = computed(() => {
  if (qualityErrors.value.length) return 'err'
  if (stampedCount.value === 0) return 'idle'
  if (stampedCount.value < lines.value.length) return 'partial'
  return 'ok'
})
const qualityIcon = computed(() => {
  if (qualityErrors.value.length) return 'ph:warning-fill'
  if (stampedCount.value === lines.value.length && lines.value.length) return 'ph:check-circle-fill'
  return 'ph:gauge-bold'
})
const qualityText = computed(() => {
  const total = lines.value.length
  const stamped = stampedCount.value
  const errs = qualityErrors.value.length
  if (errs) return t('publish.qualityErrors', { stamped, total, errs })
  if (stamped === 0) return t('publish.qualityIdle')
  if (stamped < total) return t('publish.qualityPartial', { stamped, total })
  return t('publish.qualityFull', { total })
})
function jumpToNextError() {
  if (!qualityErrors.value.length) return
  const cur = activeLine.value
  const next = qualityErrors.value.find((i) => i > cur) ?? qualityErrors.value[0]
  setActive(next)
  scrollActiveIntoView()
}

// ─── Scrub bar ───
const scrubEl = ref(null)
const scrubProgress = computed(() => {
  const d = player.duration.value || 0
  if (!d) return 0
  return Math.min(100, Math.max(0, (player.currentTime.value / d) * 100))
})
function onScrubDown(e) {
  if (!scrubEl.value) return
  scrubAt(e.clientX)
  const move = (ev) => scrubAt(ev.clientX)
  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}
function scrubAt(clientX) {
  const rect = scrubEl.value.getBoundingClientRect()
  const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
  const d = player.duration.value || 0
  if (d) player.seek(d * ratio)
}

// ─── Loop region visuals ───
const loopVisible = computed(
  () =>
    player.clipLoopStart.value != null &&
    player.clipLoopEnd.value != null &&
    (player.duration.value || 0) > 0
)
const loopStyle = computed(() => {
  const d = player.duration.value || 1
  const a = ((player.clipLoopStart.value || 0) / d) * 100
  const b = ((player.clipLoopEnd.value || 0) / d) * 100
  return { left: a + '%', width: Math.max(1, b - a) + '%' }
})

// ─── Stamp ticks on the scrub bar ───
const stampedTicks = computed(() => {
  const d = player.duration.value || 1
  return lines.value
    .map((l, i) => ({ ...l, idx: i }))
    .filter((l) => l.time != null)
    .map((l) => ({
      time: l.time,
      text: l.text,
      left: (l.time / d) * 100,
      error: !!stampQuality.value[l.idx]?.error,
    }))
})

// ─── Hero card data ───
const activeLineDisplay = computed(() => {
  if (!lines.value.length) return ''
  return `${activeLine.value + 1} / ${lines.value.length}`
})
const activeLineText = computed(
  () => lines.value[activeLine.value]?.text || ''
)
const activeLineStampDisplay = computed(() => {
  const t = lines.value[activeLine.value]?.time
  return t == null ? blankStamp : formatLrcTime(t)
})

// What an unstamped line shows: clearly "no value", never a plausible 0:00.
const blankStamp = '--:--.--'

// ─── Output formatters ───
function formatLrcTime(t) {
  if (t == null) return ''
  const m = Math.floor(t / 60)
  const s = (t % 60).toFixed(2).padStart(5, '0')
  return `${m.toString().padStart(2, '0')}:${s}`
}
function formatHMS(t) {
  if (!isFinite(t) || t < 0) t = 0
  const total = Math.floor(t)
  const m = Math.floor(total / 60)
  const s = total % 60
  const ms = Math.floor((t - Math.floor(t)) * 1000)
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`
}

const syncedOutput = computed(() => {
  if (lines.value.length === 0) return ''
  if (stampedCount.value < Math.max(2, Math.ceil(lines.value.length * 0.5))) {
    return ''
  }
  const sorted = lines.value
    .filter((l) => l.time != null)
    .slice()
    .sort((a, b) => a.time - b.time)
  return sorted.map((l) => `[${formatLrcTime(l.time)}]${l.text}`).join('\n')
})

const plainOutput = computed(() =>
  lines.value
    .map((l) => l.text)
    .filter((t, i, arr) => t || arr[i - 1])
    .join('\n')
    .trim()
)

// ─── Phase transitions ───
function goPhase(p) {
  if (p === 1) {
    // entering sync editor: initialise lines from the pasted text
    if (lines.value.length === 0) {
      const parsed = parseLrc(form.value.raw)
      if (detectedSynced.value) {
        lines.value = parsed.map((p) => makeLine(p.text, p.time))
      } else {
        lines.value = form.value.raw
          .split('\n')
          .map((s) => s.trim())
          .filter((s) => s.length > 0)
          .map((s) => makeLine(s, null))
      }
      activeLine.value = 0
    }
    nextTick(() => syncRoot.value && syncRoot.value.focus())
  } else if (p === 2) {
    if (lines.value.length === 0 && detectedSynced.value) {
      const parsed = parseLrc(form.value.raw)
      lines.value = parsed.map((p) => makeLine(p.text, p.time))
    }
    // Stop any loop when leaving the editor.
    player.clipUnloop()
    loopLineIdx.value = -1
  } else if (p === 0) {
    player.clipUnloop()
    loopLineIdx.value = -1
  }
  phase.value = p
}

// ─── Submission ───
async function doSubmit() {
  submitting.value = true
  submitState.value = {
    kind: null, message: '',
    step: t('publish.solving'),
  }
  try {
    const payload = {
      track: form.value.track.trim(),
      artist: form.value.artist.trim(),
      album: form.value.album.trim(),
      duration: form.value.duration,
      plain: plainOutput.value,
      synced: syncedOutput.value,
    }
    const res = await API.publishLyrics(payload)
    const data = res?.data || {}
    if (data.published) {
      submitState.value = {
        kind: 'ok',
        message: t('publish.success'),
        step: '',
      }
      try {
        localStorage.removeItem(DRAFT_KEY.value)
      } catch {}
      // Tell the player to pull the new lyrics in if this is the open song.
      window.dispatchEvent(
        new CustomEvent('dannify:lyrics-published', {
          detail: { track: payload.track, artist: payload.artist },
        })
      )
    } else {
      submitState.value = {
        kind: 'error',
        message: data.error || t('publish.failed'),
        step: '',
      }
    }
  } catch (err) {
    submitState.value = {
      kind: 'error',
      message: (err && err.message) || t('publish.failed'),
      step: '',
    }
  } finally {
    submitting.value = false
  }
}

function finishAndClose() {
  player.clipUnloop()
  loopLineIdx.value = -1
  player.setPlaybackRate(1)
  player.noAutoAdvance.value = false
  emit('close')
}

function confirmClose() {
  if (submitting.value) return
  player.clipUnloop()
  loopLineIdx.value = -1
  player.noAutoAdvance.value = false
  emit('close')
}

// ─── Draft persistence (debounced 500 ms) ───
let draftTimer = null
watch(
  [() => form.value, () => lines.value, () => phase.value],
  () => {
    if (!form.value.track) return
    clearTimeout(draftTimer)
    draftTimer = setTimeout(() => {
      try {
        const snapshot = {
          form: form.value,
          // Strip the _id (Vue-only) field: and don't persist undo/redo.
          lines: lines.value.map((l) => ({ text: l.text, time: l.time })),
          phase: phase.value,
        }
        localStorage.setItem(DRAFT_KEY.value, JSON.stringify(snapshot))
      } catch {}
    }, 500)
  },
  { deep: true }
)

// ─── Open/close hydration ───
watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) {
      player.clipUnloop()
      loopLineIdx.value = -1
      player.noAutoAdvance.value = false
      unbindWindowKeys()
      return
    }
    // While the modal is open, the song "ended" event should NOT
    // advance to the next track: that would yank the user's editor
    // context mid-sync. The modal restores normal behavior on close.
    player.noAutoAdvance.value = true
    bindWindowKeys()
    const cur = player.currentTrack.value
    if (!cur) return
    // Seed the textarea with whatever the player has now.
    let seeded = ''
    if (player.lyricsLines.value?.length) {
      seeded = player.lyricsLines.value
        .map((l) => `[${formatLrcTime(l.time)}]${l.text || ''}`)
        .join('\n')
    } else if (player.lyricsPlain.value) {
      seeded = player.lyricsPlain.value
    }
    const initial = {
      track: cur.title || '',
      artist: cur.artist || '',
      album: cur.album || '',
      duration: cur.duration || player.duration.value || 0,
      raw: seeded,
    }
    try {
      const key = `dannify-lyric-draft|${initial.track.toLowerCase()}|${initial.artist.toLowerCase()}`
      const saved = localStorage.getItem(key)
      if (saved) {
        const data = JSON.parse(saved)
        if (data?.form?.track === initial.track) {
          form.value = data.form
          // Re-hydrate _id on each line for stable v-for keys.
          lines.value = (data.lines || []).map((l) => makeLine(l.text, l.time))
          phase.value = Math.min(data.phase ?? 0, 2)
          activeLine.value = 0
          undoStack.value = []
          redoStack.value = []
          submitState.value = { kind: null, message: '', step: '' }
          return
        }
      }
    } catch {}
    form.value = initial
    lines.value = []
    phase.value = 0
    activeLine.value = 0
    editingIndex.value = -1
    undoStack.value = []
    redoStack.value = []
    submitState.value = { kind: null, message: '', step: '' }
  }
)

onUnmounted(() => {
  player.clipUnloop()
  player.setPlaybackRate(1)
  player.noAutoAdvance.value = false
  if (typeof window !== 'undefined') {
    window.removeEventListener('keydown', onKey, true)
  }
})

// Window-level keydown so the editor's shortcuts work even when focus
// isn't inside the section (e.g. the user clicked an action button or
// a scroll-bar). The capturing phase ensures we beat anything else
// that might also be listening on Space.
function bindWindowKeys() {
  if (typeof window === 'undefined') return
  window.removeEventListener('keydown', onKey, true)
  window.addEventListener('keydown', onKey, true)
}
function unbindWindowKeys() {
  if (typeof window === 'undefined') return
  window.removeEventListener('keydown', onKey, true)
}
</script>

<style scoped>
/* The editor borrows the app's own tokens so it reads as part of Dannify
   rather than a web form that happens to be on top of it. */
.ls-backdrop {
  position: fixed;
  inset: 0;
  background: rgb(0 0 0 / 0.55);
  backdrop-filter: blur(10px) saturate(0.9);
  display: grid;
  place-items: center;
  z-index: 1200;
  padding: 1rem;
}
[data-theme='dannify-light'] .ls-backdrop {
  background: rgb(210 214 222 / 0.7);
}
.ls-shell {
  background: rgb(var(--c-elev));
  color: rgb(var(--c-fg));
  border-radius: 14px;
  box-shadow: var(--shadow-pop);
  width: min(980px, 100%);
  max-height: 94vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgb(var(--c-tint) / 0.1);
}

.ls-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px 14px 18px;
}
.ls-head-art {
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  box-shadow: 0 4px 14px rgb(0 0 0 / 0.3);
}
.ls-head-titles {
  min-width: 0;
  flex: 1;
}
.ls-eyebrow {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: rgb(var(--c-accent));
}
.ls-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.3;
}
.ls-by {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.55);
}
.ls-x {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 9999px;
  color: rgb(var(--c-fg) / 0.6);
  flex-shrink: 0;
  align-self: flex-start;
}
.ls-x:hover {
  background: rgb(var(--c-tint) / 0.1);
  color: rgb(var(--c-fg));
}

/* Beads on a rail: compact, and the rail fills in as you progress. */
.ls-steps {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 2px 22px 10px;
  list-style: none;
}
.ls-step-why {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin: 0 22px 14px;
  padding: 9px 12px;
  border-radius: 9px;
  background: rgb(var(--c-tint) / 0.05);
  font-size: 12.5px;
  line-height: 1.5;
  color: rgb(var(--c-fg) / 0.66);
}
.ls-step-why svg {
  margin-top: 1px;
  color: rgb(var(--c-fg) / 0.4);
}
.ls-intro {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  margin-bottom: 14px;
  padding: 11px 13px;
  border-radius: 10px;
  border: 1px solid rgb(var(--c-accent) / 0.2);
  background: rgb(var(--c-accent) / 0.06);
  font-size: 13px;
  line-height: 1.5;
  color: rgb(var(--c-fg) / 0.82);
}
.ls-intro svg {
  margin-top: 1px;
}
.ls-step {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  font-size: 12.5px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.45);
  transition: color 0.2s ease;
}
.ls-step:last-child {
  flex: 0 0 auto;
}
/* The connector runs from this bead to the next one. */
.ls-step:not(:last-child)::after {
  content: '';
  flex: 1;
  height: 2px;
  margin: 0 10px;
  border-radius: 2px;
  background: rgb(var(--c-tint) / 0.12);
  transition: background-color 0.3s ease;
}
.ls-step.done::after {
  background: rgb(var(--c-accent) / 0.55);
}
.ls-step.active,
.ls-step.done {
  color: rgb(var(--c-fg));
}
.ls-step-bead {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  border-radius: 9999px;
  background: rgb(var(--c-tint) / 0.1);
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  transition:
    background-color 0.2s ease,
    color 0.2s ease,
    box-shadow 0.2s ease;
}
.ls-step.active .ls-step-bead {
  background: rgb(var(--c-accent));
  color: rgb(var(--c-accent-fg));
  box-shadow: 0 0 0 4px rgb(var(--c-accent) / 0.16);
}
.ls-step.done .ls-step-bead {
  background: rgb(var(--c-accent) / 0.22);
  color: rgb(var(--c-accent));
}
.ls-step-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ls-body {
  flex: 1;
  padding: 1.2rem 1.4rem 1.1rem;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  min-height: 0;
  outline: none;
}
.ls-body.sync { gap: 0.6rem; }
.ls-help {
  font-size: 0.85rem;
  color: rgba(230, 231, 235, 0.65);
  line-height: 1.5;
}
[data-theme='dannify-light'] .ls-help { color: rgba(22, 24, 28, 0.65); }

.ls-meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.65rem;
}
@media (max-width: 600px) {
  .ls-meta { grid-template-columns: 1fr; }
}
.ls-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgba(230, 231, 235, 0.5);
}
[data-theme='dannify-light'] .ls-field { color: rgba(22, 24, 28, 0.5); }
.ls-field input {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 0.55rem;
  padding: 0.5rem 0.7rem;
  color: #e6e7eb;
  font-size: 0.92rem;
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
  font-family: inherit;
  outline: none;
}
[data-theme='dannify-light'] .ls-field input {
  background: rgba(0, 0, 0, 0.03);
  border-color: rgba(0, 0, 0, 0.08);
  color: #16181c;
}
.ls-field input:focus { border-color: rgba(26, 208, 92, 0.6); }
.ls-dur { display: flex; align-items: center; gap: 0.5rem; }
.ls-dur input { flex: 1; }
.ls-dur-hint {
  font-size: 0.7rem;
  font-variant-numeric: tabular-nums;
  color: rgba(230, 231, 235, 0.45);
}
.ls-paste {
  min-height: 11rem;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 0.7rem;
  padding: 0.85rem 1rem;
  color: #e6e7eb;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 0.9rem;
  line-height: 1.45;
  resize: vertical;
  outline: none;
}
[data-theme='dannify-light'] .ls-paste {
  background: rgba(0, 0, 0, 0.03);
  border-color: rgba(0, 0, 0, 0.08);
  color: #16181c;
}
.ls-paste:focus { border-color: rgba(26, 208, 92, 0.5); }
.ls-detected {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.45rem 0.8rem;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.05);
  font-size: 0.8rem;
  color: rgba(230, 231, 235, 0.75);
  align-self: flex-start;
}
.ls-detected.synced { background: rgba(26, 208, 92, 0.14); color: #1ad05c; }

.ls-actions {
  display: flex;
  justify-content: space-between;
  gap: 0.55rem;
  margin-top: 0.4rem;
}
.ls-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.55rem 1.05rem;
  border-radius: 9999px;
  font-size: 0.86rem;
  font-weight: 600;
  transition: all 0.15s ease;
}
.ls-btn.primary { background: #1ad05c; color: #04140a; }
.ls-btn.primary:hover { background: #21e96a; }
.ls-btn.primary:disabled { background: rgba(26, 208, 92, 0.25); color: rgba(4, 20, 10, 0.5); cursor: not-allowed; }
.ls-btn.ghost { background: rgba(255, 255, 255, 0.06); color: rgba(230, 231, 235, 0.75); }
.ls-btn.ghost:hover { background: rgba(255, 255, 255, 0.12); color: #fff; }
.ls-btn.ghost:disabled { opacity: 0.4; cursor: not-allowed; }
[data-theme='dannify-light'] .ls-btn.ghost {
  background: rgba(0, 0, 0, 0.05);
  color: rgba(22, 24, 28, 0.7);
}

/* ─── Phase 2: transport rail ─── */
.ls-rail {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.55rem 0.6rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 0.8rem;
}
[data-theme='dannify-light'] .ls-rail {
  background: rgba(0, 0, 0, 0.03);
  border-color: rgba(0, 0, 0, 0.06);
}
.ls-rail-play {
  display: grid;
  place-items: center;
  width: 2.2rem;
  height: 2.2rem;
  border-radius: 9999px;
  background: #1ad05c;
  color: #04140a;
  flex-shrink: 0;
}
.ls-rail-play:hover { background: #21e96a; }
.ls-rail-scrub {
  flex: 1;
  height: 1.6rem;
  position: relative;
  cursor: pointer;
  display: flex;
  align-items: center;
  user-select: none;
}
.ls-rail-track {
  height: 4px;
  width: 100%;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.08);
  position: relative;
  overflow: hidden;
}
[data-theme='dannify-light'] .ls-rail-track { background: rgba(0, 0, 0, 0.08); }
.ls-rail-track::after {
  content: '';
  position: absolute;
  inset: 0;
  width: var(--p);
  background: linear-gradient(90deg, #1ad05c, #21e96a);
}
.ls-rail-loop {
  position: absolute;
  height: 14px;
  border-radius: 9999px;
  background: rgba(26, 208, 92, 0.22);
  border: 1px solid rgba(26, 208, 92, 0.5);
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
}
.ls-rail-tick {
  position: absolute;
  width: 2px;
  height: 12px;
  top: 50%;
  transform: translate(-50%, -50%);
  background: #1ad05c;
  border-radius: 2px;
  pointer-events: none;
}
.ls-rail-tick.error { background: #ff7c7c; }
.ls-rail-thumb {
  position: absolute;
  width: 12px;
  height: 12px;
  top: 50%;
  transform: translate(-50%, -50%);
  background: #fff;
  border: 2px solid #1ad05c;
  border-radius: 9999px;
  pointer-events: none;
}
.ls-rail-time {
  font-variant-numeric: tabular-nums;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
.ls-rail-time .now { color: #1ad05c; }
.ls-rail-time .sep { color: rgba(230, 231, 235, 0.35); }
.ls-rail-time .total { color: rgba(230, 231, 235, 0.6); }
[data-theme='dannify-light'] .ls-rail-time .total { color: rgba(22, 24, 28, 0.6); }

/* ─── Phase 2: transport buttons ─── */
.ls-trans {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  flex-wrap: wrap;
}
.ls-trans-sep {
  width: 1px;
  height: 1.4rem;
  background: rgba(255, 255, 255, 0.08);
  margin: 0 0.25rem;
}
[data-theme='dannify-light'] .ls-trans-sep { background: rgba(0, 0, 0, 0.08); }
.ls-tbtn {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.4rem 0.7rem;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.05);
  color: rgba(230, 231, 235, 0.8);
  font-size: 0.74rem;
  font-weight: 600;
}
[data-theme='dannify-light'] .ls-tbtn {
  background: rgba(0, 0, 0, 0.04);
  color: rgba(22, 24, 28, 0.75);
}
.ls-tbtn:hover { background: rgba(255, 255, 255, 0.1); color: #fff; }
.ls-tbtn:disabled { opacity: 0.4; cursor: not-allowed; }
.ls-tbtn.danger:hover { background: rgba(255, 90, 90, 0.18); color: #ff7c7c; }
.ls-speed {
  display: inline-flex;
  align-items: center;
  gap: 0.18rem;
  padding: 0.18rem 0.35rem;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 9999px;
}
[data-theme='dannify-light'] .ls-speed { background: rgba(0, 0, 0, 0.04); }
.ls-speed-btn {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 0.22rem 0.5rem;
  border-radius: 9999px;
  color: rgba(230, 231, 235, 0.55);
  transition: all 0.13s ease;
}
[data-theme='dannify-light'] .ls-speed-btn { color: rgba(22, 24, 28, 0.55); }
.ls-speed-btn:hover { color: #1ad05c; }
.ls-speed-btn.on { background: rgba(26, 208, 92, 0.2); color: #1ad05c; }

/* ─── Phase 2: hero card ─── */
.ls-hero {
  background: linear-gradient(135deg, rgba(26, 208, 92, 0.16), rgba(26, 208, 92, 0.04));
  border: 1px solid rgba(26, 208, 92, 0.28);
  border-radius: 0.9rem;
  padding: 0.85rem 1rem;
  position: sticky;
  top: 0;
  z-index: 2;
}
.ls-hero-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgba(230, 231, 235, 0.55);
}
[data-theme='dannify-light'] .ls-hero-meta { color: rgba(22, 24, 28, 0.55); }
.ls-hero-num {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.18rem 0.55rem;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.08);
  color: #1ad05c;
  font-variant-numeric: tabular-nums;
}
.ls-hero-time {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  color: #1ad05c;
  font-variant-numeric: tabular-nums;
}
.ls-hero-text {
  margin-top: 0.5rem;
  font-size: 1.5rem;
  line-height: 1.25;
  font-weight: 800;
  letter-spacing: -0.01em;
  color: #fff;
  word-break: break-word;
}
[data-theme='dannify-light'] .ls-hero-text { color: #16181c; }
.ls-hero-hint {
  margin-top: 0.4rem;
  font-size: 0.72rem;
  color: rgba(230, 231, 235, 0.55);
}
[data-theme='dannify-light'] .ls-hero-hint { color: rgba(22, 24, 28, 0.55); }
.ls-hero-hint kbd {
  background: rgba(255, 255, 255, 0.12);
  padding: 0.05rem 0.4rem;
  border-radius: 0.3rem;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 0.7rem;
  margin: 0 0.15rem;
}
[data-theme='dannify-light'] .ls-hero-hint kbd { background: rgba(0, 0, 0, 0.08); }

/* ─── Phase 2: lines list ─── */
.ls-lines2 {
  /* Dense on purpose: syncing is a rhythm task, and you need to see the
     lines that are coming, not five of them at a time. */
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 0.8rem;
  padding: 0.4rem;
  overflow-y: auto;
  overflow-anchor: none;
  max-height: 26rem;
}
.ls-lines2 > * {
  margin: 0;
}
[data-theme='dannify-light'] .ls-lines2 {
  background: rgba(0, 0, 0, 0.02);
  border-color: rgba(0, 0, 0, 0.05);
}
.ls-row {
  display: grid;
  grid-template-columns: 1.6rem auto 1fr auto;
  align-items: center;
  gap: 0.55rem;
  padding: 0.45rem 0.6rem;
  border-radius: 0.55rem;
  cursor: pointer;
  border: 1px solid transparent;
}
.ls-row:hover { background: rgba(255, 255, 255, 0.04); }
[data-theme='dannify-light'] .ls-row:hover { background: rgba(0, 0, 0, 0.03); }
.ls-row.active {
  background: rgba(26, 208, 92, 0.12);
  border-color: rgba(26, 208, 92, 0.28);
}
.ls-row-num {
  font-size: 0.7rem;
  font-weight: 700;
  color: rgba(230, 231, 235, 0.4);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
[data-theme='dannify-light'] .ls-row-num { color: rgba(22, 24, 28, 0.4); }
.ls-row-stamp {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.3rem 0.55rem;
  border-radius: 0.45rem;
  background: rgba(255, 255, 255, 0.05);
  color: rgba(230, 231, 235, 0.6);
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 0.74rem;
  font-weight: 700;
  white-space: nowrap;
  min-width: 7rem;
  justify-content: center;
  transition: all 0.13s ease;
}
[data-theme='dannify-light'] .ls-row-stamp {
  background: rgba(0, 0, 0, 0.05);
  color: rgba(22, 24, 28, 0.55);
}
.ls-row-stamp:hover { background: rgba(26, 208, 92, 0.2); color: #1ad05c; }
.ls-row-stamp.filled {
  background: rgba(26, 208, 92, 0.18);
  color: #1ad05c;
}
.ls-row-stamp.warn { background: rgba(255, 200, 60, 0.18); color: #ffd57a; }
.ls-row-stamp.error { background: rgba(255, 90, 90, 0.18); color: #ff8b8b; }
.ls-row-text {
  font-size: 0.95rem;
  color: rgba(230, 231, 235, 0.92);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
[data-theme='dannify-light'] .ls-row-text { color: rgba(22, 24, 28, 0.92); }
.ls-row-edit {
  font-size: 0.95rem;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(26, 208, 92, 0.4);
  border-radius: 0.4rem;
  padding: 0.3rem 0.55rem;
  color: #fff;
  font-family: inherit;
  outline: none;
}
[data-theme='dannify-light'] .ls-row-edit {
  background: rgba(0, 0, 0, 0.04);
  color: #16181c;
}
.ls-row-acts {
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
  opacity: 0;
  transition: opacity 0.13s ease;
}
.ls-row:hover .ls-row-acts,
.ls-row.active .ls-row-acts { opacity: 1; }
.ls-row-act {
  display: grid;
  place-items: center;
  width: 1.7rem;
  height: 1.7rem;
  border-radius: 9999px;
  color: rgba(230, 231, 235, 0.55);
}
.ls-row-act:hover { background: rgba(255, 255, 255, 0.1); color: #fff; }
.ls-row-act.on { background: rgba(26, 208, 92, 0.2); color: #1ad05c; }
.ls-row-act.danger:hover { background: rgba(255, 90, 90, 0.18); color: #ff8b8b; }
.ls-row-act:disabled { opacity: 0.3; cursor: not-allowed; pointer-events: none; }
[data-theme='dannify-light'] .ls-row-act { color: rgba(22, 24, 28, 0.55); }

.ls-row.error { background: rgba(255, 90, 90, 0.05); border-color: rgba(255, 90, 90, 0.18); }
.ls-row.warn { background: rgba(255, 200, 60, 0.04); border-color: rgba(255, 200, 60, 0.18); }

/* ─── Phase 2: inline add buttons ─── */
/* The between-lines "add here" target used to reserve a full row of height
   between every pair of lines, which halved how much of the song you could
   see. It is now a 6px hairline that only grows when you reach for it. */
.ls-insert {
  position: relative;
  width: 100%;
  height: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  padding: 0;
  font-size: 0.7rem;
  font-weight: 700;
  line-height: 1;
  color: rgba(230, 231, 235, 0.35);
  border-radius: 0.4rem;
  opacity: 0;
  overflow: hidden;
  /* Was 6px and fully transparent: a target nobody could find, which is why
     adding a line felt like a hidden feature. */
  transition:
    opacity 0.13s ease,
    height 0.13s ease,
    background 0.13s ease;
}
.ls-insert :deep(svg),
.ls-insert svg {
  opacity: 0;
  transition: opacity 0.13s ease;
}
.ls-lines2:hover .ls-insert {
  height: 14px;
  opacity: 0.75;
}
.ls-lines2:hover .ls-insert svg {
  opacity: 0.8;
}
.ls-insert:hover {
  height: 20px;
  opacity: 1;
  color: #1ad05c;
  background: rgba(26, 208, 92, 0.1);
}
.ls-insert:hover svg {
  opacity: 1;
}
.ls-hero-tip {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.4rem;
  font-size: 0.72rem;
  color: rgba(230, 231, 235, 0.5);
}
.ls-insert.top {
  height: 26px;
  opacity: 0.6;
}
.ls-insert.top svg {
  opacity: 1;
}
[data-theme='dannify-light'] .ls-insert { color: rgba(22, 24, 28, 0.35); }
[data-theme='dannify-light'] .ls-insert { color: rgba(22, 24, 28, 0.35); }

/* ─── Phase 2: quality pill ─── */
.ls-trans-label {
  margin-right: 1px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / 0.38);
}
.ls-progress {
  margin: 0 22px 10px;
}
.ls-progress-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}
.ls-progress-count {
  font-size: 12.5px;
  font-weight: 700;
  color: rgb(var(--c-fg) / 0.8);
}
.ls-progress-state {
  font-size: 11.5px;
  color: rgb(var(--c-fg) / 0.5);
}
.ls-progress-state.err {
  color: rgb(var(--c-danger));
}
.ls-progress-state.ok {
  color: rgb(var(--c-accent));
}
.ls-progress-track {
  height: 4px;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.1);
  overflow: hidden;
}
.ls-progress-fill {
  height: 100%;
  border-radius: 999px;
  background: rgb(var(--c-accent));
  transition: width 0.25s var(--ease-out);
}
.ls-progress-fill.err {
  background: rgb(var(--c-danger));
}
.ls-progress-fill.idle {
  background: rgb(var(--c-tint) / 0.2);
}

.ls-quality {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  flex-wrap: wrap;
}
.ls-quality-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.85rem;
  border-radius: 9999px;
  font-size: 0.78rem;
  font-weight: 600;
}
.ls-quality-pill.idle { background: rgba(255, 255, 255, 0.06); color: rgba(230, 231, 235, 0.55); }
.ls-quality-pill.partial { background: rgba(26, 208, 92, 0.12); color: rgba(26, 208, 92, 0.85); }
.ls-quality-pill.ok { background: rgba(26, 208, 92, 0.2); color: #1ad05c; }
.ls-quality-pill.err { background: rgba(255, 90, 90, 0.18); color: #ff8b8b; }
[data-theme='dannify-light'] .ls-quality-pill.idle {
  background: rgba(0, 0, 0, 0.05);
  color: rgba(22, 24, 28, 0.55);
}
.ls-quality-fix {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.7rem;
  border-radius: 9999px;
  background: rgba(255, 90, 90, 0.12);
  color: #ff8b8b;
  font-size: 0.74rem;
  font-weight: 600;
}
.ls-quality-fix:hover { background: rgba(255, 90, 90, 0.2); }

/* ─── Phase 3: review (unchanged) ─── */
.ls-review-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.6rem;
}
.ls-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.7rem;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 0.7rem;
}
[data-theme='dannify-light'] .ls-stat { background: rgba(0, 0, 0, 0.04); }
.ls-stat-num {
  font-size: 1.55rem;
  font-weight: 800;
  color: #1ad05c;
  font-variant-numeric: tabular-nums;
}
.ls-stat-label {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgba(230, 231, 235, 0.6);
  margin-top: 0.15rem;
}
[data-theme='dannify-light'] .ls-stat-label { color: rgba(22, 24, 28, 0.6); }
.ls-preview {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 0.7rem;
  max-height: 16rem;
  overflow-y: auto;
  padding: 0.7rem 0.9rem;
}
[data-theme='dannify-light'] .ls-preview {
  background: rgba(0, 0, 0, 0.03);
  border-color: rgba(0, 0, 0, 0.05);
}
.ls-preview pre {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 0.82rem;
  line-height: 1.55;
  color: #e6e7eb;
  white-space: pre-wrap;
}
[data-theme='dannify-light'] .ls-preview pre { color: #16181c; }
.ls-msg {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.55rem 0.85rem;
  border-radius: 0.6rem;
  font-size: 0.84rem;
  font-weight: 500;
}
.ls-msg.ok { background: rgba(26, 208, 92, 0.16); color: #1ad05c; }
.ls-msg.error { background: rgba(255, 90, 90, 0.16); color: #ff7c7c; }
.ls-submitting {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 0.7rem;
  padding: 0.65rem 0.85rem;
}
[data-theme='dannify-light'] .ls-submitting {
  background: rgba(0, 0, 0, 0.04);
  border-color: rgba(0, 0, 0, 0.06);
}
.ls-submit-step { font-size: 0.9rem; font-weight: 600; }
.ls-submit-sub {
  font-size: 0.75rem;
  color: rgba(230, 231, 235, 0.55);
  margin-top: 0.1rem;
}
[data-theme='dannify-light'] .ls-submit-sub { color: rgba(22, 24, 28, 0.55); }

/* Transitions */
.ls-modal-enter-active, .ls-modal-leave-active { transition: opacity 0.18s ease; }
.ls-modal-enter-active .ls-shell, .ls-modal-leave-active .ls-shell {
  transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1);
}
.ls-modal-enter-from, .ls-modal-leave-to { opacity: 0; }
.ls-modal-enter-from .ls-shell, .ls-modal-leave-to .ls-shell { transform: translateY(14px); }
.ls-fade-enter-active, .ls-fade-leave-active { transition: opacity 0.15s ease; }
.ls-fade-enter-from, .ls-fade-leave-to { opacity: 0; }
</style>
