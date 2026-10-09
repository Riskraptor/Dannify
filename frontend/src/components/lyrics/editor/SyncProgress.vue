<template>
  <div class="progress">
    <!-- How it is done, until the first line is timed. -->
    <ol v-if="!timed" class="howto">
      <li><b>1</b>{{ t('publish.howto1') }}</li>
      <li><b>2</b>{{ t('publish.howto2') }}</li>
      <li><b>3</b>{{ t('publish.howto3') }}</li>
    </ol>

    <!-- How far along, then what is wrong. "Partially timed" never
         answered the question the user is actually asking. -->
    <template v-else>
      <div class="head">
        <span class="count">{{ t('publish.timedOf', { done: timed, total }) }}</span>
        <span v-if="state !== 'partial'" class="state" :class="state">{{ stateText }}</span>
      </div>
      <div class="progress-track" role="progressbar" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100">
        <div class="progress-fill" :class="state" :style="{ width: percent + '%' }" />
      </div>
      <button v-if="issues" class="btn btn-pill press fix" @click="session.jumpToIssue()">
        <Icon icon="ph:warning-fill" class="h-3.5 w-3.5" />
        {{ t('publish.fixIssues') }}
      </button>
    </template>
  </div>
</template>

<script setup>
import { computed, inject } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { LYRICS_EDITOR } from '/src/model/lyrics/useLyricsSubmit'

const { t } = useI18n()
const { s, session } = inject(LYRICS_EDITOR)
const editor = s.editor

const timed = computed(() => editor.timed.value)
const total = computed(() => editor.lines.value.length)
const issues = computed(() => editor.issues.value.length)
const percent = computed(() => (total.value ? Math.round((timed.value / total.value) * 100) : 0))
const state = computed(() => {
  if (issues.value) return 'err'
  if (timed.value < total.value) return 'partial'
  return 'ok'
})
const stateText = computed(() =>
  state.value === 'err' ? t('publish.issuesCount', { count: issues.value }) : t('publish.allTimed')
)
</script>

<style scoped>
.progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.howto {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.howto li {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 8px 10px;
  border-radius: 9px;
  background: rgb(var(--c-tint) / 0.05);
  font-size: 12.5px;
  line-height: 1.45;
  color: rgb(var(--c-fg) / 0.8);
}
.howto b {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgb(var(--c-accent) / 0.18);
  color: rgb(var(--c-accent));
  font-size: 11px;
}
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 4px 10px;
  font-size: 12.5px;
}
.count {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.state {
  font-weight: 600;
}
.state.ok {
  color: rgb(var(--c-accent));
}
.state.err {
  color: rgb(var(--c-danger));
}
.progress-fill.err {
  background: rgb(var(--c-danger));
}
.fix {
  align-self: flex-start;
  color: rgb(var(--c-danger));
}
</style>
