<template>
  <section>
    <h2 class="group-title">{{ tp('settings.windowsSection') }}</h2>
    <label class="row">
      <Icon icon="ph:tray" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.closeToTray') }}</p>
        <p class="row-hint">{{ tp('settings.closeToTrayHint') }}</p>
      </div>
      <input
        type="checkbox"
        class="switch"
        :checked="tray.closeToTray"
        @change="setTray({ closeToTray: $event.target.checked })"
      />
    </label>
    <label v-if="desktop.state.autostart && desktop.state.autostart.available" class="row">
      <Icon icon="ph:power" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ tp('settings.autostart') }}</p>
        <p class="row-hint">{{ t('settings.autostartHint') }}</p>
      </div>
      <input
        type="checkbox"
        class="switch"
        :checked="desktop.state.autostart.on"
        @change="desktop.setAutostart($event.target.checked)"
      />
    </label>
    <label class="row">
      <Icon icon="ph:keyboard" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.globalHotkeys') }}</p>
        <p class="row-hint">{{ t('settings.globalHotkeysHint') }}</p>
        <p v-if="desktop.state.globalHotkeys && desktop.state.hotkeysTaken.length" class="row-hint text-danger">
          {{ t('settings.hotkeysTaken', { keys: desktop.state.hotkeysTaken.join(', ') }) }}
        </p>
      </div>
      <input
        type="checkbox"
        class="switch"
        :checked="desktop.state.globalHotkeys"
        @change="desktop.setGlobalHotkeys($event.target.checked)"
      />
    </label>
  </section>
</template>

<script setup>
import { reactive, onMounted } from 'vue'
import { Icon } from '@iconify/vue'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'
import { tp } from '/src/i18n/platform'

const { t } = useI18n()

// Tray behaviour lives in the native shell's config.
const tray = reactive({ closeToTray: false })

onMounted(async () => {
  if (!desktop.isDesktop) return
  await desktop.whenReady()
  tray.closeToTray = !!desktop.state.closeToTray
})

async function setTray(patch) {
  Object.assign(tray, patch)
  await desktop.setTray(patch)
}
</script>
