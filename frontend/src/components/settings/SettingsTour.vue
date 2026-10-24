<template>
  <section>
    <h2 class="group-title">{{ t('tour.sectionTitle') }}</h2>
    <div class="row">
      <Icon icon="ph:compass" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('tour.sectionWelcome') }}</p>
        <p class="row-hint">{{ t('tour.sectionWelcomeHint') }}</p>
      </div>
      <button class="btn" @click="startTour('welcome')">
        <Icon icon="ph:play-fill" class="h-4 w-4" />
        {{ t('tour.start') }}
      </button>
    </div>
    <div class="row">
      <Icon icon="ph:sparkle" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('tour.sectionNew', { version: versionLabel(appVersion) }) }}</p>
        <p class="row-hint">{{ t('tour.sectionNewHint') }}</p>
      </div>
      <button class="btn" @click="startTour('new')">
        <Icon icon="ph:play-fill" class="h-4 w-4" />
        {{ t('tour.start') }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { appVersion } from '/src/model/api'
import { startTour } from '/src/model/tour'
import { versionLabel } from '/src/model/updates'

// The tours, any time: the whole of Dannify, or what this version brought.
const { t } = useI18n()
</script>
