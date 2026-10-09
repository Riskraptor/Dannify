<template>
  <section>
    <h2 class="group-title">{{ t('settings.librarySection') }}</h2>
    <div class="row">
      <Icon icon="ph:folder" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.libraryLocation') }}</p>
        <p class="row-hint selectable truncate font-mono text-[12px]" :title="s.download_dir">
          {{ s.download_dir || t('settings.notSet') }}
        </p>
      </div>
      <div class="flex shrink-0 gap-2">
        <button v-if="desktop.isDesktop" class="btn" @click="desktop.openLibraryFolder()">
          <Icon icon="ph:folder-open" class="h-4 w-4" />
          {{ t('settings.openFolder') }}
        </button>
        <button class="btn" @click="changeFolder">{{ t('settings.change') }}</button>
      </div>
    </div>
    <label class="row">
      <Icon icon="ph:users-three" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.organizeByArtist') }}</p>
        <p class="row-hint">{{ t('settings.organizeByArtistHint') }}</p>
      </div>
      <input
        type="checkbox"
        class="switch"
        :checked="!!s.organize_by_artist"
        @change="sm.update({ organize_by_artist: $event.target.checked })"
      />
    </label>
  </section>
</template>

<script setup>
import { computed, inject } from 'vue'
import { Icon } from '@iconify/vue'
import { useSettingsManager } from '/src/model/settings'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'
import { STORAGE_INFO } from '/src/components/settings/storageInfo'

const { t } = useI18n()
const sm = useSettingsManager()
const s = computed(() => sm.settings.value)
const storageInfo = inject(STORAGE_INFO)

async function changeFolder() {
  const path = await sm.pickDownloadFolder()
  // The new folder is written right there in the row.
  if (path) storageInfo.remeasure()
}
</script>
