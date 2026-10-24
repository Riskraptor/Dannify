<template>
  <Teleport to="body">
    <transition name="dlg">
      <div v-if="open" class="rp-layer" @mousedown.self="close">
        <div
          ref="box"
          class="rp menu-surface"
          role="dialog"
          aria-modal="true"
          :aria-label="category === 'idea' ? t('problems.ideaTitle') : t('problems.title')"
          @keydown="onKey"
        >
          <!-- Sent, or kept to send later -->
          <div v-if="result" class="rp-done">
            <div class="rp-done-icon" :class="{ 'is-wait': result.status === 'queued' }">
              <Icon :icon="result.status === 'queued' ? 'ph:clock-countdown' : 'ph:check-bold'" class="h-6 w-6" />
            </div>
            <h2 class="rp-title">
              {{ result.status === 'queued' ? t('problems.queuedTitle') : t('problems.sentTitle') }}
            </h2>
            <p class="rp-sub">
              {{
                result.status === 'queued'
                  ? result.needsYou
                    ? t('problems.queuedAskText')
                    : t('problems.queuedText')
                  : t('problems.sentText')
              }}
            </p>
            <p class="rp-ref">{{ t('problems.reference', { id: result.id }) }}</p>
            <button ref="doneBtn" class="btn-accent btn-pill mt-5 px-6" @click="close">
              {{ t('common.close') }}
            </button>
          </div>

          <template v-else>
            <!-- Written while offline: sent now, with one slide. -->
            <template v-if="keptEmail">
              <header class="rp-head">
                <div class="min-w-0">
                  <h2 class="rp-title">{{ t('problems.heldTitle') }}</h2>
                  <p class="rp-sub">{{ t('problems.heldText', { date: keptDate }) }}</p>
                </div>
                <button class="icon-btn h-8 w-8" :title="t('common.close')" :aria-label="t('common.close')" @click="close">
                  <Icon icon="ph:x" class="h-4 w-4" />
                </button>
              </header>
              <div class="rp-body">
                <blockquote v-if="keptEmail.held_preview" class="rp-kept">{{ keptEmail.held_preview }}</blockquote>
                <HCaptchaBox v-if="captchaKey" ref="captchaBox" :sitekey="captchaKey" />
                <p v-if="error" class="rp-error">
                  <Icon icon="ph:warning" class="h-4 w-4" />
                  {{ error }}
                </p>
              </div>
            </template>
            <template v-else>
            <header class="rp-head">
              <div class="min-w-0">
                <h2 class="rp-title">{{ category === 'idea' ? t('problems.ideaTitle') : t('problems.title') }}</h2>
                <p class="rp-sub">{{ category === 'idea' ? t('problems.ideaIntro') : t('problems.intro') }}</p>
              </div>
              <button class="icon-btn h-8 w-8" :title="t('common.close')" :aria-label="t('common.close')" @click="close">
                <Icon icon="ph:x" class="h-4 w-4" />
              </button>
            </header>

            <div class="rp-body">
              <p class="rp-label">{{ t('problems.whatKind') }}</p>
              <div class="rp-kinds" role="radiogroup" :aria-label="t('problems.whatKind')">
                <button
                  v-for="k in kinds"
                  :key="k.id"
                  class="rp-kind"
                  role="radio"
                  :aria-checked="category === k.id"
                  :class="{ 'is-on': category === k.id }"
                  @click="category = k.id"
                >
                  <Icon :icon="k.icon" class="h-4 w-4" />
                  {{ t(k.label) }}
                </button>
              </div>

              <label class="rp-label" for="rp-what">{{ category === 'idea' ? t('problems.yourIdea') : t('problems.whatHappened') }}</label>
              <textarea
                id="rp-what"
                ref="what"
                v-model="description"
                class="rp-field rp-text"
                rows="5"
                :maxlength="5000"
                :placeholder="hint"
              />
              <p class="rp-count" :class="{ 'is-short': description.trim().length > 0 && !longEnough }">
                {{ longEnough ? `${description.length} / 5000` : t('problems.tooShort') }}
              </p>

              <label class="rp-label" for="rp-contact">{{ t('problems.contact') }}</label>
              <input
                id="rp-contact"
                v-model="contact"
                class="rp-field"
                type="email"
                autocomplete="email"
                :placeholder="t('problems.contactHint')"
              />

              <!-- The check the form asks for, so no robot sends a report. -->
              <HCaptchaBox v-if="captchaKey" ref="captchaBox" :sitekey="captchaKey" />

              <!-- No person sees this, so no person fills it in (report.py). -->
              <input v-model="website" class="rp-trap" type="text" name="website" tabindex="-1" autocomplete="off" aria-hidden="true" />

              <!-- What goes with it, chosen one by one. The logs are the most
                   detailed and the least often needed: off unless asked for.
                   An idea needs none of it. -->
              <section v-if="category !== 'idea'" class="rp-with" :aria-label="t('problems.withIt')">
                <p class="rp-label">{{ t('problems.withIt') }}</p>
                <label v-if="song" class="rp-part">
                  <Icon icon="ph:music-notes" class="rp-part-icon h-4 w-4" />
                  <span class="rp-part-text">
                    <b>{{ t('problems.partSong') }}</b>
                    <small dir="auto">{{ song }}</small>
                  </span>
                  <input v-model="includeSong" type="checkbox" class="switch" />
                </label>
                <label v-for="part in PARTS" :key="part.id" class="rp-part">
                  <Icon :icon="part.icon" class="rp-part-icon h-4 w-4" />
                  <span class="rp-part-text">
                    <b>{{ t(part.label) }}</b>
                    <small>{{ partText(part.id) }}</small>
                  </span>
                  <input v-model="parts[part.id]" type="checkbox" class="switch" />
                </label>

                <button class="rp-what-in" type="button" :aria-expanded="showWhat ? 'true' : 'false'" @click="showWhat = !showWhat">
                  <Icon :icon="showWhat ? 'ph:caret-down' : 'ph:caret-right'" class="h-3 w-3" />
                  {{ t('problems.seeWhat') }}
                </button>
                <div v-if="showWhat" class="rp-preview">
                  <div class="seg" role="tablist">
                    <button
                      v-for="part in PARTS"
                      :key="part.id"
                      class="seg-item"
                      role="tab"
                      :class="{ 'is-active': previewTab === part.id }"
                      :aria-selected="previewTab === part.id ? 'true' : 'false'"
                      @click="previewTab = part.id"
                    >
                      {{ t(part.label) }}
                      <Icon v-if="!parts[part.id]" icon="ph:prohibit" class="h-3 w-3 opacity-60" :title="t('problems.notSent')" />
                    </button>
                  </div>
                  <p v-if="!parts[previewTab]" class="rp-preview-off">{{ t('problems.notSent') }}</p>
                  <pre class="rp-pre" :class="{ 'is-off': !parts[previewTab] }">{{ previewText }}</pre>
                </div>
                <p class="rp-never">
                  <Icon icon="ph:lock-simple" class="h-3.5 w-3.5 shrink-0" />
                  {{ t('problems.never') }}
                </p>
              </section>

              <p v-if="error" class="rp-error">
                <Icon icon="ph:warning" class="h-4 w-4" />
                {{ error }}
              </p>
            </div>

            </template>
            <footer class="rp-foot">
              <button class="btn min-w-[88px]" @click="close">{{ t('common.cancel') }}</button>
              <!-- Sending is a slide of the note to the end: a person does it
                   in a moment, and nothing sends by a stray click. -->
              <div
                ref="track"
                class="rp-slide"
                :class="{ 'is-ready': canSend, 'is-sending': sending, 'is-dragging': dragging }"
              >
                <span class="rp-slide-fill" :style="{ width: `${knobX + KNOB}px` }" />
                <span class="rp-slide-text">{{ sending ? t('problems.sending') : t('problems.slideToSend') }}</span>
                <button
                  class="rp-slide-knob"
                  :style="{ transform: `translateX(${knobX}px)` }"
                  :disabled="!canSend"
                  role="slider"
                  :aria-label="t('problems.slideLabel')"
                  aria-valuemin="0"
                  aria-valuemax="100"
                  :aria-valuenow="Math.round((knobX / Math.max(1, travel)) * 100)"
                  @pointerdown="grab"
                  @keydown="knobKey"
                >
                  <span v-if="sending" class="spinner h-4 w-4" />
                  <Icon v-else icon="ph:music-note-fill" class="h-5 w-5" />
                </button>
              </div>
            </footer>
          </template>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { useReporting } from '/src/model/problems'
import { usePlayer } from '/src/model/player'
import HCaptchaBox from '/src/components/ui/HCaptchaBox.vue'
import { rememberFocus } from '/src/model/focusTrap'
import { useI18n } from '/src/i18n'
import { tp } from '/src/i18n/platform'

const { t, locale } = useI18n()
const reporting = useReporting()
const open = reporting.dialogOpen
// A report written while offline, opened from "Your report is ready to send".
const keptEmail = computed(() => (reporting.held.value && reporting.held.value.email) || null)
const keptDate = computed(() => {
  const at = keptEmail.value && Number(keptEmail.value.held_at)
  return at ? new Date(at).toLocaleString(locale.value || 'en', { dateStyle: 'medium', timeStyle: 'short' }) : ''
})

const kinds = [
  { id: 'idea', icon: 'ph:lightbulb', label: 'problems.kindIdea' },
  { id: 'playback', icon: 'ph:play-circle', label: 'problems.kindPlayback' },
  { id: 'downloads', icon: 'ph:download-simple', label: 'problems.kindDownloads' },
  { id: 'lyrics', icon: 'ph:microphone-stage', label: 'problems.kindLyrics' },
  { id: 'looks', icon: 'ph:paint-brush', label: 'problems.kindLooks' },
  { id: 'crash', icon: 'ph:warning-octagon', label: 'problems.kindCrash' },
  { id: 'other', icon: 'ph:chat-circle-dots', label: 'problems.kindOther' },
]

// What can go with a report (report.py PARTS), each chosen on its own.
const PARTS = [
  { id: 'about', icon: 'ph:info', label: 'problems.partAbout' },
  { id: 'errors', icon: 'ph:bug', label: 'problems.partErrors' },
  { id: 'logs', icon: 'ph:list-bullets', label: 'problems.partLogs' },
]
const HINTS = {
  idea: 'problems.ideaHint',
  playback: 'problems.hintPlayback',
  downloads: 'problems.hintDownloads',
  lyrics: 'problems.hintLyrics',
  looks: 'problems.hintLooks',
  crash: 'problems.hintCrash',
}
// What was written and not sent yet, and the address to reply to: kept on
// this computer, so closing the window, or the app, loses nothing.
const DRAFT_KEY = 'dannify-report-draft'
const CONTACT_KEY = 'dannify-report-contact'

function readStore(key) {
  try {
    return JSON.parse(localStorage.getItem(key) || 'null')
  } catch {
    return null
  }
}
function writeStore(key, value) {
  try {
    if (value == null) localStorage.removeItem(key)
    else localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Storage that throws: kept for this time only.
  }
}

const player = usePlayer()
const category = ref('playback')
const website = ref('')
const description = ref('')
const contact = ref(String(readStore(CONTACT_KEY) || ''))
const parts = reactive({ about: true, errors: true, logs: false })
const includeSong = ref(true)
const showWhat = ref(false)
const previewTab = ref('about')
const preview = ref(null)
const sending = ref(false)
const error = ref('')
const result = ref(null)
const box = ref(null)
const what = ref(null)
const doneBtn = ref(null)
let giveBack = null

// Slide to send: where the note is on its track (the handlers are below).
const KNOB = 40
const track = ref(null)
const knobX = ref(0)
const dragging = ref(false)
const travel = computed(() => (track.value ? track.value.clientWidth - KNOB - 8 : 200))

const hint = computed(() => t(HINTS[category.value] || 'problems.whatHappenedHint'))
const song = computed(() => {
  const track = player.currentTrack.value
  if (!track || !track.title) return ''
  return track.artist ? `${track.title} \u2014 ${track.artist}` : String(track.title)
})

function size(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}
function partText(id) {
  const p = preview.value
  if (id === 'about') return tp('problems.inAbout')
  if (id === 'errors') return p ? t('problems.partErrorsCount', { count: p.errors }) : t('problems.partErrorsText')
  const bytes = p ? p.logs.reduce((sum, l) => sum + (l.bytes || 0), 0) : 0
  return bytes ? t('problems.partLogsSize', { size: size(bytes) }) : t('problems.partLogsText')
}
const previewText = computed(() => {
  const p = preview.value
  if (!p) return '\u2026'
  if (previewTab.value === 'about') return p.about
  if (previewTab.value === 'errors') return p.errors_text || t('problems.noneYet')
  return p.logs_tail || t('problems.noneYet')
})

function loadPreview() {
  API.getReportPreview()
    .then((res) => {
      preview.value = res.data || null
    })
    .catch(() => {})
}

// The draft as it is typed, so nothing written is lost.
watch([category, description], ([kind, text]) => {
  if (!open.value || result.value || keptEmail.value) return
  writeStore(DRAFT_KEY, text.trim() ? { category: kind, description: text } : null)
})

const longEnough = computed(() => description.value.trim().length >= 10)
const contactOk = computed(
  () => !contact.value.trim() || /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(contact.value.trim())
)
// hCaptcha, when the form asks for it: run as the note reaches the end, its
// challenge (when there is one) in the middle of the window.
const captchaKey = computed(() => (reporting.status.captcha && reporting.status.captcha.sitekey) || '')
const captchaBox = ref(null)
const idea = computed(() => category.value === 'idea')
const canSend = computed(() => !sending.value && (keptEmail.value ? true : longEnough.value && contactOk.value))

// Immediate as well: the dialog is loaded the first time it is opened, by
// which time it is already open (App.vue).
watch(
  open,
  async (on) => {
    if (!on) return
    giveBack = rememberFocus()
    result.value = null
    error.value = ''
    knobX.value = 0
    showWhat.value = false
    // Each time: the logs stay off unless asked for this time.
    Object.assign(parts, { about: true, errors: true, logs: false })
    includeSong.value = true
    const draft = readStore(DRAFT_KEY)
    if (!description.value && draft && typeof draft.description === 'string') {
      description.value = draft.description
      if (draft.category) category.value = draft.category
    }
    if (reporting.kind.value) category.value = reporting.kind.value
    loadPreview()
    await nextTick()
    if (keptEmail.value) box.value && box.value.querySelector('.rp-slide-knob') && box.value.querySelector('.rp-slide-knob').focus()
    else what.value && what.value.focus()
  },
  { immediate: true }
)

function close() {
  if (sending.value) return
  open.value = false
  // A kept report not sent now stays kept, for the next time it is offered.
  reporting.held.value = null
  // Written and not sent is kept for next time; sent is cleared.
  if (result.value) {
    description.value = ''
    category.value = 'playback'
    writeStore(DRAFT_KEY, null)
  }
  if (giveBack) setTimeout(giveBack, 0)
}

async function submit() {
  if (!canSend.value) return
  if (!keptEmail.value && !contactOk.value) {
    error.value = t('problems.badContact')
    return
  }
  sending.value = true
  error.value = ''
  let captcha = ''
  if (captchaKey.value) {
    try {
      captcha = await captchaBox.value.run()
    } catch (err) {
      // Closed the challenge: the note goes back, and nothing is said. One
      // that could not load says so.
      sending.value = false
      knobBack()
      if (!/challenge-closed|challenge-expired/.test(String(err && (err.message || err)))) {
        error.value = t('problems.captchaOffline')
      }
      return
    }
  }
  try {
    result.value = keptEmail.value
      ? await reporting.sendHeld(captcha)
      : await reporting.send(
      {
        category: category.value,
        description: description.value,
        contact: contact.value.trim(),
        include: idea.value ? { about: false, errors: false, logs: false } : { ...parts },
        context: !idea.value && includeSong.value ? song.value : '',
        website: website.value,
      },
      captcha
    )
    // The address, for next time: a reply goes to the same place.
    if (!keptEmail.value) writeStore(CONTACT_KEY, contact.value.trim() || null)
    writeStore(DRAFT_KEY, null)
    await nextTick()
    doneBtn.value && doneBtn.value.focus()
  } catch (err) {
    const code = err && err.response && err.response.status
    error.value =
      code === 503
        ? t('problems.notOpen')
        : code === 429
          ? t('problems.tooMany')
          : err && !err.response && !err.status
            ? t('problems.offline')
            : t('problems.failed')
    knobBack()
    // A check is good for one try.
    if (captchaBox.value) captchaBox.value.reset()
  } finally {
    sending.value = false
  }
}

// --- Slide to send ----------------------------------------------------------
let grabbedAt = 0
let grabbedKnob = 0
function grab(e) {
  if (!canSend.value) return
  e.preventDefault()
  dragging.value = true
  grabbedAt = e.clientX
  grabbedKnob = knobX.value
  e.currentTarget.setPointerCapture(e.pointerId)
  e.currentTarget.addEventListener('pointermove', drag)
  e.currentTarget.addEventListener('pointerup', letGo, { once: true })
  e.currentTarget.addEventListener('pointercancel', letGo, { once: true })
}
function drag(e) {
  knobX.value = Math.max(0, Math.min(travel.value, grabbedKnob + e.clientX - grabbedAt))
}
function letGo(e) {
  e.currentTarget.removeEventListener('pointermove', drag)
  dragging.value = false
  if (knobX.value >= travel.value - 6) slidHome()
  else knobBack()
}
function slidHome() {
  knobX.value = travel.value
  submit()
}
function knobBack() {
  knobX.value = 0
}
function knobKey(e) {
  if (!canSend.value) return
  if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
    e.preventDefault()
    knobX.value = Math.min(travel.value, knobX.value + travel.value / 4)
    if (knobX.value >= travel.value - 1) slidHome()
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
    e.preventDefault()
    knobBack()
  } else if (e.key === 'End' || e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    slidHome()
  }
}

function onKey(e) {
  e.stopPropagation()
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
  } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !result.value) {
    e.preventDefault()
    if (canSend.value) slidHome()
  } else if (e.key === 'Tab' && box.value) {
    // Keep focus inside the dialog.
    const stops = [...box.value.querySelectorAll('button, textarea, input')].filter((el) => !el.disabled)
    if (!stops.length) return
    const first = stops[0]
    const last = stops[stops.length - 1]
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }
}
</script>

<style scoped>
.rp-layer {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(0 0 0 / 0.5);
}
.rp {
  display: flex;
  flex-direction: column;
  width: min(560px, 100%);
  max-height: calc(100vh - 48px);
  overflow: hidden;
}
.rp-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 20px 20px 6px 24px;
}
.rp-title {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.rp-sub {
  margin-top: 4px;
  font-size: 13px;
  line-height: 1.5;
  color: rgb(var(--c-fg) / var(--fg-62));
}
.rp-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 24px 16px;
}
.rp-label {
  display: block;
  margin: 14px 0 7px;
  font-size: 12px;
  font-weight: 700;
  color: rgb(var(--c-fg) / 0.72);
}
.rp-kinds {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 6px;
}
.rp-kind {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid rgb(var(--c-tint) / 0.12);
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.78);
  transition:
    background-color 0.12s ease,
    border-color 0.12s ease;
}
.rp-kind:hover {
  background: rgb(var(--c-tint) / 0.05);
}
.rp-kind.is-on {
  border-color: rgb(var(--c-accent));
  background: rgb(var(--c-accent) / 0.12);
  color: rgb(var(--c-fg));
}
.rp-field {
  width: 100%;
  padding: 9px 12px;
  border-radius: 8px;
  border: 1px solid rgb(var(--c-tint) / 0.14);
  background: rgb(var(--c-tint) / 0.05);
  color: rgb(var(--c-fg));
  font-size: 13.5px;
  outline: none;
}
.rp-field:focus {
  border-color: rgb(var(--c-accent));
  box-shadow: 0 0 0 1px rgb(var(--c-accent));
}
.rp-text {
  resize: vertical;
  min-height: 110px;
  line-height: 1.5;
}
.rp-count {
  margin-top: 4px;
  text-align: right;
  font-size: 11px;
  color: rgb(var(--c-fg) / var(--fg-40));
}
.rp-count.is-short {
  color: rgb(var(--c-fg) / var(--fg-60));
}
/* What was written while offline, as it will go. */
.rp-kept {
  max-height: 180px;
  overflow-y: auto;
  margin: 4px 0 6px;
  padding: 12px 14px;
  border-left: 3px solid rgb(var(--c-accent));
  border-radius: 8px;
  background: rgb(var(--c-tint) / 0.05);
  font-size: 13.5px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: rgb(var(--c-fg) / 0.88);
}
.rp-with {
  margin-top: 4px;
}
.rp-part {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgb(var(--c-tint) / 0.1);
  background: rgb(var(--c-tint) / 0.03);
  cursor: pointer;
  transition:
    background-color 0.12s ease,
    border-color 0.12s ease;
}
.rp-part:hover {
  background: rgb(var(--c-tint) / 0.06);
}
.rp-part:has(.switch:checked) {
  border-color: rgb(var(--c-accent) / 0.35);
}
.rp-part-icon {
  flex-shrink: 0;
  color: rgb(var(--c-fg) / 0.55);
}
.rp-part-text {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 1px;
}
.rp-part-text b {
  font-size: 13px;
  font-weight: 650;
}
.rp-part-text small {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11.5px;
  line-height: 1.4;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.rp-what-in {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 10px 0 0 2px;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--c-accent));
}
.rp-preview {
  margin-top: 8px;
  padding: 10px;
  border-radius: 10px;
  background: rgb(var(--c-tint) / 0.05);
}
.rp-preview-off {
  margin-top: 8px;
  font-size: 11.5px;
  font-weight: 600;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.rp-pre {
  max-height: 180px;
  margin-top: 8px;
  overflow: auto;
  font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: rgb(var(--c-fg) / 0.8);
}
.rp-pre.is-off {
  opacity: 0.45;
}
.rp-never {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 11.5px;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.rp-error {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  font-size: 12.5px;
  color: rgb(var(--c-danger));
}
.rp-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  background: rgb(var(--c-tint) / 0.03);
  border-top: 1px solid rgb(var(--c-tint) / 0.07);
}
.rp-trap {
  position: absolute;
  left: -9999px;
  width: 1px;
  height: 1px;
  opacity: 0;
}
.rp-slide {
  position: relative;
  display: flex;
  align-items: center;
  width: 250px;
  height: 48px;
  padding: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.08);
  box-shadow: inset 0 0 0 1px rgb(var(--c-tint) / 0.1);
  user-select: none;
  touch-action: none;
}
.rp-slide-fill {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  border-radius: 999px;
  background: rgb(var(--c-accent) / 0.22);
  transition: width 0.25s ease;
}
.rp-slide.is-dragging .rp-slide-fill,
.rp-slide.is-dragging .rp-slide-knob {
  transition: none;
}
.rp-slide-text {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  padding-left: 40px;
  font-size: 12.5px;
  font-weight: 700;
  color: rgb(var(--c-fg) / 0.45);
  pointer-events: none;
}
.rp-slide.is-ready .rp-slide-text {
  color: rgb(var(--c-fg) / 0.85);
  background: linear-gradient(90deg, transparent 0%, rgb(255 255 255 / 0.5) 50%, transparent 100%) -200% 0 / 50% 100% no-repeat;
  background-clip: text;
  animation: rp-shine 2.4s ease-in-out infinite;
}
.rp-slide-knob {
  position: relative;
  z-index: 1;
  display: grid;
  width: 40px;
  height: 40px;
  flex: none;
  place-items: center;
  border-radius: 999px;
  color: rgb(var(--c-fg) / 0.5);
  background: rgb(var(--c-tint) / 0.12);
  cursor: grab;
  transition:
    transform 0.3s cubic-bezier(0.2, 0.9, 0.2, 1.1),
    background-color 0.15s ease;
}
.rp-slide.is-ready .rp-slide-knob {
  color: rgb(var(--c-accent-fg));
  background: rgb(var(--c-accent));
  box-shadow: 0 6px 16px rgb(var(--c-accent) / 0.4);
}
.rp-slide.is-dragging .rp-slide-knob {
  cursor: grabbing;
}
.rp-slide-knob:focus-visible {
  outline: 2px solid rgb(var(--c-fg));
  outline-offset: 2px;
}
.rp-slide-knob:disabled {
  cursor: not-allowed;
}
@keyframes rp-shine {
  to {
    background-position: 300% 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .rp-slide.is-ready .rp-slide-text {
    animation: none;
  }
}
.rp-done {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 36px 28px 30px;
  text-align: center;
}
.rp-done-icon {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  margin-bottom: 14px;
  border-radius: 999px;
  background: rgb(var(--c-accent) / 0.16);
  color: rgb(var(--c-accent));
}
.rp-done-icon.is-wait {
  background: rgb(var(--c-tint) / 0.1);
  color: rgb(var(--c-fg) / 0.8);
}
.rp-ref {
  margin-top: 10px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-fg) / var(--fg-45));
}
.dlg-enter-active,
.dlg-leave-active {
  transition: opacity 0.14s ease;
}
.dlg-enter-from,
.dlg-leave-to {
  opacity: 0;
}
</style>
