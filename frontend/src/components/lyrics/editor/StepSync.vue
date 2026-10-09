<template>
  <!-- The step's own focus point: the keys work from anywhere in the
       editor, and a tap that lifts the focus off a button lands here. -->
  <section ref="root" class="step-body" data-sync-home tabindex="-1" :aria-label="t('publish.step.sync')">
    <div class="sync">
      <SyncTransport class="sync-transport" />
      <div class="sync-main">
        <div class="sync-side">
          <SyncTapCard />
          <SyncProgress />
        </div>
        <SyncLineList class="sync-list" />
      </div>
    </div>

    <EditorFooter>
      <template #start>
        <button class="btn-ghost press" @click="s.back">
          <Icon icon="ph:arrow-left-bold" class="h-4 w-4" />
          {{ t('publish.back') }}
        </button>
      </template>
      <template v-if="remaining > 0" #hint>{{ t('publish.needTimed', { count: remaining }) }}</template>
      <button class="btn-accent press" :disabled="!s.canReview.value" @click="s.goPhase(REVIEW)">
        {{ t('publish.next.review') }}
        <Icon icon="ph:arrow-right-bold" class="h-4 w-4" />
      </button>
    </EditorFooter>
  </section>
</template>

<script setup>
import { ref, computed, inject, onMounted } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { LYRICS_EDITOR, REVIEW } from '/src/model/lyrics/useLyricsSubmit'
import EditorFooter from './EditorFooter.vue'
import SyncTransport from './SyncTransport.vue'
import SyncTapCard from './SyncTapCard.vue'
import SyncProgress from './SyncProgress.vue'
import SyncLineList from './SyncLineList.vue'

const { t } = useI18n()
const { s } = inject(LYRICS_EDITOR)

const root = ref(null)
// How many more lines must be timed before it can be checked over.
const remaining = computed(() => Math.max(0, s.needTimed.value - s.editor.timed.value))

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
.sync {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 14px;
  padding: 14px 18px 0;
  overflow-y: auto;
}
.sync-main {
  display: grid;
  grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
  gap: 18px;
  min-height: 0;
  flex: 1;
}
.sync-side {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  padding-bottom: 14px;
  overflow-y: auto;
}
.sync-list {
  border-left: 1px solid rgb(var(--c-tint) / 0.07);
  padding-left: 12px;
}
/* One column: the card, then the lines, which keep at least a few rows'
   worth of room and scroll inside it. */
@container editor (max-width: 720px) {
  .sync {
    gap: 12px;
    padding-top: 12px;
  }
  .sync-main {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .sync-side {
    flex: none;
    gap: 10px;
    overflow: visible;
    padding-bottom: 0;
  }
  .sync-list {
    flex: 1 0 168px;
    border-left: 0;
    border-top: 1px solid rgb(var(--c-tint) / 0.07);
    padding-left: 0;
    padding-top: 6px;
  }
}
</style>
