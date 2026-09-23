<template>
  <footer class="pbar" :class="{ 'is-empty': !cur, 'is-compact': ui.isCompact.value }">
    <!-- Thin progress line for phone-sized layouts -->
    <div v-if="ui.isCompact.value && cur" class="pb-mini-progress">
      <div :style="{ width: `${player.progressPct.value}%` }" />
    </div>

    <!-- LEFT: what's playing -->
    <div class="pb-left" @contextmenu="onTrackMenu">
      <template v-if="cur">
        <button
          class="pb-cover"
          :title="t('player.openNowPlaying')"
          @click="openNowPlaying"
        >
          <CoverImage :src="cur.cover" radius="sm" :size="56" class="h-full w-full" eager />
          <span v-if="player.isBuffering.value" class="pb-cover-overlay is-visible">
            <span class="spinner h-5 w-5 text-white" />
          </span>
          <span v-else class="pb-cover-overlay">
            <Icon icon="ph:caret-up-bold" class="h-5 w-5 text-white" />
          </span>
        </button>
        <div class="min-w-0">
          <button class="pb-title" :title="cur.title" @click="openNowPlaying">
            {{ cur.title }}
          </button>
          <div class="pb-artist">
            <ArtistLinks :artists="row ? row.artists : []" />
          </div>
        </div>
        <button
          v-if="!ui.isCompact.value && videoId"
          class="icon-btn is-round press shrink-0"
          :class="{ 'is-liked': liked }"
          :title="liked ? t('account.removeFromLiked') : t('account.addToLiked')"
          @click="account.toggleLike(row.raw)"
        >
          <Icon :icon="liked ? 'ph:heart-fill' : 'ph:heart'" class="h-[18px] w-[18px]" />
        </button>
        <button
          v-if="!ui.isCompact.value"
          class="icon-btn is-round press shrink-0"
          :class="{ 'is-active': inLibrary }"
          :title="inLibrary ? t('player.inLibrary') : t('player.saveToLibrary')"
          :disabled="inLibrary"
          @click="saveCurrent"
        >
          <Icon
            :icon="inLibrary ? 'ph:check-circle-fill' : 'ph:plus-circle'"
            class="h-[18px] w-[18px]"
          />
        </button>
      </template>
      <div v-else class="pb-idle">
        <span class="pb-idle-art"><Icon icon="ph:music-notes" class="h-5 w-5" /></span>
        <span class="text-[13px] text-fg/45">{{ t('player.nothingPlaying') }}</span>
      </div>
    </div>

    <!-- CENTER: transport + seek -->
    <div class="pb-center">
      <div class="pb-buttons">
        <button
          class="icon-btn is-round"
          :class="{ 'is-active-dot': player.shuffle.value }"
          :disabled="!cur"
          :title="`${player.shuffle.value ? t('player.shuffleOn') : t('player.shuffleOff')} (S)`"
          @click="player.toggleShuffle()"
        >
          <Icon icon="ph:shuffle-bold" class="h-[18px] w-[18px]" />
        </button>
        <button
          class="icon-btn is-round"
          :disabled="!cur"
          :title="`${t('player.previous')} (P)`"
          @click="player.prev()"
        >
          <Icon icon="ph:skip-back-fill" class="h-5 w-5" />
        </button>
        <button
          class="pb-play"
          :disabled="!cur && !player.playlist.value.length"
          :title="`${player.isPlaying.value ? t('player.pause') : t('player.play')} (Space)`"
          @click="player.toggle()"
        >
          <Icon :icon="player.isPlaying.value ? 'ph:pause-fill' : 'ph:play-fill'" class="h-[18px] w-[18px]" />
        </button>
        <button
          class="icon-btn is-round"
          :disabled="!cur"
          :title="`${t('player.next')} (N)`"
          @click="player.next()"
        >
          <Icon icon="ph:skip-forward-fill" class="h-5 w-5" />
        </button>
        <button
          class="icon-btn is-round"
          :class="{ 'is-active-dot': player.repeatMode.value !== 'off' }"
          :disabled="!cur"
          :title="`${repeatTitle} (R)`"
          @click="player.cycleRepeat()"
        >
          <Icon
            :icon="player.repeatMode.value === 'one' ? 'ph:repeat-once-bold' : 'ph:repeat-bold'"
            class="h-[18px] w-[18px]"
          />
        </button>
      </div>
      <div class="pb-seek">
        <span class="pb-time">{{ formatTime(player.currentTime.value) }}</span>
        <RangeSlider
          :value="player.progressPct.value / 100"
          :live="false"
          :disabled="!cur || !player.duration.value"
          :step="5 / Math.max(1, player.duration.value)"
          :label="t('player.seek')"
          :tooltip="(r) => formatTime(r * (player.duration.value || 0))"
          @change="(r) => player.seekRatio(r)"
        />
        <span class="pb-time">{{ formatTime(player.duration.value) }}</span>
      </div>
    </div>

    <!-- RIGHT: panels, volume, window modes -->
    <div class="pb-right">
      <button
        class="icon-btn is-round"
        :class="{ 'is-active-dot': ui.panel.value === 'lyrics' && !onNowPlaying && cur }"
        :disabled="!cur"
        :title="`${t('lyrics.title')} (Ctrl+L)`"
        @click="ui.setPanel('lyrics')"
      >
        <Icon icon="ph:microphone-stage" class="h-[18px] w-[18px]" />
      </button>
      <button
        class="icon-btn is-round"
        :class="{ 'is-active-dot': ui.panel.value === 'queue' && !onNowPlaying && cur }"
        :disabled="!cur && !player.playlist.value.length"
        :title="`${t('player.queue')} (Ctrl+Q)`"
        @click="ui.setPanel('queue')"
      >
        <Icon icon="ph:queue" class="h-[18px] w-[18px]" />
      </button>
      <div class="pb-volume">
        <button
          class="icon-btn is-round"
          :title="`${player.isMuted.value ? t('player.unmute') : t('player.mute')} (M)`"
          @click="player.toggleMute()"
        >
          <Icon :icon="volumeIcon" class="h-[18px] w-[18px]" />
        </button>
        <RangeSlider
          class="pb-vol-slider"
          :value="player.isMuted.value ? 0 : player.volume.value"
          :step="0.05"
          :label="t('player.volume')"
          :tooltip="(r) => `${Math.round(r * 100)}%`"
          @input="(v) => player.setVolume(v)"
        />
      </div>
      <button
        v-if="desktop.isDesktop"
        class="icon-btn is-round"
        :title="`${t('player.miniPlayer')} (Ctrl+Shift+M)`"
        @click="desktop.setMini(true)"
      >
        <Icon icon="ph:picture-in-picture" class="h-[18px] w-[18px]" />
      </button>
      <button
        class="icon-btn is-round"
        :class="{ 'is-active-dot': onNowPlaying }"
        :disabled="!cur"
        :title="`${t('player.openNowPlaying')} (Ctrl+E)`"
        @click="toggleNowPlaying"
      >
        <Icon :icon="onNowPlaying ? 'ph:arrows-in-simple' : 'ph:arrows-out-simple'" class="h-[18px] w-[18px]" />
      </button>
    </div>
  </footer>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import { usePlayer, formatTime } from '/src/model/player'
import { useUi } from '/src/model/ui'
import { useLibraryIndex } from '/src/model/libraryIndex'
import { useAccount } from '/src/model/account'
import { queueRow, trackMenu, isRowDownloaded, downloadRows, songVideoId } from '/src/model/tracks'
import { openContextMenu } from '/src/model/contextMenu'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'
import CoverImage from '../ui/CoverImage.vue'
import ArtistLinks from '../ui/ArtistLinks.vue'
import RangeSlider from '../ui/RangeSlider.vue'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const player = usePlayer()
const ui = useUi()
const account = useAccount()
const libIndex = useLibraryIndex()

const cur = computed(() => player.currentTrack.value)
const row = computed(() =>
  cur.value ? queueRow(cur.value, player.currentIndex.value) : null
)
const onNowPlaying = computed(() => route.name === 'NowPlaying')
const videoId = computed(() => (row.value ? songVideoId(row.value) : ''))
const liked = computed(() => account.isLiked(videoId.value))

const inLibrary = computed(() => {
  // Touch the reactive index so this recomputes after downloads finish.
  void libIndex.byVideoId.value
  return !!row.value && isRowDownloaded(row.value)
})

const repeatTitle = computed(() =>
  player.repeatMode.value === 'one'
    ? t('player.repeatOne')
    : player.repeatMode.value === 'all'
      ? t('player.repeatAll')
      : t('player.repeatOff')
)

const volumeIcon = computed(() => {
  const v = player.isMuted.value ? 0 : player.volume.value
  if (v === 0) return 'ph:speaker-x'
  if (v < 0.5) return 'ph:speaker-low'
  return 'ph:speaker-high'
})

function openNowPlaying() {
  if (!onNowPlaying.value) router.push({ name: 'NowPlaying' })
}
function toggleNowPlaying() {
  if (onNowPlaying.value) router.back()
  else openNowPlaying()
}
function saveCurrent() {
  if (row.value) downloadRows([row.value])
}
function onTrackMenu(e) {
  if (!row.value) return
  openContextMenu(e, trackMenu([row.value], { queue: true }))
}
</script>

<style scoped>
.pbar {
  position: relative;
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(320px, 1.45fr) minmax(180px, 1fr);
  align-items: center;
  gap: 16px;
  height: var(--player-h);
  padding: 0 16px 0 12px;
  background: rgb(var(--c-app));
}
.pb-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.pb-cover {
  position: relative;
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  overflow: hidden;
  border-radius: 4px;
  box-shadow: 0 2px 10px rgb(0 0 0 / 0.35);
}
.pb-cover-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgb(0 0 0 / 0.5);
  opacity: 0;
  transition: opacity 0.12s ease;
}
.pb-cover:hover .pb-cover-overlay,
.pb-cover-overlay.is-visible {
  opacity: 1;
}
.pb-title {
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 600;
  text-align: left;
  color: rgb(var(--c-fg));
}
.pb-title:hover {
  text-decoration: underline;
}
.pb-artist {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12.5px;
  color: rgb(var(--c-fg) / 0.6);
}
.is-liked,
.is-liked:hover {
  color: rgb(var(--c-accent));
}
.pb-idle {
  display: flex;
  align-items: center;
  gap: 12px;
}
.pb-idle-art {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  border-radius: 4px;
  background: rgb(var(--c-tint) / 0.06);
  color: rgb(var(--c-fg) / 0.3);
}
.pb-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.pb-buttons {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pb-play {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  margin: 0 4px;
  border-radius: 999px;
  background: rgb(var(--c-fg));
  color: rgb(var(--c-panel));
  transition: transform 0.1s ease;
}
.pb-play:hover {
  transform: scale(1.06);
}
.pb-play:active {
  transform: scale(0.96);
}
.pb-play:disabled {
  opacity: 0.4;
  transform: none;
}
.pb-seek {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  max-width: 600px;
}
.pb-time {
  min-width: 38px;
  font-size: 11.5px;
  text-align: center;
  color: rgb(var(--c-fg) / 0.55);
  font-variant-numeric: tabular-nums;
}
.pb-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  min-width: 0;
}
.pb-volume {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 132px;
  margin: 0 4px;
}
.pb-vol-slider {
  flex: 1;
}

/* Medium windows: tighten the right side. */
@media (max-width: 1000px) {
  .pbar {
    grid-template-columns: minmax(140px, 1fr) minmax(260px, 1.6fr) auto;
  }
  .pb-volume {
    width: auto;
  }
  .pb-vol-slider {
    display: none;
  }
}

/* Phones (LAN browser): cover + title + play/next only. */
.pbar.is-compact {
  grid-template-columns: minmax(0, 1fr) auto;
  padding: 0 8px;
}
.pbar.is-compact .pb-center {
  order: 2;
}
.pbar.is-compact .pb-seek,
.pbar.is-compact .pb-buttons > :first-child,
.pbar.is-compact .pb-buttons > :last-child,
.pbar.is-compact .pb-right {
  display: none;
}
.pb-mini-progress {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: rgb(var(--c-tint) / 0.12);
}
.pb-mini-progress > div {
  height: 100%;
  background: rgb(var(--c-accent));
}
</style>
