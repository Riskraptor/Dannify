<template>
  <section>
    <h2 class="group-title">{{ t('settings.storage') }}</h2>
    <div class="row">
      <Icon icon="ph:hard-drives" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.librarySize') }}</p>
        <p class="row-hint">
          {{
            storage
              ? t('settings.librarySizeHint', {
                  songs: t('artists.trackCount', { count: storage.songs }),
                  size: formatBytes(storage.bytes),
                  free: formatBytes(storage.free),
                })
              : t('settings.librarySizeLoading')
          }}
        </p>
        <div v-if="storage && storage.free" class="usage" aria-hidden="true">
          <span class="usage-fill" :style="{ width: `${usagePct}%` }" />
        </div>
      </div>
    </div>
    <div class="row">
      <Icon icon="ph:broom" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.clearCaches') }}</p>
        <p class="row-hint">
          {{ t('settings.clearCachesHint', { size: storage ? formatBytes(storage.caches) : '…' }) }}
        </p>
      </div>
      <button class="btn" :disabled="clearing" @click="clearCaches">
        <span v-if="clearing" class="spinner h-4 w-4" />
        {{ t('settings.clearCaches') }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { inject } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { STORAGE_INFO, formatBytes } from '/src/components/settings/storageInfo'

const { t } = useI18n()
const { storage, clearing, usagePct, clearCaches } = inject(STORAGE_INFO)
</script>
