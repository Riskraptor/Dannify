<template>
  <section class="step-body">
    <div class="words">
      <!-- The song in one line. Its details are opened only to correct
           them: boxes of what is already right were the first thing a
           newcomer had to read. -->
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
        <button
          v-if="!s.missing.value.details"
          class="btn-ghost btn-pill press"
          :aria-expanded="s.showDetails.value ? 'true' : 'false'"
          @click="s.detailsOpen.value = !s.detailsOpen.value"
        >
          <Icon :icon="s.showDetails.value ? 'ph:caret-up-bold' : 'ph:pencil-simple-bold'" class="h-3.5 w-3.5" />
          {{ s.showDetails.value ? t('publish.detailsDone') : t('publish.editDetails') }}
        </button>
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

      <p v-if="s.restored.value" class="note">
        <Icon icon="ph:clock-counter-clockwise-bold" class="h-4 w-4 shrink-0" />
        <span class="flex-1">{{ t('publish.restored') }}</span>
        <button class="note-act" @click="s.startOver">{{ t('publish.startOver') }}</button>
      </p>
      <p v-if="s.seedTimes.value.length && !s.detectedSynced.value" class="note is-accent">
        <Icon icon="ph:clock-clockwise-bold" class="h-4 w-4 shrink-0" />
        <span>{{ t('publish.keepsTiming') }}</span>
      </p>

      <label class="paste-wrap">
        <span class="sr-only">{{ t('publish.pastePlaceholder') }}</span>
        <textarea
          ref="pasteEl"
          v-model="form.raw"
          class="paste"
          dir="auto"
          :placeholder="t('publish.pastePlaceholder')"
          spellcheck="false"
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
import { ref, computed, inject, onMounted } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { LYRICS_EDITOR, SYNC } from '/src/model/lyrics/useLyricsSubmit'
import EditorFooter from './EditorFooter.vue'

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
