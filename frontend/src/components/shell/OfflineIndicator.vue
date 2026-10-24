<template>
  <!-- Offline, where it can be seen from every page, and calmly: a pill, not
       a red bar. A click looks again at once. -->
  <Transition name="soft">
    <button
      v-if="isOffline"
      class="off-pill press"
      :title="t('net.offlinePillHint')"
      :aria-label="t('net.offlinePillHint')"
      :disabled="asked"
      @click="check"
    >
      <span v-if="asked" class="spinner h-3 w-3" />
      <Icon v-else icon="ph:wifi-slash" class="h-3.5 w-3.5" />
      <span class="off-pill-text">{{ asked ? t('net.checking') : t('net.offlinePill') }}</span>
    </button>
  </Transition>
</template>

<script setup>
import { ref } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { useConnectivity } from '/src/model/connectivity'

const { t } = useI18n()
const { isOffline, probe } = useConnectivity()
// "Checking" only for a look the person asked for: the quiet ones the app
// takes by itself every few seconds would make the pill flicker.
const asked = ref(false)
async function check() {
  asked.value = true
  try {
    await probe()
  } finally {
    asked.value = false
  }
}
</script>

<style scoped>
.off-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  margin-right: 4px;
  padding: 0 11px;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.08);
  box-shadow: inset 0 0 0 1px rgb(var(--c-tint) / 0.12);
  color: rgb(var(--c-fg) / 0.78);
  font-size: 12px;
  font-weight: 650;
  white-space: nowrap;
  -webkit-app-region: no-drag;
}
.off-pill:hover:not(:disabled) {
  background: rgb(var(--c-tint) / 0.12);
  color: rgb(var(--c-fg));
}
@media (max-width: 640px) {
  .off-pill-text {
    display: none;
  }
}
</style>
