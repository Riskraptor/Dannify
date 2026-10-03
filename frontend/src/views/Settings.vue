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
      <section v-show="showPane('general')">
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
        <label v-if="account.signedIn.value" class="row">
          <Icon icon="ph:clock-counter-clockwise" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('account.sendHistory') }}</p>
            <p class="row-hint">{{ t('account.sendHistoryHint') }}</p>
          </div>
          <input
            type="checkbox"
            class="switch"
            :checked="account.sendHistory.value"
            @change="account.setSendHistory($event.target.checked)"
          />
        </label>
      </section>

      <!-- Appearance -->
      <section v-show="showPane('appearance')">
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
              @click="restyle(() => theme.setPreference(opt.value), $event.currentTarget)"
            >
              <Icon :icon="opt.icon" class="h-4 w-4" />
              {{ t(opt.label) }}
            </button>
          </div>
        </div>
        <!-- Interface size. This was Ctrl with plus and minus, and Ctrl with
             the scroll wheel, which is how a browser behaves and made the app
             feel like a page rather than a program. It is a choice you make
             once, here. -->
        <div class="row">
          <Icon icon="ph:text-aa" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.uiScale') }}</p>
            <p class="row-hint">{{ t('settings.uiScaleHint') }}</p>
          </div>
          <div class="seg" role="radiogroup" :aria-label="t('settings.uiScale')">
            <button
              v-for="step in zoomSteps"
              :key="step.value"
              class="seg-item"
              role="radio"
              :aria-checked="zoom === step.value"
              :class="{ 'is-active': zoom === step.value }"
              :title="`${Math.round(step.value * 100)}%`"
              @click="pickZoom(step.value, $event.currentTarget)"
            >
              <span class="zoom-glyph" :style="{ fontSize: `${10 + (step.value - 0.9) * 16}px` }">Aa</span>
              {{ t(step.label) }}
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
          <!-- One palette for each side, each remembered: the side on screen
               now says so, and the other shows what it will come back to. -->
          <div class="palette-sides">
            <div
              v-for="side in paletteSides"
              :key="side.mode"
              class="palette-side"
              :class="{ 'is-now': theme.currentMode.value === side.mode }"
            >
              <p class="palette-side-label">
                <Icon :icon="side.icon" class="h-3.5 w-3.5" />
                {{ t(side.label) }}
                <span v-if="theme.currentMode.value === side.mode" class="palette-side-now">
                  {{ t('settings.paletteOnScreen') }}
                </span>
              </p>
              <div class="palette-grid">
                <button
                  v-for="p in side.items"
                  :key="p.id"
                  class="palette press"
                  :class="{
                    'is-active': side.chosen === p.id,
                    'is-live': theme.currentTheme.value === p.id,
                  }"
                  :title="t(p.name)"
                  :aria-pressed="side.chosen === p.id"
                  @click="restyle(() => theme.setTheme(p.id), $event.currentTarget)"
                >
                  <span class="palette-chip" :style="{ background: p.bg }">
                    <span class="palette-dot" :style="{ background: p.accent }" />
                    <Icon v-if="side.chosen === p.id" icon="ph:check-bold" class="palette-tick" />
                  </span>
                  <span class="palette-name">{{ t(p.name) }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
        <label class="row">
          <Icon icon="ph:paint-brush-household" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.matchArt') }}</p>
            <p class="row-hint">{{ t('settings.matchArtHint') }}</p>
          </div>
          <input
            type="checkbox"
            class="switch"
            :checked="accentFromArt"
            @change="restyle(() => setAccentFromArt($event.target.checked), $event.target)"
          />
        </label>
        <!-- Typeface. Two bundled faces plus whatever Windows offers, each
             previewed in itself so the choice is visible rather than a name. -->
        <div class="row is-stacked">
          <Icon icon="ph:text-aa" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.font') }}</p>
            <p class="row-hint">{{ t('settings.fontHint') }}</p>
          </div>
          <div class="font-grid">
            <button
              v-for="f in fonts.fonts"
              :key="f.id"
              class="font-card press"
              :class="{ 'is-active': fonts.current.value === f.id }"
              :aria-pressed="fonts.current.value === f.id"
              @click="restyle(() => fonts.setFont(f.id), $event.currentTarget)"
            >
              <span class="font-sample" :style="{ fontFamily: f.display }">Aa</span>
              <span class="font-meta">
                <span class="font-name" :style="{ fontFamily: f.body }">{{ t(f.name) }}</span>
                <span class="font-note">{{ t(f.note) }}</span>
              </span>
              <Icon
                v-if="fonts.current.value === f.id"
                icon="ph:check-circle-fill"
                class="font-tick"
              />
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
      </section>

      <!-- Windows integration -->
      <section v-if="desktop.isDesktop" v-show="showPane('general')">
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
        <label v-if="desktop.state.autostart && desktop.state.autostart.available" class="row">
          <Icon icon="ph:power" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.autostart') }}</p>
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

      <!-- Playback -->
      <section v-show="showPane('playback')">
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
        <label class="row">
          <Icon icon="ph:equalizer" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.normalize') }}</p>
            <p class="row-hint">{{ t('settings.normalizeHint') }}</p>
          </div>
          <input
            type="checkbox"
            class="switch"
            :checked="player.normalizeLoudness.value"
            @change="player.setNormalizeLoudness($event.target.checked)"
          />
        </label>
        <div v-if="player.normalizeLoudness.value" class="row">
          <Icon icon="ph:speaker-simple-high" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.volumeLevel') }}</p>
            <p class="row-hint">{{ t('settings.volumeLevelHint') }}</p>
          </div>
          <div class="seg" role="radiogroup" :aria-label="t('settings.volumeLevel')">
            <button
              v-for="level in ['quiet', 'normal', 'loud']"
              :key="level"
              class="seg-item"
              role="radio"
              :aria-checked="player.volumeLevel.value === level"
              :class="{ 'is-active': player.volumeLevel.value === level }"
              @click="player.setVolumeLevel(level)"
            >
              {{ t(`settings.level.${level}`) }}
            </button>
          </div>
        </div>
        <template v-if="engineOn">
          <div class="row">
            <Icon icon="ph:intersect" class="row-icon" />
            <div class="row-text">
              <p class="row-label">{{ t('settings.crossfade') }}</p>
              <p class="row-hint">{{ t('settings.crossfadeHint') }}</p>
            </div>
            <div class="xf">
              <RangeSlider
                class="xf-slider"
                :value="player.crossfade.value / 12"
                :step="1 / 12"
                :label="t('settings.crossfade')"
                :tooltip="(r) => crossfadeLabel(Math.round(r * 12))"
                @input="(v) => player.setCrossfade(Math.round(v * 12))"
              />
              <span class="xf-value">{{ crossfadeLabel(player.crossfade.value) }}</span>
            </div>
          </div>
          <label class="row" :class="{ 'is-disabled': player.crossfade.value > 0 }">
            <Icon icon="ph:infinity" class="row-icon" />
            <div class="row-text">
              <p class="row-label">{{ t('settings.gapless') }}</p>
              <p class="row-hint">
                {{ player.crossfade.value > 0 ? t('settings.gaplessWithCrossfade') : t('settings.gaplessHint') }}
              </p>
            </div>
            <input
              type="checkbox"
              class="switch"
              :disabled="player.crossfade.value > 0"
              :checked="player.gapless.value || player.crossfade.value > 0"
              @change="player.setGapless($event.target.checked)"
            />
          </label>
          <label class="row">
            <Icon icon="ph:sliders-horizontal" class="row-icon" />
            <div class="row-text">
              <p class="row-label">{{ t('settings.equalizer') }}</p>
              <p class="row-hint">{{ t('settings.equalizerHint') }}</p>
            </div>
            <input
              type="checkbox"
              class="switch"
              :checked="player.eq.value.on"
              @change="player.setEqEnabled($event.target.checked)"
            />
          </label>
          <div v-if="player.eq.value.on" class="row eq">
            <EqGraph
              class="eq-curve"
              :on="player.eq.value.on"
              :gains="player.eq.value.gains"
              @band="(i, db) => player.setEqBand(i, db)"
            />
            <div class="eq-presets" role="radiogroup" :aria-label="t('settings.equalizer')">
              <button
                v-for="name in eqPresetNames"
                :key="name"
                class="eq-chip"
                role="radio"
                :aria-checked="player.eq.value.preset === name"
                :class="{ 'is-active': player.eq.value.preset === name }"
                @click="player.setEqPreset(name)"
              >
                {{ t(`settings.eqPreset.${name}`) }}
              </button>
              <span v-if="player.eq.value.preset === 'custom'" class="eq-chip is-active">
                {{ t('settings.eqPreset.custom') }}
              </span>
              <button
                v-if="player.eq.value.preset !== 'flat'"
                class="eq-chip eq-reset"
                :title="t('settings.eqReset')"
                @click="player.setEqPreset('flat')"
              >
                <Icon icon="ph:arrow-counter-clockwise" class="h-3.5 w-3.5" />
                {{ t('settings.eqReset') }}
              </button>
            </div>
            <div class="eq-bands">
              <label v-for="(hz, i) in EQ_BANDS" :key="hz" class="eq-band">
                <span class="eq-db">{{ formatDb(player.eq.value.gains[i]) }}</span>
                <input
                  type="range"
                  class="eq-slider"
                  min="-12"
                  max="12"
                  step="0.5"
                  :value="player.eq.value.gains[i]"
                  :aria-label="`${formatHz(hz)} ${formatDb(player.eq.value.gains[i])}`"
                  @input="player.setEqBand(i, $event.target.value)"
                />
                <span class="eq-hz">{{ formatHz(hz) }}</span>
              </label>
            </div>
          </div>
        </template>
        <template v-if="engineOn">
          <div class="row">
            <Icon icon="ph:speaker-simple-x" class="row-icon" />
            <div class="row-text">
              <p class="row-label">{{ t('settings.balance') }}</p>
              <p class="row-hint">{{ t('settings.balanceHint') }}</p>
            </div>
            <div class="xf bal" @dblclick="player.setBalance(0)">
              <span class="bal-side">{{ t('settings.balanceLeft') }}</span>
              <RangeSlider
                class="xf-slider"
                :value="(player.balance.value + 1) / 2"
                :step="0.05"
                :label="t('settings.balance')"
                :tooltip="balanceLabel"
                @input="(v) => player.setBalance(Math.abs(v - 0.5) < 0.03 ? 0 : v * 2 - 1)"
              />
              <span class="bal-side">{{ t('settings.balanceRight') }}</span>
            </div>
          </div>
          <label class="row">
            <Icon icon="ph:ear" class="row-icon" />
            <div class="row-text">
              <p class="row-label">{{ t('settings.mono') }}</p>
              <p class="row-hint">{{ t('settings.monoHint') }}</p>
            </div>
            <input
              type="checkbox"
              class="switch"
              :checked="player.mono.value"
              @change="player.setMono($event.target.checked)"
            />
          </label>
        </template>
        <div v-if="desktop.isDesktop" class="row">
          <Icon icon="ph:headphones" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.outputDevice') }}</p>
            <p class="row-hint">{{ t('settings.outputDeviceHint') }}</p>
          </div>
          <button class="btn" @click="desktop.openSoundSettings()">
            <Icon icon="ph:arrow-square-out" class="h-4 w-4" />
            {{ t('settings.openSoundSettings') }}
          </button>
        </div>
      </section>

      <!-- Library -->
      <section v-show="showPane('library')">
        <h2 class="group-title">{{ t('settings.librarySection') }}</h2>
        <div class="row">
          <Icon icon="ph:folder" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.libraryLocation') }}</p>
            <p class="row-hint selectable truncate font-mono text-[12px]" :title="s.download_dir">
              {{ s.download_dir || t('settings.notSet') }}
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

      <!-- Downloads. How a saved song is kept is the app's business, not a
           setting or something to explain: format, quality and playlist
           files are not offered. -->
      <section v-show="showPane('library')">
        <h2 class="group-title">{{ t('settings.downloadsSection') }}</h2>
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
      </section>

      <!-- Storage -->
      <section v-show="showPane('library')">
        <h2 class="group-title">{{ t('settings.storage') }}</h2>
        <div class="row">
          <Icon icon="ph:hard-drives" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.librarySize') }}</p>
            <p class="row-hint">
              {{
                storage
                  ? t('settings.librarySizeHint', {
                      songs: t('artists.trackCount', { count: storage.songs }),
                      size: formatBytes(storage.bytes),
                      free: formatBytes(storage.free),
                    })
                  : t('settings.librarySizeLoading')
              }}
            </p>
            <div v-if="storage && storage.free" class="usage" aria-hidden="true">
              <span class="usage-fill" :style="{ width: `${usagePct}%` }" />
            </div>
          </div>
        </div>
        <div class="row">
          <Icon icon="ph:broom" class="row-icon" />
          <div class="row-text">
            <p class="row-label">{{ t('settings.clearCaches') }}</p>
            <p class="row-hint">
              {{ t('settings.clearCachesHint', { size: storage ? formatBytes(storage.caches) : '…' }) }}
            </p>
          </div>
          <button class="btn" :disabled="clearing" @click="clearCaches">
            <span v-if="clearing" class="spinner h-4 w-4" />
            {{ t('settings.clearCaches') }}
          </button>
        </div>
      </section>

      <!-- Lyrics -->
      <section v-show="showPane('lyrics')">
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
      <section v-if="support.configured" v-show="showPane('about')">
        <h2 class="group-title">{{ t('support.title') }}</h2>
        <div class="row">
          <Icon icon="ph:coffee" class="row-icon text-accent" />
          <div class="row-text">
            <p class="row-label">{{ t('support.heading') }}</p>
            <p class="row-hint">{{ support.message || t('support.blurb') }}</p>
          </div>
          <button class="btn-accent btn-pill press shrink-0 px-4" @click="donate()">
            <Icon icon="ph:coffee" class="h-4 w-4" />
            {{ t('support.give') }}
          </button>
        </div>
      </section>

      <!-- About -->
      <section v-show="showPane('about')">
        <h2 class="group-title">{{ t('settings.about') }}</h2>
        <div class="row">
          <img src="../assets/dannify.svg" alt="" class="row-icon h-6 w-6 drag-none" />
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
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUpdated, nextTick } from 'vue'
import { Icon } from '@iconify/vue'
import API, { appVersion } from '/src/model/api'
import { useSettingsManager } from '/src/model/settings'
import { useTheme } from '/src/model/theme'
import { accentFromArt, setAccentFromArt } from '/src/model/artAccent'
import { useFonts } from '/src/model/fonts'
import { useUi } from '/src/model/ui'
import { usePlayer } from '/src/model/player'
import { EQ_BANDS, EQ_PRESETS } from '/src/model/audioEngine'
import RangeSlider from '/src/components/ui/RangeSlider.vue'
import EqGraph from '/src/components/ui/EqGraph.vue'
import { useAccount } from '/src/model/account'
import { useUpdates } from '/src/model/updates'
import { useConnectivity } from '/src/model/connectivity'
import { desktop } from '/src/desktop/bridge'
import { ZOOM_STEPS, currentZoom, setZoom } from '/src/desktop/shortcuts'
import { toast } from '/src/model/toast'
import { useReporting } from '/src/model/problems'
import { restyle, resize } from '/src/model/smoothChange'
import { useSupport } from '/src/model/support'
import { useI18n } from '/src/i18n'
import ViewHeader from '/src/components/ui/ViewHeader.vue'

const { t, locale, setLocale, locales } = useI18n()
const sm = useSettingsManager()
const theme = useTheme()
const fonts = useFonts()
const ui = useUi()
const player = usePlayer()
const account = useAccount()
const updates = useUpdates()
const connectivity = useConnectivity()
const s = computed(() => sm.settings.value)

const version = appVersion

// "Report a problem": written and sent in the app (model/problems.js).
const reporting = useReporting()

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
// Interface size lives here now, not on Ctrl and the scroll wheel. Named,
// with a sample drawn at each size: a list of percentages said nothing about
// what each would look like.
const ZOOM_NAMES = {
  0.9: 'settings.uiScaleCompact',
  1: 'settings.uiScaleDefault',
  1.1: 'settings.uiScaleComfortable',
  1.25: 'settings.uiScaleLarge',
}
const zoomSteps = ZOOM_STEPS.map((value) => ({
  value,
  label: ZOOM_NAMES[value] || `${Math.round(value * 100)}%`,
}))
const zoom = ref(currentZoom())
// The palettes, by the side they are for.
const paletteSides = computed(() => [
  {
    mode: 'dark',
    label: 'settings.paletteDark',
    icon: 'ph:moon',
    items: theme.themes.filter((p) => p.mode === 'dark'),
    chosen: theme.darkTheme.value,
  },
  {
    mode: 'light',
    label: 'settings.paletteLight',
    icon: 'ph:sun',
    items: theme.themes.filter((p) => p.mode === 'light'),
    chosen: theme.lightTheme.value,
  },
])

function pickZoom(step, anchor) {
  if (step === zoom.value) return
  const from = zoom.value
  zoom.value = step
  resize(() => setZoom(step), from, step, anchor)
}

// The notes come back as one block of text. Split it for reading, and never
// render it as markup: it arrives over the network.
const noteLines = computed(() =>
  String(updates.info.value.notes || '')
    .split(/\r?\n+/)
    .map((l) => l.replace(/^[#*\-\s]+/, '').trim())
    .filter(Boolean)
    .slice(0, 12)
)

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

watch(pane, (id) => {
  try {
    localStorage.setItem(PANE_KEY, id)
  } catch {
    // storage blocked: the choice just won't survive a restart
  }
})

const updateHint = computed(() => {
  if (updates.downloading.value) {
    return t('update.downloading', { percent: Math.round(updates.progress.value) })
  }
  if (updates.available.value) {
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
const { config: support, openSupport: donate } = useSupport()

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

// ----- Storage --------------------------------------------------------------
const storage = ref(null)
const clearing = ref(false)
const usagePct = computed(() => {
  const st = storage.value
  if (!st || !st.free) return 0
  return Math.max(1, Math.min(100, (st.bytes / (st.bytes + st.free)) * 100))
})

function formatBytes(n) {
  const value = Number(n) || 0
  if (value < 1024 * 1024) return `${Math.max(0, Math.round(value / 1024))} KB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(value < 10 * 1024 ** 2 ? 1 : 0)} MB`
  return `${(value / 1024 ** 3).toFixed(1)} GB`
}

async function loadStorage() {
  try {
    const res = await API.getStorage()
    storage.value = res.data || null
  } catch {
    storage.value = null
  }
}

async function clearCaches() {
  clearing.value = true
  try {
    await API.clearCaches()
    // The size beside the button drops to nothing: that is the answer.
    loadStorage()
  } catch {
    toast(t('settings.clearFailed'), { tone: 'error' })
  } finally {
    clearing.value = false
  }
}

// Measured when its pane is opened, not on every visit to Settings: it walks
// the whole music folder.
watch(
  () => pane.value === 'library' || searching.value,
  (need) => {
    if (need && !storage.value) loadStorage()
  },
  { immediate: true }
)

async function changeFolder() {
  const path = await sm.pickDownloadFolder()
  if (path) {
    // The new folder is written right there in the row.
    storage.value = null
    loadStorage()
  }
}

// Tray behaviour lives in the native shell's config.
const tray = reactive({ closeToTray: false })

// --- The sound engine's settings (see audioEngine.js) ---
const engineOn = player.hasEngine()
const eqPresetNames = Object.keys(EQ_PRESETS)
function crossfadeLabel(seconds) {
  return seconds > 0 ? t('settings.seconds', { count: seconds }) : t('settings.crossfadeOff')
}
function formatDb(db) {
  const v = Number(db) || 0
  return `${v > 0 ? '+' : ''}${v % 1 ? v.toFixed(1) : v} dB`
}
function balanceLabel(r) {
  const v = Math.round((r * 2 - 1) * 100)
  if (Math.abs(v) < 3) return t('settings.balanceCentre')
  return v < 0 ? `${t('settings.balanceLeft')} ${-v}%` : `${t('settings.balanceRight')} ${v}%`
}

function formatHz(hz) {
  return hz >= 1000 ? `${hz / 1000}k` : String(hz)
}

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

<style scoped>
/* Crossfade: a short slider with its value beside it. */
.xf {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 220px;
  max-width: 100%;
}
.xf-slider {
  flex: 1;
}
.xf-value {
  min-width: 34px;
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
  text-align: right;
  color: rgb(var(--c-fg) / 0.7);
}
/* Equalizer: presets as chips, then ten upright sliders. */
.row.eq {
  flex-direction: column;
  align-items: stretch;
  gap: 16px;
}
/* The rule that sends a row's control to the right would bunch the bands
   up against the edge: here they span the card. */
.row.row.eq > .eq-presets,
.row.row.eq > .eq-bands {
  margin-left: 0;
  flex-shrink: 1;
}
.eq-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.eq-chip {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.07);
  font-size: 12.5px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.75);
}
.eq-chip:hover {
  background: rgb(var(--c-tint) / 0.12);
  color: rgb(var(--c-fg));
}
.eq-chip.is-active {
  background: rgb(var(--c-accent));
  color: rgb(var(--c-on-accent, 0 0 0));
}
.eq-bands {
  display: grid;
  grid-template-columns: repeat(10, minmax(0, 1fr));
  gap: 4px;
}
.eq-band {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  font-variant-numeric: tabular-nums;
}
.eq-slider {
  writing-mode: vertical-lr;
  direction: rtl;
  width: 22px;
  height: 120px;
  accent-color: rgb(var(--c-accent));
  cursor: pointer;
}
.eq-db {
  font-size: 10.5px;
  color: rgb(var(--c-fg) / 0.7);
  white-space: nowrap;
}
.eq-hz {
  font-size: 11px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.55);
}

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
  color: rgb(var(--c-fg) / 0.45);
  pointer-events: none;
}
.set-nav.is-muted {
  opacity: 0.5;
}
.set-empty {
  padding: 28px 4px;
  font-size: 14px;
  color: rgb(var(--c-fg) / 0.6);
}
/* A row or a group the search left out. `hidden` alone loses to the display
   the rows set for themselves. */
.set-pane :deep([hidden]) {
  display: none !important;
}
.zoom-glyph {
  font-weight: 700;
  line-height: 1;
  opacity: 0.8;
}
.usage {
  margin-top: 8px;
  height: 5px;
  max-width: 320px;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.12);
  overflow: hidden;
}
.usage-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: rgb(var(--c-accent));
  transition: width 0.4s var(--ease-out);
}
.settings {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  align-items: start;
  gap: 28px;
  max-width: 1040px;
}
.up-notes {
  margin-top: 8px;
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid rgb(var(--c-tint) / 0.1);
  background: rgb(var(--c-tint) / 0.04);
  display: grid;
  gap: 8px;
  font-size: 14px;
  line-height: 1.55;
  color: rgb(var(--c-fg) / 0.72);
}
.up-notes-head {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / 0.5);
}
.up-flow {
  margin-top: 8px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgb(var(--c-tint) / 0.05);
}
.up-line {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  font-size: 12.5px;
  font-weight: 600;
}
.up-pct {
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-fg) / 0.6);
}
.up-track {
  margin-top: 8px;
  height: 6px;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.14);
  overflow: hidden;
}
.up-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: rgb(var(--c-accent));
  transition: width 0.25s var(--ease-out);
}
.up-note {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: rgb(var(--c-fg) / 0.55);
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
.font-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 10px;
  width: 100%;
}
.font-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 13px;
  border-radius: 11px;
  border: 1px solid rgb(var(--c-tint) / 0.1);
  background: rgb(var(--c-tint) / 0.03);
  text-align: left;
  transition:
    border-color 0.15s ease,
    background 0.15s ease;
}
.font-card:hover {
  background: rgb(var(--c-tint) / 0.06);
}
.font-card.is-active {
  border-color: rgb(var(--c-accent) / 0.55);
  background: rgb(var(--c-accent) / 0.07);
}
/* The sample is set in the face it names: the point is to see it. */
.font-sample {
  flex: none;
  width: 38px;
  font-size: 26px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: -0.02em;
  color: rgb(var(--c-fg) / 0.9);
}
.font-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.font-name {
  font-size: 13px;
  font-weight: 700;
}
.font-note {
  font-size: 11.5px;
  line-height: 1.35;
  color: rgb(var(--c-fg) / 0.55);
}
.font-tick {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 15px;
  height: 15px;
  color: rgb(var(--c-accent));
}

.palette-sides {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
}
.palette-side-label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px 2px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / 0.5);
}
.palette-side.is-now .palette-side-label {
  color: rgb(var(--c-fg) / 0.78);
}
.palette-side-now {
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 10px;
  letter-spacing: 0.02em;
  text-transform: none;
  color: rgb(var(--c-accent));
  background: rgb(var(--c-accent) / 0.12);
}
.palette-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
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
/* Chosen for its side: a thin ring. On screen now: the full one. */
.palette.is-active .palette-chip {
  border-color: rgb(var(--c-tint) / 0.4);
}
.palette.is-live .palette-chip {
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
[data-mode='light'] .row {
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
.soon-pill {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 8px;
  border-radius: 999px;
  vertical-align: 1px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: rgb(var(--c-accent));
  background: rgb(var(--c-accent) / 0.12);
}
.eq-curve {
  margin-bottom: 12px;
}
.eq-reset {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.bal {
  gap: 10px;
}
.bal-side {
  font-size: 11px;
  font-weight: 700;
  color: rgb(var(--c-fg) / 0.45);
}
</style>
