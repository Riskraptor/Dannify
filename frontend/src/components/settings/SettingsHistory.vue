<template>
  <section>
    <h2 class="group-title">{{ t('settings.historyGroup') }}</h2>
    <label class="row">
      <Icon icon="ph:chart-bar" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.listenHistory') }}</p>
        <p class="row-hint">{{ t('settings.listenHistoryHint') }}</p>
      </div>
      <input
        type="checkbox"
        class="switch"
        :checked="listens.keeping.value"
        @change="listens.setKeeping($event.target.checked)"
      />
    </label>
    <div class="row">
      <Icon icon="ph:clock-counter-clockwise" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('history.clear') }}</p>
        <p class="row-hint">{{ t('settings.clearHistoryHint') }}</p>
      </div>
      <button class="btn" :disabled="clearing" @click="clearAll">
        <span v-if="clearing" class="spinner h-4 w-4" />
        {{ t('history.clear') }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { Icon } from '@iconify/vue'
import { useListens } from '/src/model/listens'
import { confirmDialog } from '/src/model/dialog'
import { toast } from '/src/model/toast'
import { useI18n } from '/src/i18n'

// What the app remembers of what was played (History and Stats): whether it
// does at all, and a way to make it forget.
const { t } = useI18n()
const listens = useListens()
const clearing = ref(false)

async function clearAll() {
  const ok = await confirmDialog({
    title: t('history.clearTitle'),
    message: t('history.clearText'),
    confirmText: t('history.clear'),
    danger: true,
    icon: 'ph:trash',
  })
  if (!ok) return
  clearing.value = true
  try {
    await listens.clearListens()
    toast(t('history.cleared'), { icon: 'ph:trash' })
  } catch {
    toast(t('history.clearFailed'), { tone: 'error' })
  } finally {
    clearing.value = false
  }
}
</script>

