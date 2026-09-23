<template>
  <div class="np">
    <div v-if="cur && cur.cover" class="np-bg" :style="{ backgroundImage: `url('${cur.cover}')` }" aria-hidden="true" />
    <div class="np-shade" aria-hidden="true" />

    <header class="np-top">
      <button class="icon-btn np-btn" :title="`${t('common.close')} (Esc)`" @click="close">
        <Icon icon="ph:caret-down" class="h-5 w-5" />
      </button>
      <p class="np-top-label">{{ t('player.nowPlaying') }}</p>
      <div class="ml-auto flex items-center gap-2">
        <div class="seg np-seg">
          <button class="seg-item" :class="{ 'is-active': tab === 'lyrics' }" @click="tab = 'lyrics'">
            <Icon icon="ph:microphone-stage" class="h-4 w-4" /> {{ t('lyrics.title') }}
          </button>
          <button class="seg-item" :class="{ 'is-active': tab === 'queue' }" @click="tab = 'queue'">
            <Icon icon="ph:queue" class="h-4 w-4" /> {{ t('player.queue') }}
          </button>
        </div>
        <button
          v-if="desktop.isDesktop"
          class="icon-btn np-btn"
          :title="`${win.fullscreen ? t('window.exitFullscreen') : t('window.fullscreen')} (F11)`"
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
        <div class="np-cover-wrap" @contextmenu="onMenu">
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
          <button
            class="icon-btn is-round np-btn h-10 w-10"
            :class="{ 'is-active': inLibrary }"
            :disabled="inLibrary"
            :title="inLibrary ? t('player.inLibrary') : t('player.saveToLibrary')"
            @click="downloadRows([row])"
          >
            <Icon :icon="inLibrary ? 'ph:check-circle-fill' : 'ph:plus-circle'" class="h-6 w-6" />
          </button>
          <button class="icon-btn is-round np-btn h-10 w-10" :title="t('actions.more')" @click="onMore">
            <Icon icon="ph:dots-three-bold" class="h-6 w-6" />
          </button>
        </div>
        <span v-if="cur.type === 'stream'" class="np-badge">
          <Icon icon="ph:cloud" class="h-3.5 w-3.5" /> {{ t('player.streaming') }}
        </span>
      </section>

      <section class="np-right">
        <template v-if="tab === 'lyrics'">
          <LyricsPanel large class="np-lyrics" />
          <LyricsControls bar class="np-lyrics-tools" />
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
import { useLibraryIndex } from '/src/model/libraryIndex'
import { queueRow, trackMenu, isRowDownloaded, downloadRows, goToAlbum } from '/src/model/tracks'
import { openContextMenu } from '/src/model/contextMenu'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'
import CoverImage from '/src/components/ui/CoverImage.vue'
import ArtistLinks from '/src/components/ui/ArtistLinks.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'
import LyricsPanel from '/src/components/LyricsPanel.vue'
import LyricsControls from '/src/components/LyricsControls.vue'
import QueueList from '/src/components/shell/QueueList.vue'

const { t } = useI18n()
const router = useRouter()
const player = usePlayer()
const libIndex = useLibraryIndex()
const win = desktop.state

const tab = ref('lyrics')
const cur = computed(() => player.currentTrack.value)
const row = computed(() => (cur.value ? queueRow(cur.value, player.currentIndex.value) : null))
const inLibrary = computed(() => {
  void libIndex.byVideoId.value
  return !!row.value && isRowDownloaded(row.value)
})

function close() {
  if (window.history.state && window.history.state.back) router.back()
  else router.push({ name: 'Home' })
}

function onMenu(e) {
  if (row.value) openContextMenu(e, trackMenu([row.value], { queue: true }))
}
function onMore(e) {
  if (row.value) openContextMenu(e, trackMenu([row.value], { queue: true }), { anchor: true })
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
  inset: -120px;
  background-size: cover;
  background-position: center;
  filter: blur(90px) saturate(1.5);
  opacity: 0.55;
  transform: scale(1.1);
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
  width: min(100%, 440px, 58vh);
  aspect-ratio: 1;
}
.np-cover {
  width: 100%;
  height: 100%;
  box-shadow: 0 24px 70px rgb(0 0 0 / 0.55);
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
.np-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
@media (max-width: 860px) {
  .np-body {
    grid-template-columns: minmax(0, 1fr);
    overflow-y: auto;
  }
  .np-right {
    min-height: 60vh;
  }
}
</style>
