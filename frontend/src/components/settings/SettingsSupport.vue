<template>
  <section>
    <h2 class="group-title">{{ t('support.title') }}</h2>
    <div class="row">
      <Icon icon="ph:coffee" class="row-icon text-accent" />
      <div class="row-text">
        <p class="row-label">{{ t('support.heading') }}</p>
        <p class="row-hint">{{ support.message || t('support.blurb') }}</p>
      </div>
      <button class="btn-accent btn-pill press shrink-0 px-4" @click="donate()">
        <Icon icon="ph:coffee" class="h-4 w-4" />
        {{ t('support.give') }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import { useSupport } from '/src/model/support'
import { useI18n } from '/src/i18n'

// One link: see support.py and model/support.js.
const { t } = useI18n()
const { config: support, openSupport: donate } = useSupport()
</script>
