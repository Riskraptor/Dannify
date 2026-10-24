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
          :class="{ 'is-shared': !onNowPlaying }"
          :title="`${t('player.openNowPlaying')} (Ctrl+E)`"
          :aria-label="t('player.openNowPlaying')"
          data-tour="np-cover"
          @click="openNowPlaying"
        >
          <CoverImage :src="cur.cover" radius="sm" :size="56" class="h-full w-full" eager />
          <span v-if="player.isBuffering.value" class="pb-cover-overlay is-visible">
            <span class="spinner h-5 w-5 text-white" />
          </span>
          <span v-else class="pb-cover-overlay">
            <Icon icon="ph:arrows-out-simple-bold" class="h-5 w-5 text-white" />
          </span>
        </button>
        <!-- Once, for whoever has never opened the big player: where it is. -->
        <Transition name="pb-hint">
          <button v-if="showHint" class="pb-hint" @click="openNowPlaying">
            <Icon icon="ph:arrows-out-simple-bold" class="h-3.5 w-3.5" />
            {{ t('player.hintNowPlaying') }}
          </button>
        </Transition>
        <div class="min-w-0">
          <button class="pb-title" :title="cur.title" @click="openNowPlaying">
            {{ cur.title }}
          </button>
          <div class="pb-artist">
            <ArtistLinks :artists="row ? row.artists : []" />
          </div>
        </div>
        <button
          v-if="!ui.isCompact.value && videoId && !onNowPlaying"
          class="icon-btn is-round press shrink-0 pb-like"
          :class="{ 'is-liked': liked }"
          :title="liked ? t('account.removeFromLiked') : t('account.addToLiked')"
          :aria-label="liked ? t('account.removeFromLiked') : t('account.addToLiked')"
          :aria-pressed="liked"
          @click="account.toggleLike(row.raw)"
        >
          <Icon :icon="liked ? 'ph:heart-fill' : 'ph:heart'" class="h-[18px] w-[18px]" />
        </button>
        <!-- A download arrow, filled once saved, a ring while it saves. A
             green tick beside the heart read as a second "liked", not as
             "on this PC". -->
        <SaveSongButton v-if="!ui.isCompact.value && !onNowPlaying" :row="row" class="shrink-0 pb-save" />
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
          :aria-label="player.shuffle.value ? t('player.shuffleOn') : t('player.shuffleOff')"
          :aria-pressed="player.shuffle.value"
          aria-keyshortcuts="S"
          @click="player.toggleShuffle()"
        >
          <Icon icon="ph:shuffle-bold" class="h-[18px] w-[18px]" />
        </button>
        <button
          class="icon-btn is-round"
          :disabled="!cur"
          :title="`${t('player.previous')} (P)`"
          :aria-label="t('player.previous')"
          aria-keyshortcuts="P"
          @click="player.prev()"
        >
          <Icon icon="ph:skip-back-fill" class="h-5 w-5" />
        </button>
        <button
          class="pb-play"
          :disabled="!cur && !player.playlist.value.length"
          :title="`${player.isPlaying.value ? t('player.pause') : t('player.play')} (Space)`"
          :aria-label="player.isPlaying.value ? t('player.pause') : t('player.play')"
          aria-keyshortcuts="Space"
          @click="player.toggle()"
        >
          <Icon :icon="player.isPlaying.value ? 'ph:pause-fill' : 'ph:play-fill'" class="h-[18px] w-[18px]" />
        </button>
        <button
          class="icon-btn is-round"
          :disabled="!cur"
          :title="nextTitle"
          :aria-label="t('player.next')"
          aria-keyshortcuts="N"
          @click="player.next()"
        >
          <Icon icon="ph:skip-forward-fill" class="h-5 w-5" />
        </button>
        <button
          class="icon-btn is-round"
          :class="{ 'is-active-dot': player.repeatMode.value !== 'off' }"
          :disabled="!cur"
          :title="`${repeatTitle} (R)`"
          :aria-label="repeatTitle"
          :aria-pressed="player.repeatMode.value !== 'off'"
          aria-keyshortcuts="R"
          @click="player.cycleRepeat()"
        >
          <Icon
            :icon="player.repeatMode.value === 'one' ? 'ph:repeat-once-bold' : 'ph:repeat-bold'"
            class="h-[18px] w-[18px]"
          />
        </button>
      </div>
      <div class="pb-seek" @wheel="onSeekWheel">
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
        class="icon-btn is-round pb-more"
        :class="{ 'is-on': player.sleepMode.value !== 'off' }"
        :title="t('actions.more')"
        :aria-label="t('actions.more')"
        aria-haspopup="menu"
        @click="onMoreMenu"
      >
        <Icon icon="ph:dots-three-outline" class="h-[18px] w-[18px]" />
      </button>
      <button
        class="icon-btn is-round pb-sleep pb-extra"
        :class="{ 'is-on': player.sleepMode.value !== 'off' }"
        :title="sleepTitle"
        :aria-label="sleepTitle"
        aria-haspopup="menu"
        @click="onSleepMenu"
      >
        <Icon :icon="player.sleepMode.value !== 'off' ? 'ph:moon-fill' : 'ph:moon'" class="h-[18px] w-[18px]" />
        <span v-if="sleepLeft" class="pb-sleep-left">{{ sleepLeft }}</span>
      </button>
      <button
        class="icon-btn is-round pb-extra"
        :class="{ 'is-active-dot': ui.panel.value === 'about' && !onNowPlaying && cur }"
        :disabled="!cur"
        :title="t('panel.aboutButton')"
        :aria-label="t('panel.aboutButton')"
        :aria-pressed="ui.panel.value === 'about' && !onNowPlaying && !!cur"
        @click="ui.setPanel('about')"
      >
        <Icon icon="ph:vinyl-record" class="h-[18px] w-[18px]" />
      </button>
      <button
        class="icon-btn is-round"
        :class="{ 'is-active-dot': shows('lyrics') }"
        :disabled="!cur"
        :title="`${t('lyrics.title')} (Ctrl+L)`"
        :aria-label="t('lyrics.title')"
        :aria-pressed="shows('lyrics')"
        aria-keyshortcuts="Control+L"
        @click="ui.showPane('lyrics', onNowPlaying)"
      >
        <Icon icon="ph:microphone-stage" class="h-[18px] w-[18px]" />
      </button>
      <button
        class="icon-btn is-round"
        :class="{ 'is-active-dot': shows('queue') }"
        :disabled="!cur && !player.playlist.value.length"
        :title="`${t('player.queue')} (Ctrl+Q)`"
        :aria-label="t('player.queue')"
        :aria-pressed="shows('queue')"
        aria-keyshortcuts="Control+Q"
        @click="ui.showPane('queue', onNowPlaying)"
      >
        <Icon icon="ph:queue" class="h-[18px] w-[18px]" />
      </button>
      <button
        ref="soundBtn"
        class="icon-btn is-round"
        :class="{ 'is-active-dot': soundOpen || player.eq.value.on }"
        :title="t('sound.title')"
        :aria-label="t('sound.title')"
        :aria-expanded="soundOpen"
        aria-haspopup="dialog"
        @click="soundOpen = !soundOpen"
      >
        <Icon icon="ph:sliders-horizontal" class="h-[18px] w-[18px]" />
      </button>
      <SoundPanel v-if="soundWanted" :open="soundOpen" :anchor="soundBtn" @close="soundOpen = false" />
      <div class="pb-volume" @wheel="onVolumeWheel">
        <button
          class="icon-btn is-round"
          :title="`${player.isMuted.value ? t('player.unmute') : t('player.mute')} (M)`"
          :aria-label="player.isMuted.value ? t('player.unmute') : t('player.mute')"
          aria-keyshortcuts="M"
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
        class="icon-btn is-round pb-extra pb-mini"
        :title="`${t('player.miniPlayer')} (Ctrl+Shift+M)`"
        :aria-label="t('player.miniPlayer')"
        aria-keyshortcuts="Control+Shift+M"
        @click="desktop.setMini(true)"
      >
        <Icon icon="ph:picture-in-picture" class="h-[18px] w-[18px]" />
      </button>
      <button
        class="icon-btn is-round"
        :class="{ 'is-active-dot': onNowPlaying }"
        :disabled="!cur"
        :title="`${t('player.openNowPlaying')} (Ctrl+E)`"
        :aria-label="t('player.openNowPlaying')"
        :aria-pressed="onNowPlaying"
        aria-keyshortcuts="Control+E"
        data-tour="np-button"
        @click="toggleNowPlaying"
      >
        <Icon :icon="onNowPlaying ? 'ph:arrows-in-simple' : 'ph:arrows-out-simple'" class="h-[18px] w-[18px]" />
      </button>
    </div>
  </footer>
</template>

<script setup>
import { computed, defineAsyncComponent, ref, watch, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import { usePlayer, formatTime } from '/src/model/player'
import { useUi } from '/src/model/ui'
import { useAccount } from '/src/model/account'
import { queueRow, trackMenu, songVideoId } from '/src/model/tracks'
import { openContextMenu, openMenuAt, lastMenuPoint } from '/src/model/contextMenu'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'
import { nowPlayingSeen, openNowPlaying, closeNowPlaying, toggleNowPlaying } from '/src/model/nowPlaying'
import CoverImage from '../ui/CoverImage.vue'
import ArtistLinks from '../ui/ArtistLinks.vue'
import RangeSlider from '../ui/RangeSlider.vue'
import SaveSongButton from '/src/components/ui/SaveSongButton.vue'
// The sound panel and its equaliser are fetched when first opened, and
// quietly a little after start, so that first opening is still instant.
const loadSoundPanel = () => import('./SoundPanel.vue')
const SoundPanel = defineAsyncComponent(loadSoundPanel)

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const player = usePlayer()
const ui = useUi()
const account = useAccount()

const cur = computed(() => player.currentTrack.value)

// --- Sleep timer ---
// A clock for the minutes left, ticking only while a timer is set.
const now = ref(Date.now())
// The sound panel (SoundPanel.vue), from its button beside the volume.
const soundOpen = ref(false)
// Drawn from its first opening on, so closing can animate.
const soundWanted = ref(false)
watch(soundOpen, (on) => on && (soundWanted.value = true))
if (typeof window !== 'undefined') {
  const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 1500))
  setTimeout(() => idle(() => loadSoundPanel().catch(() => {}), { timeout: 5000 }), 3500)
}
const soundBtn = ref(null)
let sleepTick = 0
watch(
  () => player.sleepMode.value,
  (mode) => {
    clearInterval(sleepTick)
    now.value = Date.now()
    if (mode === 'time') sleepTick = setInterval(() => (now.value = Date.now()), 15000)
  },
  { immediate: true }
)
onBeforeUnmount(() => clearInterval(sleepTick))
const sleepMinutes = computed(() =>
  player.sleepMode.value === 'time' ? Math.max(1, Math.ceil((player.sleepEndsAt.value - now.value) / 60000)) : 0
)
const sleepLeft = computed(() => (sleepMinutes.value ? String(sleepMinutes.value) : ''))
const sleepTitle = computed(() => {
  if (player.sleepMode.value === 'time') return t('player.sleepStopsIn', { count: sleepMinutes.value })
  if (player.sleepMode.value === 'track') return t('player.sleepAfterSong')
  return t('player.sleep')
})
function sleepItems() {
  const mode = player.sleepMode.value
  return [
      { header: mode === 'off' ? t('player.sleep') : sleepTitle.value },
      ...[15, 30, 45, 60, 90].map((m) => ({
        label: t('player.sleepMinutes', { count: m }),
        icon: 'ph:timer',
        action: () => player.setSleepTimer(m),
      })),
      {
        label: t('player.sleepEndOfSong'),
        icon: 'ph:music-note',
        checked: mode === 'track',
        disabled: !cur.value,
        action: () => player.setSleepAfterTrack(),
      },
      { divider: true },
      { label: t('player.sleepOff'), icon: 'ph:x', disabled: mode === 'off', action: () => player.cancelSleep() },
  ]
}
function onSleepMenu(e) {
  openContextMenu(e, sleepItems(), { anchor: true })
}
// Narrow windows: what does not fit beside the volume, one click away.
// More: everything about the song playing (like it, add it to a playlist,
// its radio, artist and album, its link), then what the player itself can
// do. It held three things and read as where things were hidden.
function onMoreMenu(e) {
  openContextMenu(
    e,
    [
      ...(row.value ? trackMenu([row.value], { queue: true, playing: true }) : []),
      { divider: true },
      {
        label: player.sleepMode.value === 'off' ? t('player.sleep') : sleepTitle.value,
        icon: player.sleepMode.value === 'off' ? 'ph:moon' : 'ph:moon-fill',
        // Its own choices, where this menu was.
        action: () => setTimeout(() => openMenuAt(lastMenuPoint(), sleepItems())),
      },
      {
        label: t('sound.title'),
        icon: 'ph:sliders-horizontal',
        action: () => setTimeout(() => (soundOpen.value = true)),
      },
      {
        label: t('player.aboutSong'),
        icon: 'ph:vinyl-record',
        disabled: !cur.value,
        action: () => {
          // Now Playing has no room for it: the side panel, beside the page
          // that was there before.
          if (onNowPlaying.value) closeNowPlaying()
          ui.openPanel('about')
        },
      },
      desktop.isDesktop && {
        label: t('player.miniPlayer'),
        icon: 'ph:picture-in-picture',
        shortcut: 'Ctrl+Shift+M',
        action: () => desktop.setMini(true),
      },
    ],
    { anchor: true }
  )
}
const row = computed(() =>
  cur.value ? queueRow(cur.value, player.currentIndex.value) : null
)
const onNowPlaying = computed(() => route.name === 'NowPlaying')
// Lit for what is on screen: the side panel's tab, or on Now Playing its own.
function shows(name) {
  if (!cur.value) return false
  return onNowPlaying.value ? ui.npTab.value === name : ui.panel.value === name
}
const videoId = computed(() => (row.value ? songVideoId(row.value) : ''))
const liked = computed(() => account.isLiked(videoId.value))


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

// "Next: Chikwere · Bien", when there is a next.
const nextTitle = computed(() => {
  const at = player.upcoming.value[0]
  const next = at != null ? player.playlist.value[at] : null
  if (!next || !next.title) return `${t('player.next')} (N)`
  return `${t('player.nextIs', { title: next.title, artist: next.artist || '' })} (N)`
})

// The wheel over the song's bar moves through it five seconds a notch; over
// the volume, five per cent.
function onSeekWheel(e) {
  if (!cur.value || !player.duration.value) return
  e.preventDefault()
  const step = e.deltaY < 0 ? 5 : -5
  player.seek(Math.max(0, Math.min(player.duration.value - 1, (player.currentTime.value || 0) + step)))
}
function onVolumeWheel(e) {
  e.preventDefault()
  const v = player.isMuted.value ? 0 : player.volume.value
  player.setVolume(Math.max(0, Math.min(1, Math.round((v + (e.deltaY < 0 ? 0.05 : -0.05)) * 20) / 20)))
}

// The tip, for whoever has never opened Now Playing: a few seconds into a
// song, once a run, and never again once they have.
const showHint = ref(false)
let hintShown = false
let hintTimer = 0
watch(
  () => [player.isPlaying.value, cur.value && cur.value.title],
  ([playing]) => {
    if (hintShown || nowPlayingSeen.value || !playing || ui.isCompact.value) return
    clearTimeout(hintTimer)
    hintTimer = setTimeout(() => {
      if (nowPlayingSeen.value || onNowPlaying.value || !player.isPlaying.value) return
      hintShown = true
      showHint.value = true
      hintTimer = setTimeout(() => (showHint.value = false), 9000)
    }, 12000)
  }
)
watch(nowPlayingSeen, (seen) => seen && (showHint.value = false))
onBeforeUnmount(() => clearTimeout(hintTimer))
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
/* The cover grows into Now Playing's (smoothChange.travel). */
.pb-cover.is-shared {
  view-transition-name: np-cover;
}
.pb-cover {
  transition:
    transform 0.16s ease,
    box-shadow 0.16s ease;
}
.pb-cover:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 18px rgb(0 0 0 / 0.45);
}
.pb-cover-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: linear-gradient(180deg, rgb(0 0 0 / 0.15), rgb(0 0 0 / 0.55));
  opacity: 0;
  transition: opacity 0.12s ease;
}
.pb-cover:hover .pb-cover-overlay,
.pb-cover:focus-visible .pb-cover-overlay,
.pb-cover-overlay.is-visible {
  opacity: 1;
}
.pb-hint {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 12px;
  z-index: 5;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border-radius: 10px;
  background: rgb(var(--c-accent));
  color: rgb(var(--c-accent-fg));
  font-size: 12.5px;
  font-weight: 700;
  white-space: nowrap;
  box-shadow: 0 10px 26px rgb(0 0 0 / 0.35);
}
.pb-hint::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 22px;
  border: 7px solid transparent;
  border-top-color: rgb(var(--c-accent));
}
.pb-hint-enter-active,
.pb-hint-leave-active {
  transition:
    opacity 0.25s ease,
    transform 0.25s cubic-bezier(0.2, 0.9, 0.2, 1.2);
}
.pb-hint-enter-from,
.pb-hint-leave-to {
  opacity: 0;
  transform: translateY(6px) scale(0.96);
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
  color: rgb(var(--c-fg) / var(--fg-60));
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
  color: rgb(var(--c-fg) / var(--fg-30));
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
  color: rgb(var(--c-fg) / var(--fg-55));
  font-variant-numeric: tabular-nums;
}
.pb-sleep {
  position: relative;
}
.pb-sleep.is-on {
  color: rgb(var(--c-accent));
}
.pb-sleep-left {
  position: absolute;
  right: -2px;
  bottom: -1px;
  min-width: 16px;
  padding: 0 3px;
  border-radius: 999px;
  background: rgb(var(--c-accent));
  color: rgb(var(--c-accent-fg));
  font-size: 9.5px;
  font-weight: 800;
  line-height: 14px;
  text-align: center;
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

/* About sits behind More at every width: ten icons in a row, most of them
   unlabelled, was more than anyone could tell apart. The mini player is out
   where there is room for it (it is a way of using Dannify, not a detail),
   and the sleep timer while it runs, because its countdown is live. */
.pb-extra:not(.pb-sleep):not(.pb-mini),
.pb-sleep:not(.is-on) {
  display: none;
}
@media (max-width: 1180px) {
  .pb-mini {
    display: none;
  }
}

/* Medium windows: tighten the right side; a running sleep timer goes behind
   More too, so the song's own name keeps its room. */
@media (max-width: 1000px) {
  .pbar {
    grid-template-columns: minmax(150px, 1fr) minmax(240px, 1.5fr) auto;
  }
  .pb-extra {
    display: none;
  }
  /* The song's own name needs the room more than a second button beside
     it: saving is in the song's menu too. Below 860 the heart goes as well;
     at 760 the two of them left the title two letters wide. */
  .pb-save {
    display: none;
  }
  .pb-volume {
    width: auto;
  }
  /* A short slider rather than none at all. The window minimum is 760 px, so
     hiding this below 1000 took the volume away from most real sessions and
     left a mute button that could only be all or nothing. */
  .pb-vol-slider {
    flex: none;
    width: 58px;
  }
}

@media (max-width: 860px) {
  .pb-like {
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
