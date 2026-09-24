<template>
  <!-- Downloaded and waiting: say so in words. An icon you have to discover
       is fine for "there is an update"; it is not fine for "the update is
       sitting on disk and one click applies it". -->
  <button
    v-if="updates.available.value && updates.ready.value"
    class="upd-ready press"
    :title="t('update.available', { version: updates.info.value.version })"
    @click="updates.downloadAndInstall()"
    @contextmenu.prevent="onClick"
  >
    <Icon icon="ph:arrow-clockwise-bold" class="h-[15px] w-[15px]" />
    <span>{{ t('update.restartToUpdate') }}</span>
  </button>

  <button
    v-else-if="updates.available.value"
    class="upd"
    :class="{ 'is-busy': updates.downloading.value }"
    :title="t('update.available', { version: updates.info.value.version })"
    @click="onClick"
  >
    <span v-if="updates.downloading.value" class="upd-ring" :style="ringStyle" />
    <Icon icon="ph:arrow-circle-down-fill" class="relative h-[18px] w-[18px]" />
  </button>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import { useUpdates } from '/src/model/updates'
import { openContextMenu } from '/src/model/contextMenu'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'

// A quiet dot in the title bar: it only exists when there is an update.
// Left click starts it; right click offers the notes and "skip this one".
const { t } = useI18n()
const updates = useUpdates()

const ringStyle = computed(() => ({
  background: `conic-gradient(rgb(var(--c-accent)) ${updates.progress.value * 3.6}deg, rgb(var(--c-tint) / 0.2) 0)`,
}))

function onClick(e) {
  if (updates.downloading.value) return
  openContextMenu(
    e,
    [
      {
        label: t('update.available', { version: updates.info.value.version }),
        icon: 'ph:sparkle',
        disabled: true,
      },
      { divider: true },
      {
        label: updates.ready.value ? t('update.installNow') : t('update.downloadAndInstall'),
        icon: 'ph:download-simple',
        action: () => updates.downloadAndInstall(),
      },
      { divider: true },
      { label: t('update.skip'), icon: 'ph:x', action: () => updates.skipVersion() },
    ],
    { anchor: true }
  )
}
</script>

<style scoped>
.upd {
  position: relative;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 999px;
  color: rgb(var(--c-accent));
  animation: upd-in 0.35s var(--ease-out);
}
.upd:hover {
  background: rgb(var(--c-tint) / 0.1);
}
.upd-ring {
  position: absolute;
  inset: 2px;
  border-radius: 999px;
  mask: radial-gradient(circle, transparent 60%, #000 62%);
  -webkit-mask: radial-gradient(circle, transparent 60%, #000 62%);
}
.upd-ready {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  height: 26px;
  padding: 0 11px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: -0.01em;
  white-space: nowrap;
  color: rgb(var(--c-bg));
  background: rgb(var(--c-accent));
  animation:
    upd-in 0.35s var(--ease-out),
    upd-breathe 2.6s ease-in-out 0.4s infinite;
}
.upd-ready:hover {
  filter: brightness(1.08);
}
@keyframes upd-in {
  from {
    opacity: 0;
    transform: scale(0.6);
  }
}
/* A slow pulse: noticeable when you look at the title bar, ignorable when
   you are doing something else. */
@keyframes upd-breathe {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgb(var(--c-accent) / 0.45);
  }
  60% {
    box-shadow: 0 0 0 6px rgb(var(--c-accent) / 0);
  }
}
</style>
