<template>
  <div class="np">
    <!-- The artwork, blurred into light that drifts while the music plays and
         rests when it stops; one song's light fades into the next. The blur
         is drawn once per layer and only the layer moves, so this costs the
         graphics card a slide, not a blur sixty times a second. -->
    <transition name="np-bg-fade">
      <div
        v-if="cur && cur.cover"
        :key="cur.cover"
        class="np-bg"
        :class="{ 'is-playing': player.isPlaying.value }"
        aria-hidden="true"
      >
        <span class="np-bg-layer np-bg-a"><i :style="{ backgroundImage: `url('${cur.cover}')` }" /></span>
        <span class="np-bg-layer np-bg-b"><i :style="{ backgroundImage: `url('${cur.cover}')` }" /></span>
      </div>
    </transition>
    <div class="np-shade" aria-hidden="true" />

    <header class="np-top">
      <button class="icon-btn np-btn" :title="`${t('common.close')} (Esc)`" :aria-label="t('common.close')" @click="close">
        <Icon icon="ph:caret-down" class="h-5 w-5" />
      </button>
      <p class="np-top-label">{{ t('player.nowPlaying') }}</p>
      <div class="ml-auto flex items-center gap-2">
        <div class="seg np-seg">
          <button class="seg-item" :class="{ 'is-active': tab === 'lyrics' }" @click="ui.npTab.value = 'lyrics'">
            <Icon icon="ph:microphone-stage" class="h-4 w-4" /> {{ t('lyrics.title') }}
          </button>
          <button class="seg-item" :class="{ 'is-active': tab === 'queue' }" @click="ui.npTab.value = 'queue'">
            <Icon icon="ph:queue" class="h-4 w-4" /> {{ t('player.queue') }}
          </button>
        </div>
        <button
          v-if="desktop.isDesktop"
          class="icon-btn np-btn"
          :title="`${win.fullscreen ? t('window.exitFullscreen') : t('window.fullscreen')} (F11)`"
          :aria-label="win.fullscreen ? t('window.exitFullscreen') : t('window.fullscreen')"
          @click="desktop.toggleFullscreen()"
        >
          <Icon :icon="win.fullscreen ? 'ph:corners-in' : 'ph:corners-out'" class="h-5 w-5" />
        </button>
      </div>
    </header>

    <EmptyState
      v-if="!cur"
      class="relative"
      icon="ph:music-notes"
      :title="t('player.nothingPlaying')"
      :text="t('player.emptyHint')"
    >
      <button class="btn-accent btn-pill" @click="router.push({ name: 'Home' })">{{ t('nav.browse') }}</button>
    </EmptyState>

    <div v-else class="np-body">
      <section class="np-left">
        <div class="np-cover-wrap" :class="{ 'is-resting': !player.isPlaying.value }" @contextmenu="onMenu">
          <CoverImage :src="cur.cover" radius="lg" class="np-cover" eager />
          <span v-if="player.isBuffering.value" class="np-buffer">
            <span class="spinner h-8 w-8 text-white" />
          </span>
        </div>
        <div class="np-meta">
          <div class="min-w-0 flex-1">
            <h1 class="np-title" :title="cur.title">{{ cur.title }}</h1>
            <p class="np-artist"><ArtistLinks :artists="row ? row.artists : []" /></p>
            <p v-if="row && row.album" class="np-album">
              <a class="link" @click="goToAlbum(row)">{{ row.album }}</a>
            </p>
          </div>
          <SaveSongButton :row="row" class="np-btn h-10 w-10" icon-class="h-6 w-6" />
          <button class="icon-btn is-round np-btn h-10 w-10" :title="t('actions.more')" :aria-label="t('actions.more')" @click="onMore">
            <Icon icon="ph:dots-three-bold" class="h-6 w-6" />
          </button>
        </div>
        <span v-if="cur.type === 'stream'" class="np-badge">
          <Icon icon="ph:cloud" class="h-3.5 w-3.5" /> {{ t('player.streaming') }}
        </span>
      </section>

      <section class="np-right">
        <template v-if="tab === 'lyrics'">
          <LyricsView large class="np-lyrics" />
          <LyricsToolbar bar class="np-lyrics-tools" />
        </template>
        <QueueList v-else class="np-queue" />
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { usePlayer } from '/src/model/player'
import { queueRow, trackMenu, goToAlbum } from '/src/model/tracks'
import { openContextMenu } from '/src/model/contextMenu'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'
import CoverImage from '/src/components/ui/CoverImage.vue'
import ArtistLinks from '/src/components/ui/ArtistLinks.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'
import LyricsView from '/src/components/lyrics/LyricsView.vue'
import LyricsToolbar from '/src/components/lyrics/LyricsToolbar.vue'
import QueueList from '/src/components/shell/QueueList.vue'
import SaveSongButton from '/src/components/ui/SaveSongButton.vue'
import { useUi } from '/src/model/ui'

const { t } = useI18n()
const router = useRouter()
const player = usePlayer()
const win = desktop.state

const ui = useUi()
const tab = computed(() => ui.npTab.value)
const cur = computed(() => player.currentTrack.value)
const row = computed(() => (cur.value ? queueRow(cur.value, player.currentIndex.value) : null))

function close() {
  if (window.history.state && window.history.state.back) router.back()
  else router.push({ name: 'Home' })
}

function onMenu(e) {
  if (row.value) openContextMenu(e, trackMenu([row.value], { queue: true, playing: true }))
}
function onMore(e) {
  if (row.value) openContextMenu(e, trackMenu([row.value], { queue: true, playing: true }), { anchor: true })
}
</script>

<style scoped>
.np {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  color: #fff;
  --c-fg: 255 255 255;
  --c-tint: 255 255 255;
}
.np-bg {
  position: absolute;
  inset: -160px;
  opacity: 0.62;
}
.np-bg-layer {
  position: absolute;
  inset: 0;
  /* A layer of its own: its blurred picture is drawn once and then moved. */
  will-change: transform;
  animation: np-drift-a 46s ease-in-out infinite alternate;
  animation-play-state: paused;
}
.np-bg-layer i {
  position: absolute;
  inset: 0;
  background-size: cover;
  background-position: center;
  filter: blur(90px) saturate(1.6);
}
.np-bg-b {
  opacity: 0.55;
  mix-blend-mode: screen;
  animation-name: np-drift-b;
  animation-duration: 63s;
}
.np-bg.is-playing .np-bg-layer {
  animation-play-state: running;
}
@keyframes np-drift-a {
  from {
    transform: scale(1.12) rotate(0deg) translate(0, 0);
  }
  to {
    transform: scale(1.32) rotate(24deg) translate(4%, -3%);
  }
}
@keyframes np-drift-b {
  from {
    transform: scale(1.3) rotate(180deg) translate(0, 0);
  }
  to {
    transform: scale(1.1) rotate(150deg) translate(-5%, 4%);
  }
}
.np-bg-fade-enter-active,
.np-bg-fade-leave-active {
  transition: opacity 1.1s ease;
}
.np-bg-fade-enter-from,
.np-bg-fade-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .np-bg-layer {
    animation: none;
  }
  .np-bg-fade-enter-active,
  .np-bg-fade-leave-active {
    transition: none;
  }
}
.np-shade {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse at 20% 30%, transparent 0%, rgb(0 0 0 / 0.35) 70%),
    linear-gradient(to bottom, rgb(0 0 0 / 0.2), rgb(0 0 0 / 0.55));
}
.np-top {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px 0;
}
.np-top-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(255 255 255 / 0.7);
}
.np-btn {
  color: rgb(255 255 255 / 0.8);
}
.np-btn:hover {
  color: #fff;
  background: rgb(255 255 255 / 0.12);
}
.np-btn.is-active {
  color: rgb(var(--c-accent));
}
.np-seg {
  background: rgb(0 0 0 / 0.25);
}
.np-seg .seg-item.is-active {
  background: rgb(255 255 255 / 0.18);
  color: #fff;
}
.np-body {
  position: relative;
  display: grid;
  flex: 1;
  min-height: 0;
  grid-template-columns: minmax(260px, 0.9fr) minmax(0, 1.2fr);
  gap: clamp(24px, 4vw, 64px);
  padding: 16px clamp(24px, 4vw, 56px) 24px;
}
.np-left {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
  min-height: 0;
}
.np-cover-wrap {
  position: relative;
  /* Square, and as large as the column allows in whichever direction runs
     out first. Sized from its height rather than its width: in a short
     window the artwork then shrinks, where before it kept its size and
     pushed the title and the badge out of the bottom of the column. */
  aspect-ratio: 1;
  height: min(440px, 58vh);
  max-height: 100%;
  max-width: 100%;
  min-height: 0;
  flex: 0 1 auto;
  /* Without this the column stretches it to full width and the square
     becomes a letterbox. */
  align-self: flex-start;
  /* Full size while the music plays, settled back a little when it stops. */
  transform-origin: center;
  transition:
    transform 0.55s cubic-bezier(0.2, 0.8, 0.2, 1),
    filter 0.55s ease;
}
.np-cover-wrap.is-resting {
  transform: scale(0.94);
  filter: saturate(0.85);
}
.np-cover {
  width: 100%;
  height: 100%;
  box-shadow: 0 24px 70px rgb(0 0 0 / 0.55);
  transition: box-shadow 0.55s ease;
}
.is-resting .np-cover {
  box-shadow: 0 14px 40px rgb(0 0 0 / 0.45);
}
@media (prefers-reduced-motion: reduce) {
  .np-cover-wrap {
    transition: none;
  }
}
.np-buffer {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: rgb(0 0 0 / 0.4);
}
.np-meta {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  width: min(100%, 440px, 58vh);
  margin-top: 24px;
}
/* Two lines before it is cut: "Girl Next Door (feat. tiwa savage)" read
   "Girl Next Door (feat. ti…" with the room for the rest just below. */
.np-title {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-height: 1.15;
  overflow-wrap: anywhere;
  font-size: clamp(22px, 2.4vw, 30px);
  font-weight: 800;
  letter-spacing: -0.02em;
}
.np-artist {
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
  color: rgb(255 255 255 / 0.75);
}
.np-album {
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: rgb(255 255 255 / 0.55);
}
.np-badge {
  display: inline-flex;
  align-self: flex-start;
  align-items: center;
  gap: 6px;
  margin-top: 14px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  background: rgb(255 255 255 / 0.12);
  color: rgb(255 255 255 / 0.8);
}
.np-right {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  /* The lyrics toolbar below sizes itself against this. */
  container: lyricsbar / inline-size;
}
.np-lyrics-tools {
  flex-shrink: 0;
  color: #fff;
}
.np-lyrics {
  flex: 1;
  min-height: 0;
}
.np-queue {
  flex: 1;
  min-height: 0;
  border-radius: 12px;
  background: rgb(0 0 0 / 0.22);
}
/* Narrow window: artwork above, lyrics or queue below, the whole thing one
   scroll. */
@media (max-width: 860px) {
  .np-body {
    grid-template-columns: minmax(0, 1fr);
    gap: 20px;
    overflow-y: auto;
  }
  /* The min-height:0 that lets the two columns shrink side by side has to go
     here: stacked, it let the artwork's row collapse to nothing, and the
     lyrics were then drawn straight over the cover and the title. */
  .np-left {
    min-height: auto;
  }
  .np-cover-wrap {
    height: min(340px, 44vh);
  }
  .np-right {
    min-height: 55vh;
  }
}
</style>
