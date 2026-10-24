<template>
  <!-- Offline, said calmly and with somewhere to go: the saved music is all
       there, and what needs the internet comes back by itself. -->
  <section class="off-card" :class="{ 'is-compact': compact }" role="status">
    <span class="off-icon" aria-hidden="true">
      <Icon icon="ph:wifi-slash" class="h-6 w-6" />
    </span>
    <div class="off-body">
      <h2 class="off-title">{{ title || t('net.offlineTitle') }}</h2>
      <p class="off-text">{{ text || t('net.offlinePage') }}</p>
      <div class="off-actions">
        <button v-if="saved.length" class="btn-accent btn-pill off-btn" @click="shuffleRows(saved)">
          <Icon icon="ph:shuffle-bold" class="h-4 w-4" />
          {{ t('net.shuffleSaved') }}
        </button>
        <button class="btn btn-pill off-btn" @click="router.push({ name: 'Library' })">
          <Icon icon="ph:music-notes" class="h-4 w-4" />
          {{ t('net.openSaved') }}
        </button>
        <button class="btn-ghost btn-pill off-btn" :disabled="asked" @click="check">
          <span v-if="asked" class="spinner h-3.5 w-3.5" />
          <Icon v-else icon="ph:arrows-clockwise" class="h-4 w-4" />
          {{ asked ? t('net.checking') : t('net.checkAgain') }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { useConnectivity } from '/src/model/connectivity'
import { useLibrary } from '/src/model/library'
import { localRow, shuffleRows } from '/src/model/tracks'

defineProps({
  title: { type: String, default: '' },
  text: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})

const { t } = useI18n()
const router = useRouter()
const { probe } = useConnectivity()
// Only a look asked for here says "Checking": the app's own quiet ones
// would make the button flicker.
const asked = ref(false)
async function check() {
  asked.value = true
  try {
    await probe()
  } finally {
    asked.value = false
  }
}
const lib = useLibrary()
const saved = computed(() => (lib.tracks.value || []).map(localRow))
</script>

<style scoped>
.off-card {
  display: flex;
  align-items: flex-start;
  gap: 18px;
  max-width: 720px;
  margin: 8px auto;
  padding: 22px 24px;
  border-radius: 18px;
  background: rgb(var(--c-tint) / 0.05);
  box-shadow: inset 0 0 0 1px rgb(var(--c-tint) / 0.08);
}
.off-card.is-compact {
  max-width: none;
  margin: 8px 0;
  padding: 16px 18px;
}
.off-icon {
  display: grid;
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.08);
  color: rgb(var(--c-fg) / 0.7);
}
.off-body {
  min-width: 0;
}
.off-title {
  font-size: 17px;
  font-weight: 750;
  letter-spacing: -0.01em;
}
.off-text {
  margin-top: 4px;
  max-width: 62ch;
  font-size: 13.5px;
  line-height: 1.5;
  color: rgb(var(--c-fg) / var(--fg-62, 0.65));
}
.off-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}
.off-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 14px;
  font-size: 13px;
}
@container (max-width: 520px) {
  .off-card {
    flex-direction: column;
  }
}
</style>
