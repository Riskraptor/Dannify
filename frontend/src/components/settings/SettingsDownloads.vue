<template>
  <section>
    <h2 class="group-title">{{ t('settings.downloadsSection') }}</h2>
    <div class="row">
      <Icon icon="ph:stack" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.parallelDownloads') }}</p>
        <p class="row-hint">{{ t('settings.parallelDownloadsHint') }}</p>
      </div>
      <div class="seg">
        <button
          v-for="n in sm.settingsOptions.max_parallel_downloads"
          :key="n"
          class="seg-item min-w-[36px] justify-center"
          :class="{ 'is-active': s.max_parallel_downloads === n }"
          @click="sm.update({ max_parallel_downloads: n })"
        >
          {{ n }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import { useSettingsManager } from '/src/model/settings'
import { useI18n } from '/src/i18n'

const { t } = useI18n()
const sm = useSettingsManager()
const s = computed(() => sm.settings.value)
</script>
