<template>
  <button
    v-if="round.running"
    class="icon-btn fix-ind"
    :title="tooltip"
    :aria-label="tooltip"
    @click="openMenu"
  >
    <svg class="fix-ring" viewBox="0 0 36 36" aria-hidden="true">
      <circle cx="18" cy="18" r="15" class="fix-ring-track" />
      <circle
        cx="18"
        cy="18"
        r="15"
        class="fix-ring-fill"
        :stroke-dasharray="`${ringLength} ${RING}`"
      />
    </svg>
    <Icon icon="ph:wrench" class="relative h-[16px] w-[16px]" />
    <span class="badge fix-badge">{{ remaining }}</span>
  </button>
</template>

<script setup>
/**
 * A repair in progress, shown the way a download is: a ring in the title bar.
 *
 * It used to be a red box across the top of whatever page was open, the Now
 * Playing screen included, repeating the problem it was in the middle of
 * fixing next to a count that disagreed with it. A repair is background work
 * like any download, so it sits where downloads sit, and it stays out of the
 * way of the music.
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useRepair } from '/src/model/repair'
import { openContextMenu } from '/src/model/contextMenu'
import { useI18n } from '/src/i18n'

const { t } = useI18n()
const router = useRouter()
const repair = useRepair()
const round = computed(() => repair.status.value)

const RING = 2 * Math.PI * 15
const percent = computed(() => {
  const r = round.value
  const total = r.total || 1
  const working = Object.values(r.items || {}).filter((i) => i.state === 'working')
  const partial = working.reduce((sum, i) => sum + (i.progress || 0) / 100, 0)
  return Math.min(100, ((r.done + partial) / total) * 100)
})
const ringLength = computed(() => (RING * Math.max(4, percent.value)) / 100)
const remaining = computed(() => Math.max(0, round.value.total - round.value.done))
const place = computed(() => Math.min(round.value.done + 1, round.value.total))
const tooltip = computed(() =>
  t('repair.indicator', { done: place.value, total: round.value.total })
)

function openMenu(e) {
  openContextMenu(
    e,
    [
      { header: tooltip.value },
      {
        label: t('repair.show'),
        icon: 'ph:music-notes',
        action: () => router.push({ name: 'Library' }),
      },
      { divider: true },
      {
        label: t('repair.stop'),
        icon: 'ph:stop-circle',
        danger: true,
        action: () => repair.stopRepairs(),
      },
    ],
    { anchor: true }
  )
}
</script>

<style scoped>
.fix-ind {
  position: relative;
}
.fix-ring {
  position: absolute;
  inset: 2px;
  width: calc(100% - 4px);
  height: calc(100% - 4px);
  transform: rotate(-90deg);
}
.fix-ring-track {
  fill: none;
  stroke: rgb(var(--c-tint) / 0.12);
  stroke-width: 2.5;
}
.fix-ring-fill {
  fill: none;
  stroke: rgb(var(--c-accent));
  stroke-width: 2.5;
  stroke-linecap: round;
  transition: stroke-dasharray 0.3s ease;
}
.fix-badge {
  position: absolute;
  top: -3px;
  right: -4px;
  height: 15px;
  min-width: 15px;
  font-size: 9px;
}
</style>
