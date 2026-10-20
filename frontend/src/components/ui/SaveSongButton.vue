<template>
  <!-- Saving one song, with every state it can be in: not saved, on its way
       (a ring filling as it downloads, turning while it starts), saved, or
       failed and ready to try again. A plain arrow showed nothing between the
       press and the end, so people pressed it again and again. -->
  <button
    class="icon-btn is-round press save-song"
    :class="[`is-${state}`, { 'is-active': state === 'saved' }]"
    :disabled="state === 'saved' || state === 'saving' || !row"
    :title="label"
    :aria-label="label"
    :aria-busy="state === 'saving' ? 'true' : undefined"
    @click="save"
  >
    <svg v-if="state === 'saving'" class="ss-ring" :class="{ 'is-waiting': !progress }" viewBox="0 0 36 36" aria-hidden="true">
      <circle cx="18" cy="18" r="15" class="ss-track" />
      <circle cx="18" cy="18" r="15" class="ss-fill" :stroke-dasharray="dash" />
    </svg>
    <Icon :icon="icon" :class="iconClass" />
  </button>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { useLibraryIndex } from '/src/model/libraryIndex'
import { useProgressTracker } from '/src/model/download'
import { isRowDownloaded, downloadRows } from '/src/model/tracks'

const props = defineProps({
  // The song, as a queue row (model/tracks.js queueRow).
  row: { type: Object, default: null },
  iconClass: { type: String, default: 'h-[18px] w-[18px]' },
})

const { t } = useI18n()
const libIndex = useLibraryIndex()
const tracker = useProgressTracker()
const RING = 2 * Math.PI * 15

const item = computed(() => {
  const r = props.row
  return r && r.kind === 'song' && r.raw ? tracker.getBySong(r.raw) : null
})
const state = computed(() => {
  // Read so this follows the library as downloads land.
  void libIndex.byVideoId.value
  if (props.row && isRowDownloaded(props.row)) return 'saved'
  const it = item.value
  if (it && it.isPending()) return 'saving'
  if (it && it.isErrored()) return 'failed'
  return 'idle'
})
const progress = computed(() => Math.max(0, Math.min(100, Number(item.value?.progress) || 0)))
const dash = computed(() => `${((progress.value || 22) / 100) * RING} ${RING}`)

const icon = computed(
  () =>
    ({
      saved: 'ph:arrow-circle-down-fill',
      saving: 'ph:arrow-down-bold',
      failed: 'ph:arrow-clockwise-bold',
      idle: 'ph:arrow-circle-down',
    })[state.value]
)
const label = computed(() => {
  if (state.value === 'saved') return t('player.inLibrary')
  if (state.value === 'saving')
    return progress.value ? t('player.savingPercent', { percent: Math.round(progress.value) }) : t('player.saving')
  if (state.value === 'failed') return t('downloads.failedRetry')
  return t('player.saveToLibrary')
})

function save() {
  if (props.row && (state.value === 'idle' || state.value === 'failed')) downloadRows([props.row])
}
</script>

<style scoped>
.save-song {
  position: relative;
}
.save-song.is-saving {
  color: rgb(var(--c-accent));
  opacity: 1;
}
.save-song.is-failed {
  color: rgb(var(--c-danger, 239 68 68));
}
.ss-ring {
  position: absolute;
  inset: 3px;
  width: calc(100% - 6px);
  height: calc(100% - 6px);
  transform: rotate(-90deg);
}
.ss-ring.is-waiting {
  animation: ss-turn 0.9s linear infinite;
}
.ss-track {
  fill: none;
  stroke: rgb(var(--c-tint) / 0.14);
  stroke-width: 2.6;
}
.ss-fill {
  fill: none;
  stroke: rgb(var(--c-accent));
  stroke-width: 2.6;
  stroke-linecap: round;
  transition: stroke-dasharray 0.3s ease;
}
.save-song.is-saving :deep(svg:not(.ss-ring)) {
  transform: scale(0.62);
}
@keyframes ss-turn {
  from {
    transform: rotate(-90deg);
  }
  to {
    transform: rotate(270deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .ss-ring.is-waiting {
    animation: none;
  }
}
</style>
