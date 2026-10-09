<template>
  <section>
    <h2 class="group-title">{{ t('settings.about') }}</h2>
    <div class="row">
      <img src="../../assets/dannify.svg" alt="" class="row-icon h-6 w-6 drag-none" />
      <div class="row-text">
        <p class="row-label">Dannify</p>
        <p class="row-hint">{{ t('settings.version', { version }) }}</p>
      </div>
      <button class="btn" @click="desktop.openExternal(updates.siteUrl.value)">
        <Icon icon="ph:download-simple" class="h-4 w-4" />
        {{ t('settings.builds') }}
      </button>
    </div>
    <label class="row">
      <Icon icon="ph:arrows-clockwise" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('update.autoUpdate') }}</p>
        <p class="row-hint">{{ t('update.autoUpdateHint') }}</p>
      </div>
      <input
        type="checkbox"
        class="switch"
        :checked="updates.autoUpdate.value"
        @change="updates.setAutoUpdate($event.target.checked)"
      />
    </label>
    <div class="row">
      <Icon icon="ph:arrow-circle-down" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('update.title') }}</p>
        <p class="row-hint">{{ updateHint }}</p>
      </div>
      <div class="flex shrink-0 gap-2">
        <button
          v-if="updates.available.value"
          class="btn-accent btn-pill px-4"
          :disabled="updates.downloading.value"
          @click="updates.downloadAndInstall()"
        >
          <span v-if="updates.downloading.value" class="spinner h-4 w-4" />
          <Icon v-else :icon="updates.manual.value ? 'ph:arrow-square-out' : 'ph:download-simple'" class="h-4 w-4" />
          {{ updates.downloading.value
            ? `${Math.round(updates.progress.value)}%`
            : updates.manual.value
              ? t('update.downloadManual')
              : updates.ready.value
              ? t('update.installNow')
              : t('update.downloadAndInstall') }}
        </button>
        <button class="btn" :disabled="updates.checking.value" @click="updates.check(true, { quiet: false })">
          <span v-if="updates.checking.value" class="spinner h-4 w-4" />
          {{ t('update.checkNow') }}
        </button>
      </div>
    </div>

    <!-- What is in the new version, here, rather than behind a link to
         a page on the internet. -->
    <div v-if="updates.available.value && noteLines.length" class="up-notes">
      <p class="up-notes-head">
        {{ t('update.releaseNotes') }} &middot; {{ updates.info.value.version }}
      </p>
      <p v-for="(line, i) in noteLines" :key="i">{{ line }}</p>
    </div>

    <!-- What the update is actually doing. Most of the wait is spent
         working out which files changed, and a bar on its own at 0%
         reads as a download that never started. -->
    <div v-if="updates.downloading.value || updates.ready.value" class="up-flow">
      <div class="up-line">
        <span class="up-stage">{{ updates.stage.value || t('update.title') }}</span>
        <span class="up-pct">{{ Math.round(updates.progress.value) }}%</span>
      </div>
      <div class="up-track">
        <span class="up-fill" :style="{ width: `${Math.max(2, updates.progress.value)}%` }" />
      </div>
      <p class="up-note">
        {{ updates.ready.value ? t('update.readyNote') : t('update.flowNote') }}
      </p>
    </div>
    <div class="row">
      <Icon icon="ph:keyboard" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('shortcuts.title') }}</p>
        <p class="row-hint">{{ t('settings.shortcutsHint') }}</p>
      </div>
      <button class="btn" @click="ui.shortcutsOpen.value = true">
        {{ t('settings.showShortcuts') }}
      </button>
    </div>
    <div class="row" :class="{ 'is-disabled': !reporting.status.enabled }">
      <Icon icon="ph:bug" class="row-icon" />
      <div class="row-text">
        <p class="row-label">
          {{ t('problems.title') }}
          <span v-if="!reporting.status.enabled" class="soon-pill">{{ t('problems.comingSoon') }}</span>
        </p>
        <p class="row-hint">
          {{ reporting.status.enabled ? t('problems.hint') : t('problems.hintSoon') }}
          <template v-if="reporting.status.pending">
            {{ t('problems.waiting', { count: reporting.status.pending }) }}
          </template>
        </p>
      </div>
      <button class="btn" :disabled="!reporting.status.enabled" @click="reporting.openReport()">
        <Icon icon="ph:paper-plane-tilt" class="h-4 w-4" />
        {{ t('problems.report') }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import { appVersion } from '/src/model/api'
import { useUi } from '/src/model/ui'
import { useUpdates } from '/src/model/updates'
import { useConnectivity } from '/src/model/connectivity'
import { useReporting } from '/src/model/problems'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'

const { t } = useI18n()
const ui = useUi()
const updates = useUpdates()
const connectivity = useConnectivity()

const version = appVersion

// "Report a problem": written and sent in the app (model/problems.js).
const reporting = useReporting()

// The notes come back as one block of text. Split it for reading, and never
// render it as markup: it arrives over the network.
const noteLines = computed(() =>
  String(updates.info.value.notes || '')
    .split(/\r?\n+/)
    .map((l) => l.replace(/^[#*\-\s]+/, '').trim())
    .filter(Boolean)
    .slice(0, 12)
)

const updateHint = computed(() => {
  if (updates.downloading.value) {
    return t('update.downloading', { percent: Math.round(updates.progress.value) })
  }
  if (updates.available.value) {
    // Said up front, so the button that opens a web page is no surprise.
    if (updates.manual.value) return t('update.manualHint', { version: updates.info.value.version })
    return t('update.available', { version: updates.info.value.version })
  }
  // Every failure used to be reported as the connection being down, which
  // was wrong whenever the connection was fine and something else was not.
  if (updates.lastError.value) {
    return connectivity.online.value ? t('update.checkFailedLater') : t('update.offline')
  }
  if (updates.checking.value) return t('update.checking')
  if (!updates.checkedOk.value) {
    return connectivity.online.value ? t('update.notChecked') : t('update.offline')
  }
  return t('update.upToDate', { version: version.value })
})
</script>
