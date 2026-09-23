<template>
  <button
    v-if="stats.total > 0"
    class="icon-btn dl-ind"
    :class="{ 'is-active': route.name === 'Downloads' }"
    :title="tooltip"
    @click="router.push({ name: 'Downloads' })"
  >
    <svg v-if="stats.active > 0" class="dl-ring" viewBox="0 0 36 36" aria-hidden="true">
      <circle cx="18" cy="18" r="15" class="dl-ring-track" />
      <circle
        cx="18"
        cy="18"
        r="15"
        class="dl-ring-fill"
        :stroke-dasharray="`${ringLength} ${RING}`"
      />
    </svg>
    <Icon
      :icon="stats.failed > 0 && stats.active === 0 ? 'ph:warning' : 'ph:download-simple'"
      class="relative h-[17px] w-[17px]"
      :class="{ 'text-danger': stats.failed > 0 && stats.active === 0 }"
    />
    <span v-if="stats.active > 0" class="badge dl-badge">{{ stats.active }}</span>
  </button>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useDownloadStats } from '/src/model/downloadStats'
import { useI18n } from '/src/i18n'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const stats = useDownloadStats()

const RING = 2 * Math.PI * 15
const ringLength = computed(() => (RING * Math.max(4, stats.value.percent)) / 100)

const tooltip = computed(() => {
  const s = stats.value
  if (s.active > 0) {
    return t('downloads.tooltipActive', { active: s.active, percent: Math.round(s.percent) })
  }
  if (s.failed > 0) return t('downloads.tooltipFailed', { count: s.failed })
  return t('downloads.tooltipDone', { count: s.done })
})
</script>

<style scoped>
.dl-ind {
  position: relative;
}
.dl-ring {
  position: absolute;
  inset: 2px;
  width: calc(100% - 4px);
  height: calc(100% - 4px);
  transform: rotate(-90deg);
}
.dl-ring-track {
  fill: none;
  stroke: rgb(var(--c-tint) / 0.12);
  stroke-width: 2.5;
}
.dl-ring-fill {
  fill: none;
  stroke: rgb(var(--c-accent));
  stroke-width: 2.5;
  stroke-linecap: round;
  transition: stroke-dasharray 0.3s ease;
}
.dl-badge {
  position: absolute;
  top: -3px;
  right: -4px;
  height: 15px;
  min-width: 15px;
  font-size: 9px;
}
</style>
