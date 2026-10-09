<template>
  <section ref="root" class="step-body" tabindex="-1" :aria-label="t('publish.step.review')">
    <div class="review">
      <!-- Done: said first and plainly, with what happens next. -->
      <div v-if="s.status.value === 'done'" class="banner is-ok" role="status">
        <Icon icon="ph:check-circle-fill" class="h-6 w-6 shrink-0" />
        <div>
          <p class="banner-title">{{ t('publish.doneTitle') }}</p>
          <p class="banner-text">{{ t('publish.success') }}</p>
        </div>
      </div>

      <div class="stats">
        <div class="stat">
          <span class="stat-num">{{ s.editor.timed.value }}</span>
          <span class="stat-label">{{ t('publish.linesStamped') }}</span>
        </div>
        <div class="stat">
          <span class="stat-num">{{ s.editor.lines.value.length }}</span>
          <span class="stat-label">{{ t('publish.linesTotal') }}</span>
        </div>
        <div class="stat">
          <span class="stat-num is-word">{{ s.syncedOutput.value ? t('publish.inTime') : t('publish.wordsOnly') }}</span>
          <span class="stat-label">{{ t('publish.timing') }}</span>
        </div>
      </div>

      <!-- What people will see, as they will see it: not the file format
           with its [00:10.53] on every line. -->
      <div class="preview-wrap">
        <p class="eyebrow">{{ t('publish.previewTitle') }}</p>
        <ol class="preview">
          <li v-for="(ln, i) in s.previewLines.value" :key="i" :class="{ brk: !ln.text }">
            <span v-if="ln.time != null" class="pv-time" data-time>{{ formatShort(ln.time) }}</span>
            <span class="pv-text" dir="auto">{{ ln.text || '♪' }}</span>
          </li>
        </ol>
      </div>

      <!-- Lines out of order would be published in the wrong order: they
           are put right first. -->
      <div v-if="s.blockedByOrder.value" class="banner is-error">
        <Icon icon="ph:warning-fill" class="h-5 w-5 shrink-0" />
        <p class="banner-text flex-1">{{ t('publish.outOfOrder', { count: s.editor.issues.value.length }) }}</p>
        <button class="btn btn-pill press" @click="s.fixOrder">{{ t('publish.fixTiming') }}</button>
      </div>

      <div v-else-if="offline && s.status.value !== 'done'" class="banner is-warn" role="status">
        <Icon icon="ph:wifi-slash" class="h-5 w-5 shrink-0" />
        <p class="banner-text">{{ t('publish.offline') }}</p>
      </div>

      <div v-if="s.status.value === 'sending'" class="banner is-busy" role="status">
        <span class="spinner h-5 w-5 shrink-0 text-accent"></span>
        <div class="min-w-0 flex-1">
          <p class="banner-title">{{ t('publish.solving') }}</p>
          <p class="banner-text">{{ t('publish.powSlow') }}</p>
          <div class="progress-track is-indeterminate mt-2"><div class="progress-fill" /></div>
        </div>
      </div>

      <div v-else-if="s.status.value === 'failed'" class="banner is-error" role="alert">
        <Icon icon="ph:warning-circle-fill" class="h-5 w-5 shrink-0" />
        <p class="banner-text">{{ failureText }}</p>
      </div>
    </div>

    <EditorFooter>
      <template #start>
        <button
          class="btn-ghost press"
          :disabled="s.status.value === 'sending' || s.status.value === 'done'"
          @click="s.back"
        >
          <Icon icon="ph:arrow-left-bold" class="h-4 w-4" />
          {{ t('publish.back') }}
        </button>
      </template>
      <button v-if="s.status.value === 'done'" ref="primary" class="btn-accent press" @click="close">
        <Icon icon="ph:check-bold" class="h-4 w-4" />
        {{ t('common.close') }}
      </button>
      <button v-else ref="primary" class="btn-accent press" :disabled="!s.canSubmit.value || offline" @click="onSubmit">
        <Icon icon="ph:paper-plane-tilt-fill" class="h-4 w-4" />
        {{ s.status.value === 'failed' ? t('publish.retry') : t('publish.submit') }}
      </button>
    </EditorFooter>
  </section>
</template>

<script setup>
import { ref, computed, inject, nextTick, onMounted } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { useConnectivity } from '/src/model/connectivity'
import { LYRICS_EDITOR } from '/src/model/lyrics/useLyricsSubmit'
import { formatShort } from '/src/model/lyrics/lrc'
import EditorFooter from './EditorFooter.vue'

const { t } = useI18n()
const { s, close } = inject(LYRICS_EDITOR)
const { isOffline } = useConnectivity()

const root = ref(null)
const primary = ref(null)
const offline = computed(() => isOffline.value)

// Each way it can fail, said in the user's language. The catalogue's own
// reason, when it gave one, is more use than anything general.
const failureText = computed(() => {
  const f = s.failure.value
  if (!f) return ''
  if (f.reason === 'offline') return t('publish.offline')
  if (f.reason === 'timeout') return t('publish.timeout')
  if (f.reason === 'rejected' && f.error) return f.error
  return t('publish.failed')
})

async function onSubmit() {
  await s.submit()
  // The button changed (Close, or Try again): the focus goes with it.
  nextTick(() => primary.value?.focus({ preventScroll: true }))
}

onMounted(() => root.value?.focus({ preventScroll: true }))
</script>

<style scoped>
.step-body {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  outline: none;
}
.review {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 14px;
  padding: 16px 18px;
  overflow-y: auto;
}
.stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgb(var(--c-tint) / 0.05);
}
.stat-num {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
}
.stat-num.is-word {
  font-size: 18px;
  line-height: 1.6;
}
.stat-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / 0.5);
}
.preview-wrap {
  display: flex;
  min-height: 160px;
  flex: 1;
  flex-direction: column;
  gap: 8px;
}
.preview {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: 10px 6px;
  overflow-y: auto;
  list-style: none;
  border-radius: 12px;
  background: rgb(var(--c-tint) / 0.04);
}
.preview li {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 4px 12px;
  font-size: 14px;
  line-height: 1.5;
  color: rgb(var(--c-fg) / 0.9);
}
.preview li.brk {
  color: rgb(var(--c-fg) / 0.4);
}
.pv-time {
  flex-shrink: 0;
  min-width: 2.6rem;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.4);
}
.pv-text {
  min-width: 0;
  flex: 1;
  overflow-wrap: anywhere;
  text-align: start;
}
.banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.5;
}
.banner-title {
  font-weight: 700;
}
.banner-text {
  color: rgb(var(--c-fg) / 0.8);
}
.banner.is-ok {
  background: rgb(var(--c-accent) / 0.12);
  border: 1px solid rgb(var(--c-accent) / 0.3);
}
.banner.is-ok svg {
  color: rgb(var(--c-accent));
}
.banner.is-error {
  background: rgb(var(--c-danger) / 0.1);
  border: 1px solid rgb(var(--c-danger) / 0.3);
}
.banner.is-error svg {
  color: rgb(var(--c-danger));
}
.banner.is-warn {
  background: rgb(var(--c-warn) / 0.1);
  border: 1px solid rgb(var(--c-warn) / 0.3);
}
.banner.is-warn svg {
  color: rgb(var(--c-warn));
}
.banner.is-busy {
  background: rgb(var(--c-tint) / 0.05);
}
@container editor (max-width: 520px) {
  .stat {
    padding: 10px;
  }
  .stat-num {
    font-size: 20px;
  }
  .stat-num.is-word {
    font-size: 14px;
  }
}
</style>
