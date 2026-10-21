<template>
  <section>
    <h2 class="group-title">{{ t('settings.language') }}</h2>
    <div class="row">
      <Icon icon="ph:translate" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.language') }}</p>
        <p class="row-hint">{{ t('settings.languageHint') }}</p>
      </div>
      <select class="field-select w-48" :value="choice" :aria-label="t('settings.language')" @change="setLocale($event.target.value)">
        <option value="auto">{{ t('settings.languageAuto', { language: systemName }) }}</option>
        <option v-for="l in locales" :key="l.code" :value="l.code">{{ l.name }}</option>
      </select>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'

// The language, first thing in General: it is about the whole app, not about
// how it looks.
const { t, choice, setLocale, locales, systemLocale } = useI18n()
// Each language under its own name, so whoever cannot read the one on screen
// still finds theirs.
const systemName = computed(() => locales.find((l) => l.code === systemLocale())?.name || 'English')
</script>
