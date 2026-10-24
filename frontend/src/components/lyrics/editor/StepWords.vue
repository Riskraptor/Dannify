<template>
  <section class="step-body">
    <div class="words">
      <!-- The song in one line. Its details are the song's own and are not
           changed here: lyrics are for the song that is playing. Only a song
           that came without a title or an artist asks for them. -->
      <div class="songline">
        <span class="songline-text" dir="auto">
          <b>{{ form.track || '—' }}</b>
          <span class="dot">·</span>
          {{ form.artist || '—' }}
          <template v-if="form.album">
            <span class="dot">·</span>
            {{ form.album }}
          </template>
        </span>
      </div>

      <div v-if="s.showDetails.value" class="details">
        <label class="detail">
          <span>{{ t('publish.title') }}</span>
          <input
            ref="titleEl"
            v-model="form.track"
            class="field"
            type="text"
            dir="auto"
            required
            :aria-invalid="!form.track.trim() ? 'true' : undefined"
          />
        </label>
        <label class="detail">
          <span>{{ t('publish.artist') }}</span>
          <input
            v-model="form.artist"
            class="field"
            type="text"
            dir="auto"
            required
            :aria-invalid="!form.artist.trim() ? 'true' : undefined"
          />
        </label>
        <label class="detail">
          <span>{{ t('publish.album') }}</span>
          <input v-model="form.album" class="field" type="text" dir="auto" :placeholder="t('publish.albumOptional')" />
        </label>
      </div>

      <ListenBar />

      <p v-if="s.restored.value" class="note">
        <Icon icon="ph:clock-counter-clockwise-bold" class="h-4 w-4 shrink-0" />
        <span class="flex-1">{{ t('publish.restored') }}</span>
        <button class="note-act" @click="s.startOver">{{ t('publish.startOver') }}</button>
      </p>
      <p v-if="s.seedTimes.value.length && !s.detectedSynced.value" class="note is-accent">
        <Icon icon="ph:clock-clockwise-bold" class="h-4 w-4 shrink-0" />
        <span>{{ t('publish.keepsTiming') }}</span>
      </p>

      <!-- A chorus sung four times is typed once: select it, repeat it.
           The buttons keep the box's selection (mousedown would take it). -->
      <div class="tools" role="toolbar" :aria-label="t('publish.repeatLines')">
        <button
          class="tool press"
          :disabled="!form.raw.trim()"
          :title="`${t('publish.repeatLines')} (Ctrl+D)`"
          @mousedown.prevent
          @click="repeat"
        >
          <Icon icon="ph:copy-simple-bold" class="h-4 w-4" />
          <span>{{ t('publish.repeatLines') }}</span>
          <kbd class="kbd">Ctrl D</kbd>
        </button>
        <button v-if="part" class="tool press" :title="part" @mousedown.prevent @click="putPart">
          <Icon icon="ph:arrow-elbow-down-right-bold" class="h-4 w-4" />
          <span class="truncate">{{ t('publish.insertPart', { start: partLabel(part) }) }}</span>
        </button>
        <span class="tools-hint">{{ t('publish.repeatHint') }}</span>
      </div>

      <label class="paste-wrap">
        <span class="sr-only">{{ t('publish.pastePlaceholder') }}</span>
        <textarea
          ref="pasteEl"
          v-model="form.raw"
          class="paste"
          dir="auto"
          :placeholder="t('publish.pastePlaceholder')"
          spellcheck="false"
          @keydown="onPasteKey"
        ></textarea>
      </label>

      <!-- Always the same height, filled or not, so the editor does not
           jump as the first line is typed. -->
      <p class="detected" :class="{ 'is-synced': s.detectedSynced.value }" aria-live="polite">
        <template v-if="s.detectedSynced.value">
          <Icon icon="ph:check-circle-fill" class="h-4 w-4 shrink-0" />
          {{ t('publish.detectedSynced', { count: s.syncedCount.value }) }}
        </template>
        <template v-else-if="s.plainCount.value && !s.seedTimes.value.length">
          <Icon icon="ph:info-fill" class="h-4 w-4 shrink-0" />
          {{ t('publish.detectedPlain', { count: s.plainCount.value }) }}
        </template>
      </p>
    </div>

    <EditorFooter>
      <template #start>
        <button class="btn-ghost press" @click="close">{{ t('common.cancel') }}</button>
      </template>
      <template v-if="blocker" #hint>{{ blocker }}</template>
      <!-- Words already in time: their timing can be fixed on its own, or
           left as it is. -->
      <button
        v-if="s.seedTimes.value.length && !s.detectedSynced.value"
        class="btn press"
        :disabled="!s.canLeaveWords.value"
        @click="s.goPhase(SYNC)"
      >
        <Icon icon="ph:clock-clockwise-bold" class="h-4 w-4" />
        {{ t('publish.fixTiming') }}
      </button>
      <button class="btn-accent press" :disabled="!s.canLeaveWords.value" @click="s.nextFromWords">
        {{ nextLabel }}
        <Icon icon="ph:arrow-right-bold" class="h-4 w-4" />
      </button>
    </EditorFooter>
  </section>
</template>

<script setup>
import { ref, computed, inject, nextTick, onMounted } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { LYRICS_EDITOR, SYNC } from '/src/model/lyrics/useLyricsSubmit'
import { repeatLines, insertPart, partLabel } from '/src/model/lyrics/repeat'
import EditorFooter from './EditorFooter.vue'
import ListenBar from './ListenBar.vue'

const { t } = useI18n()
const { s, close } = inject(LYRICS_EDITOR)
const form = s.form

const titleEl = ref(null)
const pasteEl = ref(null)

const nextLabel = computed(() => {
  const untimed = s.untimedAfterWords.value
  if (s.detectedSynced.value || untimed === 0) return t('publish.next.review')
  if (untimed > 0) return t('publish.next.timeNew', { count: untimed })
  return t('publish.next.sync')
})

// Why "Next" cannot be pressed yet, in words; a greyed-out button alone
// left people guessing. Missing words need no telling: the box says so.
const blocker = computed(() => {
  const m = s.missing.value
  if (m.details) return t('publish.needDetails')
  if (m.duration) return t('publish.needDuration')
  return ''
})

onMounted(() => {
  const el = s.missing.value.details ? titleEl.value : pasteEl.value
  el?.focus({ preventScroll: true })
})

// The part last repeated, kept to be put in again further down the song.
const part = ref('')

async function apply(result) {
  if (!result) return
  form.value.raw = result.text
  await nextTick()
  const el = pasteEl.value
  if (!el) return
  el.focus({ preventScroll: true })
  el.setSelectionRange(result.selStart, result.selEnd)
}

function repeat() {
  const el = pasteEl.value
  if (!el) return
  const result = repeatLines(form.value.raw, el.selectionStart, el.selectionEnd)
  if (result) part.value = result.part
  apply(result)
}

function putPart() {
  const el = pasteEl.value
  if (!el || !part.value) return
  apply(insertPart(form.value.raw, el.selectionEnd, part.value))
}

// Ctrl+D in the box repeats, as in a code editor; it is kept from the app,
// where it would save the song playing.
function onPasteKey(e) {
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'd') {
    e.preventDefault()
    e.stopPropagation()
    repeat()
  }
}
</script>

<style scoped>
.step-body {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
}
.words {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  padding: 16px 18px 12px;
  overflow-y: auto;
}
.songline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 44px;
  padding: 6px 6px 6px 14px;
  border-radius: 10px;
  background: rgb(var(--c-tint) / 0.05);
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.75);
}
.songline-text {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  overflow-wrap: anywhere;
}
.songline-text b {
  color: rgb(var(--c-fg));
  font-weight: 700;
}
.dot {
  opacity: 0.5;
}
.details {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
@container editor (max-width: 620px) {
  .details {
    grid-template-columns: 1fr;
  }
}
.detail {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.detail .field[aria-invalid='true'] {
  border-color: rgb(var(--c-danger) / 0.6);
}
.detail > span {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / 0.5);
}
.note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 10px;
  background: rgb(var(--c-tint) / 0.05);
  font-size: 12.5px;
  line-height: 1.5;
  color: rgb(var(--c-fg) / 0.75);
}
.note svg {
  margin-top: 1px;
}
.note.is-accent {
  background: rgb(var(--c-accent) / 0.08);
  color: rgb(var(--c-fg) / 0.85);
}
.note.is-accent svg {
  color: rgb(var(--c-accent));
}
.note-act {
  flex-shrink: 0;
  border-radius: 6px;
  font-weight: 700;
  color: rgb(var(--c-accent));
}
.note-act:hover {
  text-decoration: underline;
}
.tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.tool {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  gap: 7px;
  height: 30px;
  padding: 0 11px;
  border-radius: 999px;
  border: 1px solid rgb(var(--c-tint) / 0.12);
  background: rgb(var(--c-tint) / 0.05);
  font-size: 12.5px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.85);
  transition:
    background-color 0.12s ease,
    border-color 0.12s ease;
}
.tool:hover:not(:disabled) {
  background: rgb(var(--c-tint) / 0.1);
  border-color: rgb(var(--c-tint) / 0.2);
}
.tool:disabled {
  opacity: 0.45;
}
.tool .kbd {
  height: 18px;
}
.tools-hint {
  flex: 1 1 220px;
  min-width: 0;
  font-size: 12px;
  color: rgb(var(--c-fg) / 0.5);
}
.paste-wrap {
  display: flex;
  min-height: 180px;
  flex: 1;
}
.paste {
  width: 100%;
  resize: none;
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid rgb(var(--c-tint) / 0.1);
  background: rgb(var(--c-tint) / 0.04);
  color: rgb(var(--c-fg));
  font-size: 14px;
  line-height: 1.7;
  outline: none;
  transition:
    border-color 0.12s ease,
    background-color 0.12s ease;
}
.paste::placeholder {
  color: rgb(var(--c-fg) / 0.4);
}
.paste:hover {
  border-color: rgb(var(--c-tint) / 0.18);
}
.paste:focus {
  border-color: rgb(var(--c-accent) / 0.7);
  background: rgb(var(--c-tint) / 0.03);
}
.detected {
  display: flex;
  align-items: center;
  gap: 7px;
  min-height: 20px;
  font-size: 12.5px;
  color: rgb(var(--c-fg) / 0.6);
}
.detected.is-synced {
  color: rgb(var(--c-accent));
}
</style>
