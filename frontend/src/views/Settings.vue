<template>
  <div class="pb-14">
    <ViewHeader :title="t('settings.title')" :subtitle="t('settings.subtitle')">
      <template #actions>
        <transition name="fade">
          <span v-if="showSaved" class="pill-accent h-7 px-3 text-xs">
            <Icon icon="ph:check-bold" class="h-3.5 w-3.5" />
            {{ t('settings.saved') }}
          </span>
        </transition>
      </template>
    </ViewHeader>

    <div class="settings view-pad">
      <!-- Account -->
      <section>
        <h2 class="group-title">{{ t('account.title') }}</h2>
        <div class="row">
          <img
            v-if="account.profile.value.photo"
            :src="account.profile.value.photo"
            alt=""
            class="row-icon h-9 w-9 rounded-full object-cover"
            referrerpolicy="no-referrer"
          />
          <Icon v-else icon="ph:user-circle" class="row-icon h-9 w-9" />
          <div class="row-text">
            <p class="row-label">
              {{ account.signedIn.value ? account.displayName.value || t('account.connected') : t('account.signedOutTitle') }}
            </p>
            <p class="row-hint">
              {{ account.signedIn.value ? t('account.connectedHint') : t('account.signedOutHint') }}
            </p>
          </div>
          <div class="flex shrink-0 gap-2">
            <button
              v-if="account.signedIn.value"
              class="btn"
              :disabled="account.busy.value"
              @click="account.signOut()"
            >
              {{ t('account.signOut') }}
            </button>
            <button
              v-else
              class="btn-accent btn-pill press px-4"
              :disabled="account.busy.value || !desktop.isDesktop"
              @click="account.signIn()"
            >
              <span v-if="account.busy.value" class="spinner h-4 w-4" />
              <Icon v-else icon="ph:google-logo" class="h-4 w-4" />
              {{ account.busy.value ? t('account.connecting') : t('account.connect') }}
            </button>
          </div>
        </div>
      </section>

      <!-- Appearance -->
      <section>
        <h2 class="group-title">{{ t('settings.appearance') }}</h2>
        <div class="row">
          <Icon icon="ph:palette" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.theme') }}</p>
            <p class="row-hint">{{ t('settings.themeHint') }}</p>
          </div>
          <div class="seg">
            <button
              v-for="opt in themeOptions"
              :key="opt.value"
              class="seg-item"
              :class="{ 'is-active': theme.preference.value === opt.value }"
              @click="theme.setPreference(opt.value)"
            >
              <Icon :icon="opt.icon" class="h-4 w-4" />
              {{ t(opt.label) }}
            </button>
          </div>
        </div>
        <!-- Palette. Separate from light/dark on purpose: picking a dark
             palette and leaving the mode on "System" should still follow
             Windows, into the palettes chosen for each side. -->
        <div class="row is-stacked">
          <Icon icon="ph:swatches" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.palette') }}</p>
            <p class="row-hint">{{ t('settings.paletteHint') }}</p>
          </div>
          <div class="palette-grid">
            <button
              v-for="p in theme.themes"
              :key="p.id"
              class="palette press"
              :class="{ 'is-active': theme.currentTheme.value === p.id }"
              :title="t(p.name)"
              :aria-pressed="theme.currentTheme.value === p.id"
              @click="theme.setTheme(p.id)"
            >
              <span class="palette-chip" :style="{ background: p.bg }">
                <span class="palette-dot" :style="{ background: p.accent }" />
                <Icon
                  v-if="theme.currentTheme.value === p.id"
                  icon="ph:check-bold"
                  class="palette-tick"
                />
              </span>
              <span class="palette-name">{{ t(p.name) }}</span>
            </button>
          </div>
        </div>
        <div class="row">
          <Icon icon="ph:translate" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.language') }}</p>
            <p class="row-hint">{{ t('settings.languageHint') }}</p>
          </div>
          <select class="field-select w-44" :value="locale" @change="setLocale($event.target.value)">
            <option v-for="l in locales" :key="l.code" :value="l.code">{{ l.name }}</option>
          </select>
        </div>
        <label v-if="desktop.isDesktop" class="row">
          <Icon icon="ph:app-window" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.nativeTitleBar') }}</p>
            <p class="row-hint">{{ t('settings.nativeTitleBarHint') }}</p>
          </div>
          <input
            type="checkbox"
            class="switch"
            :checked="nativeFramePref"
            @change="setNativeFrame($event.target.checked)"
          />
        </label>
      </section>

      <!-- Windows integration -->
      <section v-if="desktop.isDesktop">
        <h2 class="group-title">{{ t('settings.windowsSection') }}</h2>
        <label class="row">
          <Icon icon="ph:tray" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.closeToTray') }}</p>
            <p class="row-hint">{{ t('settings.closeToTrayHint') }}</p>
          </div>
          <input
            type="checkbox"
            class="switch"
            :checked="tray.closeToTray"
            @change="setTray({ closeToTray: $event.target.checked })"
          />
        </label>
        <label class="row">
          <Icon icon="ph:arrow-line-down" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.minimizeToTray') }}</p>
            <p class="row-hint">{{ t('settings.minimizeToTrayHint') }}</p>
          </div>
          <input
            type="checkbox"
            class="switch"
            :checked="tray.minimizeToTray"
            @change="setTray({ minimizeToTray: $event.target.checked })"
          />
        </label>
      </section>

      <!-- Playback -->
      <section>
        <h2 class="group-title">{{ t('settings.playback') }}</h2>
        <label class="row">
          <Icon icon="ph:microphone-stage" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.autoOpenLyrics') }}</p>
            <p class="row-hint">{{ t('settings.autoOpenLyricsHint') }}</p>
          </div>
          <input v-model="ui.autoOpenLyrics.value" type="checkbox" class="switch" />
        </label>
        <label class="row">
          <Icon icon="ph:broadcast" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.autoplayRadio') }}</p>
            <p class="row-hint">{{ t('settings.autoplayRadioHint') }}</p>
          </div>
          <input
            type="checkbox"
            class="switch"
            :checked="player.autoplayRadio.value"
            @change="player.setAutoplayRadio($event.target.checked)"
          />
        </label>
      </section>

      <!-- Library -->
      <section>
        <h2 class="group-title">{{ t('settings.librarySection') }}</h2>
        <div class="row">
          <Icon icon="ph:folder" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.libraryLocation') }}</p>
            <p class="row-hint selectable truncate font-mono text-[12px]" :title="s.download_dir">
              {{ s.download_dir || 'Not set' }}
            </p>
          </div>
          <div class="flex shrink-0 gap-2">
            <button v-if="desktop.isDesktop" class="btn" @click="desktop.openLibraryFolder()">
              <Icon icon="ph:folder-open" class="h-4 w-4" />
              {{ t('settings.openFolder') }}
            </button>
            <button class="btn" @click="changeFolder">{{ t('settings.change') }}</button>
          </div>
        </div>
        <label class="row">
          <Icon icon="ph:users-three" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.organizeByArtist') }}</p>
            <p class="row-hint">{{ t('settings.organizeByArtistHint') }}</p>
          </div>
          <input
            type="checkbox"
            class="switch"
            :checked="!!s.organize_by_artist"
            @change="sm.update({ organize_by_artist: $event.target.checked })"
          />
        </label>
      </section>

      <!-- Downloads -->
      <section>
        <h2 class="group-title">{{ t('settings.downloadsSection') }}</h2>
        <div class="row">
          <Icon icon="ph:file-audio" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.format') }}</p>
            <p class="row-hint">{{ t('settings.formatHint') }}</p>
          </div>
          <select class="field-select w-32" :value="s.format" @change="sm.update({ format: $event.target.value })">
            <option v-for="fmt in sm.settingsOptions.format" :key="fmt" :value="fmt">{{ fmt.toUpperCase() }}</option>
          </select>
        </div>
        <div class="row" :class="{ 'is-disabled': s.format === 'flac' }">
          <Icon icon="ph:waveform" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.quality') }}</p>
            <p class="row-hint">
              {{ s.format === 'flac' ? t('settings.qualityIgnored') : t('settings.qualityHint') }}
            </p>
          </div>
          <select
            class="field-select w-32"
            :value="s.bitrate"
            :disabled="s.format === 'flac'"
            @change="sm.update({ bitrate: $event.target.value })"
          >
            <option v-for="b in sm.settingsOptions.bitrate" :key="b" :value="b">{{ b }} kbps</option>
          </select>
        </div>
        <div class="row">
          <Icon icon="ph:stack" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.parallelDownloads') }}</p>
            <p class="row-hint">{{ t('settings.parallelDownloadsHint') }}</p>
          </div>
          <div class="seg">
            <button
              v-for="n in sm.settingsOptions.max_parallel_downloads"
              :key="n"
              class="seg-item min-w-[36px] justify-center"
              :class="{ 'is-active': s.max_parallel_downloads === n }"
              @click="sm.update({ max_parallel_downloads: n })"
            >
              {{ n }}
            </button>
          </div>
        </div>
        <label class="row">
          <Icon icon="ph:playlist" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.generateM3u') }}</p>
            <p class="row-hint">{{ t('settings.generateM3uHint') }}</p>
          </div>
          <input
            type="checkbox"
            class="switch"
            :checked="s.generate_m3u !== false"
            @change="sm.update({ generate_m3u: $event.target.checked })"
          />
        </label>
      </section>

      <!-- Lyrics -->
      <section>
        <h2 class="group-title">{{ t('settings.lyricsGroup') }}</h2>
        <label class="row">
          <Icon icon="ph:text-align-left" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.downloadLyrics') }}</p>
            <p class="row-hint">{{ t('settings.downloadLyricsHint') }}</p>
          </div>
          <input
            type="checkbox"
            class="switch"
            :checked="!!s.download_lyrics"
            @change="sm.update({ download_lyrics: $event.target.checked })"
          />
        </label>
        <div class="row">
          <Icon icon="ph:folders" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.lyricsStorage') }}</p>
            <p class="row-hint">
              {{ s.lyrics_storage === 'central' ? t('settings.lyricsCentralHint') : t('settings.lyricsSidecarHint') }}
            </p>
          </div>
          <div class="seg">
            <button
              class="seg-item"
              :class="{ 'is-active': s.lyrics_storage !== 'central' }"
              @click="sm.setLyricsStorage('sidecar')"
            >
              {{ t('settings.lyricsSidecar') }}
            </button>
            <button
              class="seg-item"
              :class="{ 'is-active': s.lyrics_storage === 'central' }"
              @click="sm.setLyricsStorage('central')"
            >
              {{ t('settings.lyricsCentral') }}
            </button>
          </div>
        </div>
      </section>

      <!-- Support -->
      <section v-if="support.configured">
        <h2 class="group-title">{{ t('support.title') }}</h2>
        <div class="row support-row">
          <Icon icon="ph:heart-fill" class="row-icon text-accent" />
          <div class="row-text">
            <p class="row-label">{{ t('support.heading') }}</p>
            <p class="row-hint">{{ support.message || t('support.blurb') }}</p>
          </div>
          <div class="flex shrink-0 flex-wrap justify-end gap-2">
            <template v-if="!support.payment_link">
              <button
                v-for="amount in support.amounts"
                :key="amount"
                class="btn press"
                @click="donate(amount)"
              >
                {{ support.currency }} {{ amount.toLocaleString() }}
              </button>
            </template>
            <button class="btn-accent btn-pill press px-4" @click="donate(0)">
              <Icon icon="ph:hand-heart" class="h-4 w-4" />
              {{ t('support.give') }}
            </button>
          </div>
        </div>
      </section>

      <!-- About -->
      <section>
        <h2 class="group-title">{{ t('settings.about') }}</h2>
        <div class="row">
          <img src="../assets/dannify.svg" alt="" class="row-icon h-6 w-6 drag-none" />
          <div class="row-text">
            <p class="row-label">Dannify</p>
            <p class="row-hint">{{ t('settings.version', { version }) }}</p>
          </div>
          <button class="btn" @click="desktop.openExternal(updates.repoUrl.value)">
            <Icon icon="ph:github-logo" class="h-4 w-4" />
            {{ t('settings.sourceCode') }}
          </button>
        </div>
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
              <Icon v-else icon="ph:download-simple" class="h-4 w-4" />
              {{ updates.downloading.value
                ? `${Math.round(updates.progress.value)}%`
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
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { useSettingsManager } from '/src/model/settings'
import { useTheme } from '/src/model/theme'
import { useUi } from '/src/model/ui'
import { usePlayer } from '/src/model/player'
import { useAccount } from '/src/model/account'
import { useUpdates } from '/src/model/updates'
import { promptRestart } from '/src/model/restart'
import { desktop } from '/src/desktop/bridge'
import { toast } from '/src/model/toast'
import { useI18n } from '/src/i18n'
import ViewHeader from '/src/components/ui/ViewHeader.vue'

const { t, locale, setLocale, locales } = useI18n()
const sm = useSettingsManager()
const theme = useTheme()
const ui = useUi()
const player = usePlayer()
const account = useAccount()
const updates = useUpdates()
const s = computed(() => sm.settings.value)

const version = ref(localStorage.getItem('version') || '')

const updateHint = computed(() => {
  if (updates.downloading.value) {
    return t('update.downloading', { percent: Math.round(updates.progress.value) })
  }
  if (updates.available.value) {
    return t('update.available', { version: updates.info.value.version })
  }
  if (updates.lastError.value) return t('update.offline')
  return t('update.upToDate', { version: version.value })
})

// --- Support the app (Paystack; configured by the packager, see support.py)
const support = reactive({
  configured: false,
  currency: 'KES',
  amounts: [],
  message: '',
  payment_link: '',
  public_key: '',
  email: '',
})

function donate(amount) {
  if (!support.configured) return
  // A Paystack Payment Page handles the amount itself: just open it.
  if (support.payment_link) {
    desktop.openExternal(support.payment_link)
    return
  }
  const value = amount || support.amounts[1] || support.amounts[0] || 0
  const params = new URLSearchParams({
    key: support.public_key,
    amount: String(value),
    currency: support.currency,
  })
  if (support.email) params.set('email', support.email)
  // Checkout opens in the real browser: card details never touch the app.
  desktop.openExternal(`${location.origin}/support/checkout?${params}`)
}

const themeOptions = [
  { value: 'system', label: 'settings.themeSystem', icon: 'ph:desktop' },
  { value: 'light', label: 'settings.themeLight', icon: 'ph:sun' },
  { value: 'dark', label: 'settings.themeDark', icon: 'ph:moon' },
]

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

async function changeFolder() {
  const path = await sm.pickDownloadFolder()
  if (path) toast(t('settings.folderChanged'), { tone: 'success' })
}

// Title-bar style and tray behaviour live in the native shell's config.
const nativeFramePref = ref(false)
const tray = reactive({ closeToTray: false, minimizeToTray: false })

onMounted(async () => {
  API.getSupportConfig()
    .then((res) => Object.assign(support, res.data || {}))
    .catch(() => {})
  if (!desktop.isDesktop) return
  await desktop.whenReady()
  nativeFramePref.value = !!desktop.state.nativeFramePref
  tray.closeToTray = !!desktop.state.closeToTray
  tray.minimizeToTray = !!desktop.state.minimizeToTray
})

async function setNativeFrame(on) {
  nativeFramePref.value = on
  await desktop.setNativeFrame(on)
  promptRestart(t('settings.restartTitleBar'))
}

async function setTray(patch) {
  Object.assign(tray, patch)
  await desktop.setTray(patch)
}

</script>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: 28px;
  max-width: 980px;
}
.group-title {
  margin: 0 0 8px 2px;
  font-size: 14px;
  font-weight: 600;
}
/* The palette row always stacks: seven swatches never sit sensibly beside a
   label in a pane this narrow. */
.row.is-stacked {
  align-items: flex-start;
}
.row.is-stacked .row-text {
  flex: 1 1 100%;
}
.palette-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(84px, 1fr));
  gap: 10px;
  width: 100%;
}
.palette {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  padding: 4px 2px 6px;
  border-radius: 10px;
}
.palette:hover {
  background: rgb(var(--c-tint) / 0.05);
}
.palette-chip {
  position: relative;
  display: grid;
  place-items: center;
  width: 100%;
  aspect-ratio: 16 / 10;
  border-radius: 9px;
  border: 1px solid rgb(var(--c-tint) / 0.12);
  overflow: hidden;
  transition:
    border-color 0.15s ease,
    transform 0.12s var(--ease-out);
}
.palette:hover .palette-chip {
  transform: translateY(-1px);
}
.palette.is-active .palette-chip {
  border-color: rgb(var(--c-accent));
  box-shadow: 0 0 0 2px rgb(var(--c-accent) / 0.35);
}
/* The accent, shown on the palette's own background: the pairing is the
   thing being chosen, so show the pairing. */
.palette-dot {
  width: 22px;
  height: 22px;
  border-radius: 999px;
}
.palette-tick {
  position: absolute;
  right: 5px;
  bottom: 4px;
  width: 12px;
  height: 12px;
  color: rgb(var(--c-accent));
}
.palette-name {
  font-size: 11.5px;
  font-weight: 600;
  line-height: 1;
  color: rgb(var(--c-fg) / 0.62);
}
.palette.is-active .palette-name {
  color: rgb(var(--c-fg));
}

.row {
  display: flex;
  /* Wrap instead of crushing: with the lyrics panel open the pane can be
     only a few hundred pixels wide, and a squeezed label next to a squeezed
     control reads like a broken layout. Below ~420px of text room the
     control drops onto its own line. */
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 16px;
  min-height: 68px;
  padding: 12px 16px;
  margin-bottom: 3px;
  border-radius: 6px;
  background: rgb(var(--c-tint) / 0.045);
  border: 1px solid rgb(var(--c-tint) / 0.05);
}
.row > .row-icon {
  align-self: flex-start;
  margin-top: 2px;
}
[data-theme='dannify-light'] .row {
  background: rgb(var(--c-raised));
}
label.row:hover {
  background: rgb(var(--c-tint) / 0.07);
}
.row.is-disabled {
  opacity: 0.55;
}
.row-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  color: rgb(var(--c-fg) / 0.75);
}
.row-text {
  flex: 1 1 240px;
  min-width: 0;
}
/* Anything after the label is a control: keep it whole and let it wrap to
   its own line, still right-aligned, rather than shrink to nothing. */
.row > :not(.row-icon):not(.row-text) {
  flex-shrink: 0;
  margin-left: auto;
}
.row-label {
  font-size: 14px;
}
.row-hint {
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.45;
  color: rgb(var(--c-fg) / 0.55);
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
