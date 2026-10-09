<template>
  <Teleport to="body">
    <transition name="dlg">
      <div v-if="open" class="rp-layer" @mousedown.self="close">
        <div
          ref="box"
          class="rp menu-surface"
          role="dialog"
          aria-modal="true"
          :aria-label="t('problems.title')"
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
              {{ result.status === 'queued' ? t('problems.queuedText') : t('problems.sentText') }}
            </p>
            <p class="rp-ref">{{ t('problems.reference', { id: result.id }) }}</p>
            <button ref="doneBtn" class="btn-accent btn-pill mt-5 px-6" @click="close">
              {{ t('common.close') }}
            </button>
          </div>

          <template v-else>
            <header class="rp-head">
              <div class="min-w-0">
                <h2 class="rp-title">{{ t('problems.title') }}</h2>
                <p class="rp-sub">{{ t('problems.intro') }}</p>
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

              <label class="rp-label" for="rp-what">{{ t('problems.whatHappened') }}</label>
              <textarea
                id="rp-what"
                ref="what"
                v-model="description"
                class="rp-field rp-text"
                rows="5"
                :maxlength="5000"
                :placeholder="t('problems.whatHappenedHint')"
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

              <label class="rp-check">
                <input v-model="includeDiagnostics" type="checkbox" class="check" />
                <span>{{ t('problems.includeDiagnostics') }}</span>
              </label>
              <button class="rp-what-in" type="button" @click="showWhat = !showWhat">
                <Icon :icon="showWhat ? 'ph:caret-down' : 'ph:caret-right'" class="h-3 w-3" />
                {{ t('problems.whatIsIncluded') }}
              </button>
              <ul v-if="showWhat" class="rp-list">
                <li>{{ t('problems.inLogs') }}</li>
                <li>{{ t('problems.inErrors') }}</li>
                <li>{{ tp('problems.inAbout') }}</li>
                <li class="rp-never">{{ t('problems.never') }}</li>
              </ul>

              <p v-if="error" class="rp-error">
                <Icon icon="ph:warning" class="h-4 w-4" />
                {{ error }}
              </p>
            </div>

            <footer class="rp-foot">
              <button class="btn min-w-[88px]" @click="close">{{ t('common.cancel') }}</button>
              <button class="btn-accent min-w-[120px]" :disabled="!canSend" @click="submit">
                <span v-if="sending" class="spinner h-4 w-4" />
                <Icon v-else icon="ph:paper-plane-tilt" class="h-4 w-4" />
                {{ sending ? t('problems.sending') : t('problems.send') }}
              </button>
            </footer>
          </template>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { Icon } from '@iconify/vue'
import { useReporting } from '/src/model/problems'
import { rememberFocus } from '/src/model/focusTrap'
import { useI18n } from '/src/i18n'
import { tp } from '/src/i18n/platform'

const { t } = useI18n()
const reporting = useReporting()
const open = reporting.dialogOpen

const kinds = [
  { id: 'playback', icon: 'ph:play-circle', label: 'problems.kindPlayback' },
  { id: 'downloads', icon: 'ph:download-simple', label: 'problems.kindDownloads' },
  { id: 'lyrics', icon: 'ph:microphone-stage', label: 'problems.kindLyrics' },
  { id: 'looks', icon: 'ph:paint-brush', label: 'problems.kindLooks' },
  { id: 'crash', icon: 'ph:warning-octagon', label: 'problems.kindCrash' },
  { id: 'other', icon: 'ph:chat-circle-dots', label: 'problems.kindOther' },
]

const category = ref('playback')
const description = ref('')
const contact = ref('')
const includeDiagnostics = ref(true)
const showWhat = ref(false)
const sending = ref(false)
const error = ref('')
const result = ref(null)
const box = ref(null)
const what = ref(null)
const doneBtn = ref(null)
let giveBack = null

const longEnough = computed(() => description.value.trim().length >= 10)
const contactOk = computed(
  () => !contact.value.trim() || /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(contact.value.trim())
)
const canSend = computed(() => longEnough.value && contactOk.value && !sending.value)

watch(open, async (on) => {
  if (!on) return
  giveBack = rememberFocus()
  result.value = null
  error.value = ''
  await nextTick()
  what.value && what.value.focus()
})

function close() {
  if (sending.value) return
  open.value = false
  // Written and not sent is kept for next time; sent is cleared.
  if (result.value) {
    description.value = ''
    contact.value = ''
    category.value = 'playback'
  }
  if (giveBack) setTimeout(giveBack, 0)
}

async function submit() {
  if (!canSend.value) return
  if (!contactOk.value) {
    error.value = t('problems.badContact')
    return
  }
  sending.value = true
  error.value = ''
  try {
    result.value = await reporting.send({
      category: category.value,
      description: description.value,
      contact: contact.value.trim(),
      include_diagnostics: includeDiagnostics.value,
    })
    await nextTick()
    doneBtn.value && doneBtn.value.focus()
  } catch (err) {
    const code = err && err.response && err.response.status
    error.value = code === 503 ? t('problems.notOpen') : t('problems.failed')
  } finally {
    sending.value = false
  }
}

function onKey(e) {
  e.stopPropagation()
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
  } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !result.value) {
    e.preventDefault()
    submit()
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
.rp-check {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 16px;
  font-size: 13px;
}
.rp-what-in {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 6px 0 0 28px;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--c-accent));
}
.rp-list {
  margin: 6px 0 0 44px;
  list-style: disc;
  font-size: 12px;
  line-height: 1.7;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.rp-never {
  color: rgb(var(--c-fg) / 0.78);
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
