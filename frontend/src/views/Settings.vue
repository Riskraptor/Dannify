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
      <nav class="setx-nav" :aria-label="t('settings.title')" @keydown="onNavKey">
        <button
          v-for="p in panes"
          :key="p.id"
          class="setx-cat"
          :class="{ 'is-active': pane === p.id && !searching, 'is-me': p.id === 'accounts' }"
          :title="t(p.label)"
          :aria-current="pane === p.id && !searching ? 'page' : undefined"
          :tabindex="pane === p.id ? 0 : -1"
          @click="pickPane(p.id)"
        >
          <!-- Accounts is who is signed in: their picture and name, the
               way a desktop's settings open on the person. -->
          <template v-if="p.id === 'accounts'">
            <span class="setx-me-pic">
              <img v-if="photo" :src="photo" alt="" referrerpolicy="no-referrer" @error="photoFailed = true" />
              <Icon v-else :icon="account.signedIn.value ? 'ph:user-fill' : 'ph:user-circle-plus-fill'" class="h-5 w-5" />
            </span>
            <span class="setx-me-text">
              <span class="setx-me-name">{{ meName }}</span>
              <span class="setx-me-sub" :class="{ 'is-invite': !account.signedIn.value }">{{ meSub }}</span>
            </span>
          </template>
          <template v-else>
            <span class="setx-tile" :style="{ '--tile': p.tone }"><Icon :icon="p.icon" class="h-4 w-4" /></span>
            <span class="setx-cat-label">{{ t(p.label) }}</span>
          </template>
        </button>
      </nav>
      <!-- The version, and whether there is a newer one: About in a glance. -->
      <button class="setx-ver" :class="{ 'is-new': updates.available.value }" :title="t('settings.about')" @click="pickPane('about')">
        <img src="../assets/dannify.svg" alt="" class="setx-ver-logo drag-none" />
        <span class="setx-ver-text">
          <span class="setx-ver-name">Dannify {{ appVersion }}</span>
          <span v-if="versionState" class="setx-ver-state"><i class="setx-ver-dot" />{{ versionState }}</span>
        </span>
      </button>
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
      <header ref="headEl" class="setx-head" :style="{ '--tone': searching ? 'var(--c-accent)' : current.tone }">
        <Icon :icon="searching ? 'ph:magnifying-glass-thin' : current.mark" class="setx-head-mark" aria-hidden="true" />
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
        <SettingsAccount v-show="showPane('accounts')" :style="paneStyle('accounts')" @vue:updated="onSectionUpdated" />
        <SettingsListenBrainz v-show="showPane('accounts')" :style="paneStyle('accounts')" @vue:updated="onSectionUpdated" />

        <!-- General: the language, then the system (closing to the tray,
             starting at login, shortcuts) -->
        <SettingsLanguage v-show="showPane('general')" :style="paneStyle('general')" @vue:updated="onSectionUpdated" />
        <SettingsSystem v-if="desktop.isDesktop" v-show="showPane('general')" :style="paneStyle('general')" @vue:updated="onSectionUpdated" />

        <!-- Appearance -->
        <SettingsAppearance v-show="showPane('appearance')" class="is-pane-named" :style="paneStyle('appearance')" @vue:updated="onSectionUpdated" />
        <SettingsSpecialDays v-show="showPane('appearance')" :style="paneStyle('appearance')" @vue:updated="onSectionUpdated" />

        <!-- Playback -->
        <SettingsPlayback v-show="showPane('playback')" class="is-pane-named" :style="paneStyle('playback')" @vue:updated="onSectionUpdated" />

        <!-- What the app remembers of what was played -->
        <SettingsHistory v-show="showPane('playback')" :style="paneStyle('playback')" @vue:updated="onSectionUpdated" />

        <!-- Library -->
        <SettingsLibrary v-show="showPane('library')" :style="paneStyle('library')" @vue:updated="onSectionUpdated" />

        <!-- Downloads. How a saved song is kept is the app's business, not a
             setting or something to explain: format, quality and playlist
             files are not offered. -->
        <SettingsDownloads v-show="showPane('library')" :style="paneStyle('library')" @vue:updated="onSectionUpdated" />

        <!-- Storage -->
        <SettingsStorage v-show="showPane('library')" :style="paneStyle('library')" @vue:updated="onSectionUpdated" />

        <!-- Lyrics -->
        <SettingsLyrics v-show="showPane('lyrics')" class="is-pane-named" :style="paneStyle('lyrics')" @vue:updated="onSectionUpdated" />

        <!-- Support -->
        <SettingsSupport v-if="support.configured" v-show="showPane('about')" :style="paneStyle('about')" @vue:updated="onSectionUpdated" />

        <!-- About -->
        <SettingsAbout v-show="showPane('about')" class="is-pane-named" :style="paneStyle('about')" @vue:updated="onSectionUpdated" />
      </div>
    </div>
  </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUpdated, onBeforeUnmount, nextTick, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useSettingsManager } from '/src/model/settings'
import { useTheme } from '/src/model/theme'
import { useUi } from '/src/model/ui'
import { useUpdates } from '/src/model/updates'
import { useAccount } from '/src/model/account'
import { appVersion } from '/src/model/api'
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
import SettingsSpecialDays from '/src/components/settings/SettingsSpecialDays.vue'
import SettingsLanguage from '/src/components/settings/SettingsLanguage.vue'
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
const router = useRouter()
const sm = useSettingsManager()
const theme = useTheme()
const ui = useUi()
const updates = useUpdates()
const account = useAccount()

// The categories, in the order they are looked for. Each has a colour of its
// own, so the column can be read at a glance, and its rows wear it.
const ALL_PANES = [
  { id: 'accounts', label: 'settings.paneAccounts', text: 'settings.paneAccountsText', icon: 'ph:user-circle-fill', mark: 'ph:user-circle-thin', tone: '59 130 246' },
  { id: 'general', label: 'settings.paneGeneral', text: 'settings.paneGeneralText', icon: 'ph:gear-six-fill', mark: 'ph:gear-six-thin', tone: '107 114 128' },
  { id: 'appearance', label: 'settings.appearance', text: 'settings.paneAppearanceText', icon: 'ph:palette-fill', mark: 'ph:palette-thin', tone: '168 85 247' },
  { id: 'playback', label: 'settings.playback', text: 'settings.panePlaybackText', icon: 'ph:play-circle-fill', mark: 'ph:play-circle-thin', tone: '34 197 94' },
  { id: 'library', label: 'settings.paneLibrary', text: 'settings.paneLibraryText', icon: 'ph:folders-fill', mark: 'ph:folders-thin', tone: '245 158 11' },
  { id: 'lyrics', label: 'settings.lyricsGroup', text: 'settings.paneLyricsText', icon: 'ph:microphone-stage-fill', mark: 'ph:microphone-stage-thin', tone: '236 72 153' },
  { id: 'about', label: 'settings.about', text: 'settings.paneAboutText', icon: 'ph:info-fill', mark: 'ph:info-thin', tone: '13 148 136' },
]
const panes = computed(() => ALL_PANES)
// A section in its pane's colour, and under its pane's name when a search
// gathers rows from all of them (unless it is named like its pane:
// is-pane-named).
function paneStyle(id) {
  const p = ALL_PANES.find((x) => x.id === id)
  return { '--tone': p.tone, '--pane-name': JSON.stringify(t(p.label)) }
}

// Who is signed in, at the top of the column.
const photoFailed = ref(false)
const photo = computed(() => (account.signedIn.value && !photoFailed.value && account.profile.value.photo) || '')
watch(() => account.profile.value.photo, () => (photoFailed.value = false))
const meName = computed(() =>
  account.signedIn.value ? account.displayName.value || t('account.connected') : t('account.signedOutTitle')
)
const meSub = computed(() => (account.signedIn.value ? t('settings.youtubeMusic') : t('account.connect')))

// Where the version stands, under it.
const versionState = computed(() => {
  if (updates.ready.value) return t('update.installNow')
  if (updates.available.value) return t('update.available', { version: updates.info.value.version })
  if (updates.checking.value) return t('update.checking')
  return updates.checkedOk.value ? t('settings.upToDate') : ''
})

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
  // The address follows, so a link to the pane it names (the sound panel's
  // "More settings") still opens it after another pane was picked here.
  if (route.query.pane !== id) router.replace({ query: { ...route.query, pane: id } })
}

// Up and down move through the categories, the way a list does.
function onNavKey(e) {
  const step = { ArrowDown: 1, ArrowUp: -1 }[e.key]
  if (!step && e.key !== 'Home' && e.key !== 'End') return
  e.preventDefault()
  const list = panes.value
  const at = list.findIndex((p) => p.id === pane.value)
  const to = e.key === 'Home' ? 0 : e.key === 'End' ? list.length - 1 : (at + step + list.length) % list.length
  const nav = e.currentTarget
  pickPane(list[to].id)
  nextTick(() => nav.querySelectorAll('.setx-cat')[to]?.focus())
}

// A new pane comes in rather than snapping in, from its top.
const headEl = ref(null)
function scrollerOf(el) {
  for (let node = el && el.parentElement; node; node = node.parentElement) {
    const y = getComputedStyle(node).overflowY
    if ((y === 'auto' || y === 'scroll') && node.scrollHeight > node.clientHeight) return node
  }
  return null
}
watch(pane, async () => {
  await nextTick()
  const scroller = scrollerOf(paneEl.value)
  if (scroller && scroller.scrollTop > 0) scroller.scrollTop = 0
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  const frames = [
    { opacity: 0, transform: 'translateY(10px)' },
    { opacity: 1, transform: 'none' },
  ]
  for (const [el, delay] of [
    [headEl.value, 0],
    [paneEl.value, 40],
  ]) {
    if (el && el.animate) el.animate(frames, { duration: 260, delay, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)', fill: 'backwards' })
  }
})

// What a search found, marked where it was found. A highlight, not changed
// markup: the rows are the sections' own.
const HIT = 'settings-hit'
function markHits(words) {
  if (typeof CSS === 'undefined' || !CSS.highlights || typeof Highlight === 'undefined') return
  CSS.highlights.delete(HIT)
  const root = paneEl.value
  if (!root || !words.length) return
  const ranges = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const host = node.parentElement
    if (!host || !host.closest('.row-label, .row-hint, .group-title') || host.closest('[hidden]')) continue
    const text = node.data.toLowerCase()
    for (const word of words) {
      for (let at = text.indexOf(word); at !== -1; at = text.indexOf(word, at + word.length)) {
        const range = new Range()
        range.setStart(node, at)
        range.setEnd(node, Math.min(at + word.length, node.length))
        ranges.push(range)
      }
    }
  }
  if (ranges.length) CSS.highlights.set(HIT, new Highlight(...ranges))
}
onBeforeUnmount(() => markHits([]))

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
  markHits(words)
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

// Opening Settings answers the question its column shows, if nothing has
// yet: the answer is kept a while, so this asks no one twice.
if (!updates.checkedOk.value && !updates.checking.value) updates.check(false)

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
  text-overflow: ellipsis;
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
.setx-cat:focus-visible {
  outline: 2px solid rgb(var(--c-accent));
  outline-offset: -2px;
}
/* The person, first: a card of their own above the categories. */
.setx-cat.is-me {
  gap: 12px;
  margin-bottom: 8px;
  padding: 10px;
  border-radius: 14px;
  background: rgb(var(--c-tint) / 0.05);
  box-shadow: inset 0 0 0 1px rgb(var(--c-tint) / 0.06);
}
.setx-cat.is-me:hover {
  background: rgb(var(--c-tint) / 0.08);
}
.setx-cat.is-me.is-active {
  background: rgb(var(--c-tint) / 0.12);
  box-shadow: inset 0 0 0 1px rgb(59 130 246 / 0.45);
}
.setx-me-pic {
  display: grid;
  flex: none;
  place-items: center;
  width: 40px;
  height: 40px;
  overflow: hidden;
  border-radius: 999px;
  color: #fff;
  background: linear-gradient(160deg, rgb(96 165 250), rgb(37 99 235));
}
.setx-me-pic img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.setx-me-text {
  display: grid;
  min-width: 0;
  line-height: 1.3;
}
.setx-me-name,
.setx-me-sub {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.setx-me-name {
  font-size: 14px;
  font-weight: 700;
  color: rgb(var(--c-fg));
}
.setx-me-sub {
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--c-fg) / var(--fg-55));
}
.setx-me-sub.is-invite {
  font-weight: 700;
  color: rgb(var(--c-accent));
}
/* The version, at the foot of the column. */
.setx-ver {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
  padding: 8px 10px;
  border-radius: 12px;
  text-align: left;
  background: rgb(var(--c-tint) / 0.04);
  transition: background-color 0.15s ease;
}
.setx-ver:hover {
  background: rgb(var(--c-tint) / 0.08);
}
.setx-ver:focus-visible {
  outline: 2px solid rgb(var(--c-accent));
  outline-offset: -2px;
}
.setx-ver-logo {
  width: 28px;
  height: 28px;
  flex: none;
}
.setx-ver-text {
  display: grid;
  min-width: 0;
  gap: 1px;
}
.setx-ver-name {
  font-size: 12.5px;
  font-weight: 700;
}
.setx-ver-state {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
  font-size: 11.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgb(var(--c-fg) / var(--fg-55));
}
.setx-ver-dot {
  width: 6px;
  height: 6px;
  flex: none;
  border-radius: 999px;
  background: rgb(34 197 94);
}
.setx-ver.is-new .setx-ver-state {
  font-weight: 700;
  color: rgb(var(--c-accent));
}
.setx-ver.is-new .setx-ver-dot {
  background: rgb(var(--c-accent));
  animation: setx-ping 1.8s ease-out infinite;
}
@keyframes setx-ping {
  0% {
    box-shadow: 0 0 0 0 rgb(var(--c-accent) / 0.55);
  }
  100% {
    box-shadow: 0 0 0 7px rgb(var(--c-accent) / 0);
  }
}
@media (prefers-reduced-motion: reduce) {
  .setx-ver.is-new .setx-ver-dot {
    animation: none;
  }
}
.is-searching .setx-cat {
  opacity: 0.55;
}
/* Two lines before it is cut: "Bibliothek und Downloads" read
   "Bibliothek und Downlo…". */
.setx-cat-label {
  display: -webkit-box;
  min-width: 0;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-height: 1.25;
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
  margin-top: -4px;
  padding: 0 6px;
  font-size: 11.5px;
  line-height: 1.45;
  color: rgb(var(--c-fg) / var(--fg-45));
}

.setx-main {
  min-width: 0;
  max-width: 900px;
  padding: 26px clamp(18px, 3.4cqi, 40px) 56px;
}
/* The pane's header: its colour rising from a corner, its mark large and
   faint behind, the square lit from below. */
.setx-head {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 26px;
  padding: 20px 22px;
  overflow: hidden;
  border-radius: 20px;
  background:
    radial-gradient(120% 190% at 0% 0%, rgb(var(--tone) / 0.28), transparent 62%),
    rgb(var(--c-tint) / 0.035);
  box-shadow: inset 0 0 0 1px rgb(var(--c-tint) / 0.07);
  isolation: isolate;
}
[data-mode='light'] .setx-head {
  background:
    radial-gradient(120% 190% at 0% 0%, rgb(var(--tone) / 0.2), transparent 62%),
    rgb(var(--c-raised));
}
.setx-head-mark {
  position: absolute;
  z-index: -1;
  right: -6px;
  bottom: -52px;
  width: 168px;
  height: 168px;
  color: rgb(var(--tone));
  opacity: 0.3;
  transform: rotate(-12deg);
  pointer-events: none;
}
.setx-head .setx-tile.is-big {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  box-shadow:
    0 10px 26px rgb(var(--tone) / 0.42),
    inset 0 0 0 1px rgb(255 255 255 / 0.14);
}
.setx-head-title {
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.015em;
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
  .setx-me-text,
  .setx-ver-text,
  .setx-foot {
    display: none;
  }
  .setx-cat.is-me {
    padding: 4px;
    background: none;
    box-shadow: none;
  }
  .setx-cat.is-me.is-active .setx-me-pic {
    box-shadow: 0 0 0 2px rgb(var(--c-accent));
  }
  .setx-me-pic {
    width: 34px;
    height: 34px;
  }
  .setx-ver {
    padding: 6px;
    background: none;
  }
  .setx-head {
    padding: 16px;
  }
  .setx-head .setx-tile.is-big {
    width: 46px;
    height: 46px;
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
