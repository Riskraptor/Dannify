<template>
  <div class="setx-host">
  <div class="setx" :class="{ 'is-searching': searching }">
    <!-- The categories, the way a desktop app's settings have them: a column
         of its own, each with its colour, and the search at the top of it. -->
    <aside class="setx-side">
      <h1 class="setx-title">{{ t('settings.title') }}</h1>
      <label class="setx-search">
        <Icon icon="ph:magnifying-glass" class="setx-search-icon" />
        <input
          v-model="query"
          type="search"
          class="setx-search-field"
          :placeholder="t('settings.searchPlaceholder')"
          :aria-label="t('settings.searchPlaceholder')"
          spellcheck="false"
          @keydown.esc="query = ''"
        />
      </label>
      <nav class="setx-nav" :aria-label="t('settings.title')">
        <button
          v-for="p in panes"
          :key="p.id"
          class="setx-cat"
          :class="{ 'is-active': pane === p.id && !searching }"
          :title="t(p.label)"
          :aria-current="pane === p.id && !searching ? 'page' : undefined"
          @click="pickPane(p.id)"
        >
          <span class="setx-tile" :style="{ '--tile': p.tone }"><Icon :icon="p.icon" class="h-4 w-4" /></span>
          <span class="setx-cat-label">{{ t(p.label) }}</span>
        </button>
      </nav>
      <p class="setx-foot">{{ t('settings.subtitle') }}</p>
    </aside>

    <div class="setx-main settings">
      <!-- The narrow column has no room for the search: it sits here then. -->
      <label class="setx-search setx-search-top">
        <Icon icon="ph:magnifying-glass" class="setx-search-icon" />
        <input
          v-model="query"
          type="search"
          class="setx-search-field"
          :placeholder="t('settings.searchPlaceholder')"
          :aria-label="t('settings.searchPlaceholder')"
          spellcheck="false"
          @keydown.esc="query = ''"
        />
      </label>
      <header class="setx-head">
        <template v-if="!searching">
          <span class="setx-tile is-big" :style="{ '--tile': current.tone }">
            <Icon :icon="current.icon" class="h-6 w-6" />
          </span>
          <div class="min-w-0">
            <h2 class="setx-head-title">{{ t(current.label) }}</h2>
            <p class="setx-head-text">{{ t(current.text) }}</p>
          </div>
        </template>
        <div v-else class="min-w-0">
          <h2 class="setx-head-title">{{ t('settings.searchResults', { query: query.trim() }) }}</h2>
          <p class="setx-head-text">{{ t('settings.searchResultsText', { count: matches }) }}</p>
        </div>
        <transition name="fade">
          <span v-if="showSaved" class="pill-accent setx-saved h-7 px-3 text-xs">
            <Icon icon="ph:check-bold" class="h-3.5 w-3.5" />
            {{ t('settings.saved') }}
          </span>
        </transition>
      </header>

      <div ref="paneEl" class="set-pane">
        <p v-if="searching && !matches" class="set-empty">
          {{ t('settings.noMatches', { query: query.trim() }) }}
        </p>

        <!-- Accounts: what Dannify is connected to -->
        <SettingsAccount v-show="showPane('accounts')" @vue:updated="onSectionUpdated" />
        <SettingsListenBrainz v-show="showPane('accounts')" @vue:updated="onSectionUpdated" />

        <!-- The system: closing to the tray, starting at login, shortcuts -->
        <SettingsSystem v-if="desktop.isDesktop" v-show="showPane('general')" @vue:updated="onSectionUpdated" />

        <!-- Appearance -->
        <SettingsAppearance v-show="showPane('appearance')" @vue:updated="onSectionUpdated" />

        <!-- Playback -->
        <SettingsPlayback v-show="showPane('playback')" @vue:updated="onSectionUpdated" />

        <!-- What the app remembers of what was played -->
        <SettingsHistory v-show="showPane('playback')" @vue:updated="onSectionUpdated" />

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
  </div>
</template>

<script setup>
import { ref, computed, watch, onUpdated, nextTick, provide } from 'vue'
import { useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useSettingsManager } from '/src/model/settings'
import { useTheme } from '/src/model/theme'
import { useUi } from '/src/model/ui'
import { useUpdates } from '/src/model/updates'
import { desktop } from '/src/desktop/bridge'
import { useSupport } from '/src/model/support'
import { useI18n } from '/src/i18n'
import { STORAGE_INFO, createStorageInfo } from '/src/components/settings/storageInfo'
import '/src/components/settings/settings.css'
// One component per section; each one's root is its <section>, which the
// search below looks through.
import SettingsAccount from '/src/components/settings/SettingsAccount.vue'
import SettingsListenBrainz from '/src/components/settings/SettingsListenBrainz.vue'
import SettingsAppearance from '/src/components/settings/SettingsAppearance.vue'
import SettingsSystem from '/src/components/settings/SettingsSystem.vue'
import SettingsPlayback from '/src/components/settings/SettingsPlayback.vue'
import SettingsHistory from '/src/components/settings/SettingsHistory.vue'
import SettingsLibrary from '/src/components/settings/SettingsLibrary.vue'
import SettingsDownloads from '/src/components/settings/SettingsDownloads.vue'
import SettingsStorage from '/src/components/settings/SettingsStorage.vue'
import SettingsLyrics from '/src/components/settings/SettingsLyrics.vue'
import SettingsSupport from '/src/components/settings/SettingsSupport.vue'
import SettingsAbout from '/src/components/settings/SettingsAbout.vue'

const { t, locale } = useI18n()
const route = useRoute()
const sm = useSettingsManager()
const theme = useTheme()
const ui = useUi()
const updates = useUpdates()

// The categories, in the order they are looked for. Each has a colour of its
// own, so the column can be read at a glance. General is only there when
// there is something in it: its rows are about the desktop window.
const ALL_PANES = [
  { id: 'accounts', label: 'settings.paneAccounts', text: 'settings.paneAccountsText', icon: 'ph:user-circle-fill', tone: '59 130 246' },
  { id: 'general', label: 'settings.paneGeneral', text: 'settings.paneGeneralText', icon: 'ph:gear-six-fill', tone: '107 114 128' },
  { id: 'appearance', label: 'settings.appearance', text: 'settings.paneAppearanceText', icon: 'ph:palette-fill', tone: '168 85 247' },
  { id: 'playback', label: 'settings.playback', text: 'settings.panePlaybackText', icon: 'ph:play-circle-fill', tone: '34 197 94' },
  { id: 'library', label: 'settings.paneLibrary', text: 'settings.paneLibraryText', icon: 'ph:folders-fill', tone: '245 158 11' },
  { id: 'lyrics', label: 'settings.lyricsGroup', text: 'settings.paneLyricsText', icon: 'ph:microphone-stage-fill', tone: '236 72 153' },
  { id: 'about', label: 'settings.about', text: 'settings.paneAboutText', icon: 'ph:info-fill', tone: '100 116 139' },
]
const panes = computed(() => ALL_PANES.filter((p) => p.id !== 'general' || desktop.isDesktop))

const PANE_KEY = 'dn.settingsPane'
function storedPane() {
  try {
    return localStorage.getItem(PANE_KEY)
  } catch {
    return null
  }
}
function known(id) {
  return panes.value.some((p) => p.id === id)
}
// A link can name the pane to open (?pane=playback): the sound panel's
// "More settings", the account button.
const pane = ref(known(route.query.pane) ? route.query.pane : known(storedPane()) ? storedPane() : 'accounts')
watch(
  () => route.query.pane,
  (id) => {
    if (known(id)) pickPane(id)
  }
)
const current = computed(() => panes.value.find((p) => p.id === pane.value) || panes.value[0])

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
function flashSaved() {
  showSaved.value = true
  clearTimeout(savedTimer)
  savedTimer = setTimeout(() => (showSaved.value = false), 1800)
}
watch(() => sm.lastSaved.value, flashSaved)
watch([() => theme.preference.value, () => locale.value, () => ui.autoOpenLyrics.value], flashSaved)

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
/* Two columns that each keep their place: the categories stay put while a
   long pane scrolls. Sized by the room the page really has, not the window:
   the sidebar takes its share first. The host is what is measured; a grid
   cannot ask its own width. */
.setx-host {
  container-type: inline-size;
  min-height: 100%;
}
.setx {
  --side: 236px;
  display: grid;
  grid-template-columns: var(--side) minmax(0, 1fr);
  align-items: start;
  min-height: 100%;
}
.setx-side {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 26px 14px 18px 18px;
}
.setx-title {
  padding: 0 6px;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.02em;
}
.setx-search {
  position: relative;
  display: block;
}
.setx-search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  width: 15px;
  height: 15px;
  transform: translateY(-50%);
  color: rgb(var(--c-fg) / var(--fg-45));
  pointer-events: none;
}
.setx-search-field {
  width: 100%;
  height: 34px;
  padding: 0 10px 0 32px;
  border-radius: 9px;
  border: 1px solid rgb(var(--c-tint) / 0.1);
  background: rgb(var(--c-tint) / 0.06);
  font-size: 13px;
  color: rgb(var(--c-fg));
  outline: none;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease;
}
.setx-search-field:focus {
  border-color: rgb(var(--c-accent) / 0.7);
  background: rgb(var(--c-tint) / 0.03);
}
.setx-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
  overflow-y: auto;
  scrollbar-width: none;
}
.setx-cat {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 6px 8px;
  border-radius: 9px;
  font-size: 13.5px;
  font-weight: 600;
  text-align: left;
  color: rgb(var(--c-fg) / 0.78);
  transition:
    background-color 0.12s ease,
    color 0.12s ease;
}
.setx-cat:hover {
  background: rgb(var(--c-tint) / 0.06);
  color: rgb(var(--c-fg));
}
.setx-cat.is-active {
  background: rgb(var(--c-tint) / 0.11);
  color: rgb(var(--c-fg));
}
.is-searching .setx-cat {
  opacity: 0.55;
}
.setx-cat-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* A small coloured square with the category's mark in white. */
.setx-tile {
  display: grid;
  flex: none;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 7px;
  color: #fff;
  background: linear-gradient(160deg, rgb(var(--tile) / 0.92), rgb(var(--tile)));
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 0.12);
}
.setx-tile.is-big {
  width: 48px;
  height: 48px;
  border-radius: 12px;
}
.setx-foot {
  margin-top: 6px;
  padding: 0 6px;
  font-size: 11.5px;
  line-height: 1.45;
  color: rgb(var(--c-fg) / var(--fg-45));
}

.setx-main {
  min-width: 0;
  max-width: 820px;
  padding: 26px clamp(18px, 3.4cqi, 40px) 56px;
}
.setx-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 24px;
}
.setx-head-title {
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.01em;
}
.setx-head-text {
  margin-top: 2px;
  font-size: 13px;
  color: rgb(var(--c-fg) / var(--fg-55));
}
.setx-saved {
  margin-left: auto;
  flex: none;
}
.set-pane {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 26px;
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

.setx-search-top {
  display: none;
}
/* Little room: the column keeps its colours and drops its words, rather
   than lying down as a row of tabs that wraps like a web page's. */
@container (max-width: 760px) {
  .setx {
    --side: 64px;
  }
  .setx-side {
    align-items: center;
    padding: 18px 8px;
  }
  .setx-side .setx-title,
  .setx-side .setx-search,
  .setx-cat-label,
  .setx-foot {
    display: none;
  }
  .setx-cat {
    justify-content: center;
    padding: 7px;
  }
  .setx-tile {
    width: 30px;
    height: 30px;
  }
  .setx-search-top {
    display: block;
    margin-bottom: 18px;
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
