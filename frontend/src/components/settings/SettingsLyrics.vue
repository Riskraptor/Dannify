<template>
  <section>
    <h2 class="group-title">{{ t('settings.lyricsGroup') }}</h2>
    <label class="row">
      <Icon icon="ph:text-align-left" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.downloadLyrics') }}</p>
        <p class="row-hint">{{ t('settings.downloadLyricsHint') }}</p>
      </div>
      <input
        type="checkbox"
        class="switch"
        :checked="!!s.download_lyrics"
        @change="sm.update({ download_lyrics: $event.target.checked })"
      />
    </label>
    <div class="row">
      <Icon icon="ph:folders" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.lyricsStorage') }}</p>
        <p class="row-hint">
          {{ s.lyrics_storage === 'central' ? t('settings.lyricsCentralHint') : t('settings.lyricsSidecarHint') }}
        </p>
      </div>
      <div class="seg">
        <button
          class="seg-item"
          :class="{ 'is-active': s.lyrics_storage !== 'central' }"
          @click="sm.setLyricsStorage('sidecar')"
        >
          {{ t('settings.lyricsSidecar') }}
        </button>
        <button
          class="seg-item"
          :class="{ 'is-active': s.lyrics_storage === 'central' }"
          @click="sm.setLyricsStorage('central')"
        >
          {{ t('settings.lyricsCentral') }}
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
