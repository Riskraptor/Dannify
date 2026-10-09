<template>
  <div class="pb-14">
    <ViewHeader :title="t('settings.title')" :subtitle="t('settings.subtitle')">
      <template #actions>
        <!-- Find a setting by what it does, across every pane. -->
        <div class="set-search">
          <Icon icon="ph:magnifying-glass" class="set-search-icon" />
          <input
            v-model="query"
            type="search"
            class="field h-9 w-64 pl-9"
            :placeholder="t('settings.searchPlaceholder')"
            spellcheck="false"
            @keydown.esc="query = ''"
          />
        </div>
        <transition name="fade">
          <span v-if="showSaved" class="pill-accent h-7 px-3 text-xs">
            <Icon icon="ph:check-bold" class="h-3.5 w-3.5" />
            {{ t('settings.saved') }}
          </span>
        </transition>
      </template>
    </ViewHeader>

    <div class="settings view-pad">
      <nav class="set-nav" :class="{ 'is-muted': searching }" :aria-label="t('settings.title')">
        <button
          v-for="p in panes"
          :key="p.id"
          class="set-tab"
          :class="{ 'is-active': pane === p.id && !searching }"
          @click="pickPane(p.id)"
        >
          <Icon :icon="p.icon" class="h-[18px] w-[18px]" />
          <span>{{ t(p.label) }}</span>
        </button>
      </nav>

      <div ref="paneEl" class="set-pane">
      <p v-if="searching && !matches" class="set-empty">
        {{ t('settings.noMatches', { query: query.trim() }) }}
      </p>
      <!-- Account -->
      <SettingsAccount v-show="showPane('general')" @vue:updated="onSectionUpdated" />

      <!-- Appearance -->
      <SettingsAppearance v-show="showPane('appearance')" @vue:updated="onSectionUpdated" />

      <!-- The system: closing to the tray, starting at login, shortcuts -->
      <SettingsSystem v-if="desktop.isDesktop" v-show="showPane('general')" @vue:updated="onSectionUpdated" />

      <!-- Playback -->
      <SettingsPlayback v-show="showPane('playback')" @vue:updated="onSectionUpdated" />

      <!-- Library -->
      <SettingsLibrary v-show="showPane('library')" @vue:updated="onSectionUpdated" />

      <!-- Downloads. How a saved song is kept is the app's business, not a
           setting or something to explain: format, quality and playlist
           files are not offered. -->
      <SettingsDownloads v-show="showPane('library')" @vue:updated="onSectionUpdated" />

      <!-- Storage -->
      <SettingsStorage v-show="showPane('library')" @vue:updated="onSectionUpdated" />

      <!-- Lyrics -->
      <SettingsLyrics v-show="showPane('lyrics')" @vue:updated="onSectionUpdated" />

      <!-- Support -->
      <SettingsSupport v-if="support.configured" v-show="showPane('about')" @vue:updated="onSectionUpdated" />

      <!-- About -->
      <SettingsAbout v-show="showPane('about')" @vue:updated="onSectionUpdated" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUpdated, nextTick, provide } from 'vue'
import { Icon } from '@iconify/vue'
import { useSettingsManager } from '/src/model/settings'
import { useTheme } from '/src/model/theme'
import { useUi } from '/src/model/ui'
import { useUpdates } from '/src/model/updates'
import { desktop } from '/src/desktop/bridge'
import { useSupport } from '/src/model/support'
import { useI18n } from '/src/i18n'
import ViewHeader from '/src/components/ui/ViewHeader.vue'
import { STORAGE_INFO, createStorageInfo } from '/src/components/settings/storageInfo'
import '/src/components/settings/settings.css'
// One component per section; each one's root is its <section>, which the
// search below looks through.
import SettingsAccount from '/src/components/settings/SettingsAccount.vue'
import SettingsAppearance from '/src/components/settings/SettingsAppearance.vue'
import SettingsSystem from '/src/components/settings/SettingsSystem.vue'
import SettingsPlayback from '/src/components/settings/SettingsPlayback.vue'
import SettingsLibrary from '/src/components/settings/SettingsLibrary.vue'
import SettingsDownloads from '/src/components/settings/SettingsDownloads.vue'
import SettingsStorage from '/src/components/settings/SettingsStorage.vue'
import SettingsLyrics from '/src/components/settings/SettingsLyrics.vue'
import SettingsSupport from '/src/components/settings/SettingsSupport.vue'
import SettingsAbout from '/src/components/settings/SettingsAbout.vue'

const { t, locale } = useI18n()
const sm = useSettingsManager()
const theme = useTheme()
const ui = useUi()
const updates = useUpdates()

// One long scroll of nine headings was hard to search by eye, so the groups
// are panes now and the rail says what is where. The choice is remembered:
// people come back to Settings for the same thing they came for last time.
const panes = [
  { id: 'general', label: 'settings.paneGeneral', icon: 'ph:sliders-horizontal' },
  { id: 'appearance', label: 'settings.appearance', icon: 'ph:palette' },
  { id: 'playback', label: 'settings.playback', icon: 'ph:play-circle' },
  { id: 'library', label: 'settings.paneLibrary', icon: 'ph:folders' },
  { id: 'lyrics', label: 'settings.lyricsGroup', icon: 'ph:microphone-stage' },
  { id: 'about', label: 'settings.about', icon: 'ph:info' },
]

const PANE_KEY = 'dn.settingsPane'
function storedPane() {
  try {
    return localStorage.getItem(PANE_KEY)
  } catch {
    return null
  }
}
const pane = ref(panes.some((p) => p.id === storedPane()) ? storedPane() : 'general')
// ----- Search -------------------------------------------------------------
// Typing looks through every pane at once and keeps only the rows that
// mention it, by name or by description.
const query = ref('')
const searching = computed(() => query.value.trim().length > 0)
const matches = ref(0)
const paneEl = ref(null)

function showPane(id) {
  return searching.value || pane.value === id
}
function pickPane(id) {
  query.value = ''
  pane.value = id
}

function foldText(text) {
  return String(text || '')
    .normalize('NFKD')
    .replace(/\p{M}+/gu, '')
    .toLowerCase()
}

async function filterRows() {
  await nextTick()
  const root = paneEl.value
  if (!root) return
  const words = foldText(query.value).split(/\s+/).filter(Boolean)
  let shown = 0
  for (const section of root.querySelectorAll(':scope > section')) {
    const title = foldText((section.querySelector('.group-title') || {}).textContent)
    let visible = 0
    for (const row of section.querySelectorAll(':scope > .row, :scope > .up-notes, :scope > .up-flow')) {
      const text = `${title} ${foldText(row.textContent)}`
      const hit = !words.length || words.every((w) => text.includes(w))
      row.hidden = !hit
      if (hit) visible++
    }
    section.hidden = words.length > 0 && visible === 0
    shown += visible
  }
  matches.value = shown
}
watch(query, filterRows)
onUpdated(() => {
  if (searching.value) filterRows()
})
// The sections draw themselves: a row that appears in one (the storage
// figures arriving, say) is filtered like the rest.
function onSectionUpdated() {
  if (searching.value) filterRows()
}

watch(pane, (id) => {
  try {
    localStorage.setItem(PANE_KEY, id)
  } catch {
    // storage blocked: the choice just won't survive a restart
  }
})

// Opening About answers the question it shows, if nothing has yet.
watch(
  () => pane.value,
  (id) => {
    if (id === 'about' && !updates.checkedOk.value && !updates.checking.value) {
      updates.check(false)
    }
  },
  { immediate: true }
)

// --- Support the app (one link, see support.py and model/support.js)
const { config: support } = useSupport()

// Flash a "Saved" pill whenever any setting is persisted.
const showSaved = ref(false)
let savedTimer = null
watch(
  () => sm.lastSaved.value,
  () => {
    showSaved.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (showSaved.value = false), 1800)
  }
)
watch([() => theme.preference.value, () => locale.value, () => ui.autoOpenLyrics.value], () => {
  showSaved.value = true
  clearTimeout(savedTimer)
  savedTimer = setTimeout(() => (showSaved.value = false), 1800)
})

// ----- Storage --------------------------------------------------------------
// Measured when its pane is opened, not on every visit to Settings: it walks
// the whole music folder. The folder and storage rows share what was found.
const storageInfo = createStorageInfo()
provide(STORAGE_INFO, storageInfo)
watch(
  () => pane.value === 'library' || searching.value,
  (need) => {
    if (need && !storageInfo.storage.value) storageInfo.load()
  },
  { immediate: true }
)

</script>

<style scoped>

.set-search {
  position: relative;
}
.set-search-icon {
  position: absolute;
  left: 11px;
  top: 50%;
  width: 16px;
  height: 16px;
  transform: translateY(-50%);
  color: rgb(var(--c-fg) / var(--fg-45));
  pointer-events: none;
}
.set-nav.is-muted {
  opacity: 0.5;
}
.set-empty {
  padding: 28px 4px;
  font-size: 14px;
  color: rgb(var(--c-fg) / var(--fg-60));
}
/* A row or a group the search left out. `hidden` alone loses to the display
   the rows set for themselves. */
.set-pane :deep([hidden]) {
  display: none !important;
}
.settings {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  align-items: start;
  gap: 28px;
  max-width: 1040px;
}
.set-pane {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 28px;
}
.set-nav {
  position: sticky;
  top: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.set-tab {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 9px;
  font-size: 13.5px;
  font-weight: 600;
  text-align: left;
  color: rgb(var(--c-fg) / 0.65);
  transition:
    background-color 0.12s ease,
    color 0.12s ease;
}
.set-tab:hover {
  background: rgb(var(--c-tint) / 0.07);
  color: rgb(var(--c-fg) / 0.9);
}
.set-tab.is-active {
  background: rgb(var(--c-tint) / 0.11);
  color: rgb(var(--c-fg));
}
/* Narrow window: the rail lies down above the pane rather than stealing a
   third of the width from it. */
@media (max-width: 860px) {
  .settings {
    grid-template-columns: minmax(0, 1fr);
    gap: 18px;
  }
  /* Wrap rather than scroll. This was a single row that overflowed with its
     scrollbar hidden, so at the smallest window the last tab sat past the
     right edge with nothing to show it was there and no way to reach it. */
  .set-nav {
    position: static;
    flex-direction: row;
    flex-wrap: wrap;
    gap: 6px;
    padding-bottom: 2px;
  }
  .set-tab {
    flex: none;
    padding: 8px 12px;
  }
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
