<template>
  <nav class="steps-wrap" :aria-label="t('publish.contributeTo')">
    <!-- Numbered beads on a rail. Each step says what it is for, because
         "Paste / Sync / Review" on its own tells a first-time contributor
         nothing. Steps already passed can be gone back to. -->
    <ol class="steps">
      <li
        v-for="(label, idx) in labels"
        :key="idx"
        class="step"
        :class="{ active: phase === idx, done: phase > idx }"
      >
        <button
          class="step-btn"
          :disabled="!canGoTo(idx)"
          :aria-current="phase === idx ? 'step' : undefined"
          :title="canGoTo(idx) ? t('publish.goToStep') : undefined"
          @click="s.goPhase(idx)"
        >
          <span class="bead">
            <Icon v-if="phase > idx" icon="ph:check-bold" class="h-3 w-3" />
            <template v-else>{{ idx + 1 }}</template>
          </span>
          <span class="step-label">{{ label }}</span>
        </button>
      </li>
    </ol>
    <p class="why">
      <Icon icon="ph:info" class="h-3.5 w-3.5 shrink-0" />
      <span>{{ why }}</span>
    </p>
  </nav>
</template>

<script setup>
import { computed, inject } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { LYRICS_EDITOR } from '/src/model/lyrics/useLyricsSubmit'

const { t } = useI18n()
const { s } = inject(LYRICS_EDITOR)

const phase = computed(() => s.phase.value)
const labels = computed(() => [t('publish.step.paste'), t('publish.step.sync'), t('publish.step.review')])

// What the current step is actually for, read once where the user already
// is rather than hidden behind a tooltip.
const why = computed(
  () =>
    [
      s.seedTimes.value.length ? t('publish.stepWhy.fix') : t('publish.stepWhy.paste'),
      t('publish.stepWhy.sync'),
      t('publish.stepWhy.review'),
    ][phase.value] || ''
)

// Back to any earlier step, unless publishing has started or finished.
function canGoTo(idx) {
  return idx < phase.value && s.status.value !== 'sending' && s.status.value !== 'done'
}
</script>

<style scoped>
.steps-wrap {
  padding: 0 18px 12px;
  border-bottom: 1px solid rgb(var(--c-tint) / 0.07);
}
.steps {
  display: flex;
  align-items: center;
  margin: 0;
  padding: 0;
  list-style: none;
}
.step {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
}
.step:last-child {
  flex: 0 0 auto;
}
/* The connector runs from this bead to the next one. */
.step:not(:last-child)::after {
  content: '';
  flex: 1;
  min-width: 16px;
  height: 2px;
  margin: 0 10px;
  border-radius: 2px;
  background: rgb(var(--c-tint) / 0.12);
  transition: background-color 0.3s ease;
}
.step.done::after {
  background: rgb(var(--c-accent) / 0.55);
}
.step-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 4px 6px 4px 2px;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.45);
  transition: color 0.2s ease, background-color 0.12s ease;
}
.step-btn:not(:disabled):hover {
  background: rgb(var(--c-tint) / 0.06);
  color: rgb(var(--c-fg));
}
.step.active .step-btn,
.step.done .step-btn {
  color: rgb(var(--c-fg));
}
.bead {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.1);
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  transition:
    background-color 0.2s ease,
    color 0.2s ease,
    box-shadow 0.2s ease;
}
.step.active .bead {
  background: rgb(var(--c-accent));
  color: rgb(var(--c-accent-fg));
  box-shadow: 0 0 0 4px rgb(var(--c-accent) / 0.16);
}
.step.done .bead {
  background: rgb(var(--c-accent) / 0.22);
  color: rgb(var(--c-accent));
}
.step-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.why {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin-top: 10px;
  font-size: 12.5px;
  line-height: 1.5;
  color: rgb(var(--c-fg) / 0.62);
}
.why svg {
  margin-top: 2px;
  color: rgb(var(--c-fg) / 0.4);
}
/* A short window keeps its height for the work itself. */
@media (max-height: 640px) {
  .why {
    display: none;
  }
}
/* Narrow: only the current step keeps its name. */
@container editor (max-width: 560px) {
  .step:not(.active) .step-label {
    display: none;
  }
}
</style>
