<template>
  <section>
    <h2 class="group-title">{{ t('settings.about') }}</h2>
    <div class="row">
      <img src="../../assets/dannify.svg" alt="" class="row-icon drag-none" />
      <div class="row-text">
        <p class="row-label">Dannify</p>
        <p class="row-hint">{{ t('settings.version', { version: versionLabel(version) }) }}</p>
      </div>
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
    <!-- Where updates stand, said as an answer: up to date, checking, ready,
         or could not look. A check asked for here ends with a tick. -->
    <article class="up-card" :class="`is-${upState}`" aria-live="polite">
      <span class="up-icon" :class="{ 'is-fresh': fresh }">
        <Icon :icon="upIcon" class="h-6 w-6" :class="{ 'animate-spin': upState === 'checking' }" />
      </span>
      <div class="up-text">
        <p class="up-title">{{ upTitle }}</p>
        <p class="up-sub">{{ updateHint }}</p>
      </div>
      <div class="flex shrink-0 flex-wrap gap-2">
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
        <button class="btn" :disabled="updates.checking.value" @click="checkNow">
          <span v-if="updates.checking.value" class="spinner h-4 w-4" />
          {{ t('update.checkNow') }}
        </button>
      </div>
    </article>

    <!-- What is in the new version, here, rather than behind a link to
         a page on the internet: what is new, not how it is packaged. -->
    <WhatsNew
      v-if="updates.available.value"
      class="up-notes"
      :version="updates.info.value.version"
      :notes="updates.info.value.notes"
    />

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
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { appVersion } from '/src/model/api'
import { useUi } from '/src/model/ui'
import { useUpdates, versionLabel } from '/src/model/updates'
import { useConnectivity } from '/src/model/connectivity'
import { useReporting } from '/src/model/problems'
import { useI18n } from '/src/i18n'
import WhatsNew from '/src/components/ui/WhatsNew.vue'

const { t, locale } = useI18n()
const ui = useUi()
const updates = useUpdates()
const connectivity = useConnectivity()

const version = appVersion

// "Report a problem": written and sent in the app (model/problems.js).
const reporting = useReporting()

// One state, said as a headline with a line under it.
const upState = computed(() => {
  if (updates.downloading.value) return 'working'
  if (updates.ready.value) return 'ready'
  if (updates.available.value) return 'available'
  if (updates.checking.value) return 'checking'
  if (updates.lastError.value || !updates.checkedOk.value) return 'unknown'
  return 'current'
})
const upIcon = computed(
  () =>
    ({
      working: 'ph:download-simple-bold',
      ready: 'ph:sparkle-fill',
      available: 'ph:arrow-circle-up-fill',
      checking: 'ph:arrows-clockwise-bold',
      unknown: 'ph:cloud-slash',
      current: 'ph:check-circle-fill',
    })[upState.value]
)
const upTitle = computed(() => {
  const next = versionLabel(updates.info.value.version)
  switch (upState.value) {
    case 'working':
      return t('update.downloading', { percent: Math.round(updates.progress.value) })
    case 'ready':
      return t('update.statusReady', { version: next })
    case 'available':
      return t('update.statusAvailable', { version: next })
    case 'checking':
      return t('update.statusChecking')
    case 'unknown':
      return connectivity.online.value ? t('update.statusUnknown') : t('update.offline')
    default:
      return t('update.statusCurrent')
  }
})

const updateHint = computed(() => {
  if (updates.available.value && updates.manual.value) {
    // Said up front, so the button that opens a web page is no surprise.
    return t('update.manualHint', { version: versionLabel(updates.info.value.version) })
  }
  // Every failure used to be reported as the connection being down, which
  // was wrong whenever the connection was fine and something else was not.
  if (updates.lastError.value && connectivity.online.value) return t('update.checkFailedLater')
  const line = t('update.youHave', { version: versionLabel(version.value) })
  if (!updates.checkedAt.value) return line
  return `${line} · ${t('update.checkedAgo', { when: ago(updates.checkedAt.value) })}`
})

// Kept current while the pane is open, so "checked a minute ago" moves on.
const tick = ref(Date.now())
let ticker = 0
onMounted(() => (ticker = setInterval(() => (tick.value = Date.now()), 30000)))
onBeforeUnmount(() => clearInterval(ticker))
function ago(ms) {
  void tick.value
  const diff = Math.max(0, (Date.now() - ms) / 1000)
  const rtf = new Intl.RelativeTimeFormat(locale.value || 'en', { numeric: 'auto' })
  if (diff < 45) return rtf.format(0, 'second')
  if (diff < 3600) return rtf.format(-Math.round(diff / 60), 'minute')
  if (diff < 86400) return rtf.format(-Math.round(diff / 3600), 'hour')
  return rtf.format(-Math.round(diff / 86400), 'day')
}

// A check asked for: the tick springs when it finds nothing to do.
const fresh = ref(false)
async function checkNow() {
  await updates.check(true, { quiet: false })
  if (upState.value === 'current') {
    fresh.value = true
    setTimeout(() => (fresh.value = false), 1600)
  }
}
</script>

<style scoped>
.up-card {
  --up: var(--c-accent);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px 16px;
  margin: 4px 0 8px;
  padding: 16px 18px;
  border-radius: 14px;
  background:
    radial-gradient(80% 140% at 0% 0%, rgb(var(--up) / 0.12), transparent 60%),
    rgb(var(--c-tint) / 0.04);
  box-shadow: inset 0 0 0 1px rgb(var(--c-tint) / 0.08);
  transition: background-color 0.3s ease;
}
.up-card.is-unknown,
.up-card.is-checking {
  --up: var(--c-tint);
}
.up-icon {
  display: grid;
  width: 46px;
  height: 46px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 999px;
  background: rgb(var(--up) / 0.16);
  color: rgb(var(--up));
}
.up-card.is-unknown .up-icon,
.up-card.is-checking .up-icon {
  color: rgb(var(--c-fg) / 0.7);
}
.up-icon.is-fresh {
  animation: up-pop 0.6s cubic-bezier(0.2, 0.9, 0.2, 1.4);
}
@keyframes up-pop {
  0% {
    transform: scale(0.6);
  }
  60% {
    transform: scale(1.15);
  }
  100% {
    transform: scale(1);
  }
}
.up-text {
  min-width: 0;
  flex: 1 1 220px;
}
.up-title {
  font-size: 15px;
  font-weight: 750;
}
.up-sub {
  margin-top: 2px;
  font-size: 12.5px;
  color: rgb(var(--c-fg) / var(--fg-60, 0.62));
}
@media (prefers-reduced-motion: reduce) {
  .up-icon.is-fresh {
    animation: none;
  }
}
</style>
