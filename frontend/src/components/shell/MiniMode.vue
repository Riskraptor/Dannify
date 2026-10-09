<template>
  <div class="mini" :class="{ 'is-open': !!panel }" @contextmenu.prevent="onMenu">
    <div
      v-if="cur && cur.cover"
      class="mini-bg"
      :style="{ backgroundImage: `url('${cur.cover}')` }"
      aria-hidden="true"
    />
    <div class="mini-shade" aria-hidden="true" />

    <div ref="bar" class="mini-bar">
      <CoverImage :src="cur ? cur.cover : ''" radius="md" class="mini-cover" eager />

      <div class="mini-body">
        <div class="mini-top">
          <div class="min-w-0 flex-1">
            <p class="mini-title">{{ cur ? cur.title : t('player.nothingPlaying') }}</p>
            <p class="mini-artist">{{ cur ? cur.artist || t('common.unknownArtist') : '' }}</p>
          </div>
          <button
            class="icon-btn h-7 w-7"
            :class="{ 'is-active': panel === 'lyrics' }"
            :title="t('lyrics.title')"
            :aria-label="t('lyrics.title')"
            @click="toggle('lyrics')"
          >
            <Icon icon="ph:microphone-stage" class="h-4 w-4" />
          </button>
          <button
            class="icon-btn h-7 w-7"
            :class="{ 'is-active': panel === 'queue' }"
            :title="t('player.queue')"
            :aria-label="t('player.queue')"
            @click="toggle('queue')"
          >
            <Icon icon="ph:queue" class="h-4 w-4" />
          </button>
          <button
            class="icon-btn h-7 w-7"
            :class="{ 'is-active': win.onTop }"
            :title="t('player.keepOnTop')"
            :aria-label="t('player.keepOnTop')"
            @click="desktop.setOnTop(!win.onTop)"
          >
            <Icon :icon="win.onTop ? 'ph:push-pin-fill' : 'ph:push-pin'" class="h-4 w-4" />
          </button>
          <button
            class="icon-btn h-7 w-7"
            :title="t('player.exitMiniPlayer')"
            :aria-label="t('player.exitMiniPlayer')"
            @click="desktop.setMini(false)"
          >
            <Icon icon="ph:arrows-out-simple" class="h-4 w-4" />
          </button>
          <!-- macOS has its own close button on the window. -->
          <button
            v-if="platform !== 'macos'"
            class="icon-btn h-7 w-7 mini-close"
            :title="t('window.close')"
            :aria-label="t('window.close')"
            @click="desktop.close()"
          >
            <Icon icon="ph:x" class="h-4 w-4" />
          </button>
        </div>

        <div class="mini-controls">
          <button class="icon-btn is-round h-8 w-8" :disabled="!cur" :title="t('player.previous')" :aria-label="t('player.previous')" @click="player.prev()">
            <Icon icon="ph:skip-back-fill" class="h-[18px] w-[18px]" />
          </button>
          <button class="mini-play" :disabled="!cur" :title="player.isPlaying.value ? t('player.pause') : t('player.play')" :aria-label="player.isPlaying.value ? t('player.pause') : t('player.play')" @click="player.toggle()">
            <Icon :icon="player.isPlaying.value ? 'ph:pause-fill' : 'ph:play-fill'" class="h-4 w-4" />
          </button>
          <button class="icon-btn is-round h-8 w-8" :disabled="!cur" :title="t('player.next')" :aria-label="t('player.next')" @click="player.next()">
            <Icon icon="ph:skip-forward-fill" class="h-[18px] w-[18px]" />
          </button>
          <div class="mini-seek">
            <RangeSlider
              :value="player.progressPct.value / 100"
              :live="false"
              :disabled="!cur || !player.duration.value"
              :label="t('player.seek')"
              :tooltip="(r) => formatTime(r * (player.duration.value || 0))"
              @change="(r) => player.seekRatio(r)"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Lyrics and queue, in the same window. The bar above stays exactly
         where it was: the panel unfolds upwards, so nothing under the
         pointer moves when it opens. -->
    <div v-if="panel" class="mini-panel" data-no-drag>
      <template v-if="panel === 'lyrics'">
        <LyricsView v-if="cur" class="mini-lyrics" compact />
        <div v-else class="mini-empty">
          <Icon icon="ph:microphone-stage" class="mb-2 h-8 w-8 opacity-40" />
          <p>{{ t('panel.lyricsIdle') }}</p>
        </div>
      </template>
      <QueueList v-else class="mini-queue" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { Icon } from '@iconify/vue'
import { usePlayer, formatTime } from '/src/model/player'
import { desktop, bindWindowDrag, platform } from '/src/desktop/bridge'
import { openContextMenu } from '/src/model/contextMenu'
import { useI18n } from '/src/i18n'
import CoverImage from '../ui/CoverImage.vue'
import RangeSlider from '../ui/RangeSlider.vue'
import LyricsView from '../lyrics/LyricsView.vue'
import QueueList from './QueueList.vue'

// The bar on its own (MINI_H in Backend/desktop.py), and the bar with a
// panel under it. The shell allows up to MINI_MAX_H (560); 460 is what the
// panel asks for, room for the queue or a few lines of lyrics.
const BAR_H = 124
const OPEN_H = 460
const KEY = 'dn.miniPanel'

const { t } = useI18n()
const player = usePlayer()
const win = desktop.state
const bar = ref(null)
const cur = computed(() => player.currentTrack.value)

const panel = ref(read())

function read() {
  try {
    const saved = localStorage.getItem(KEY)
    return saved === 'lyrics' || saved === 'queue' ? saved : null
  } catch {
    return null
  }
}

function toggle(name) {
  panel.value = panel.value === name ? null : name
  try {
    if (panel.value) localStorage.setItem(KEY, panel.value)
    else localStorage.removeItem(KEY)
  } catch {
    // storage blocked: the choice just won't survive a restart
  }
}

// The window itself has to change size; the panel is not an overlay.
watch(
  panel,
  (open) => desktop.setMiniSize(open ? OPEN_H : BAR_H),
  { immediate: true }
)

function onMenu(e) {
  openContextMenu(e, [
    {
      label: t('lyrics.title'),
      icon: 'ph:microphone-stage',
      checked: panel.value === 'lyrics',
      action: () => toggle('lyrics'),
    },
    {
      label: t('player.queue'),
      icon: 'ph:queue',
      checked: panel.value === 'queue',
      action: () => toggle('queue'),
    },
    { divider: true },
    {
      label: t('player.keepOnTop'),
      icon: 'ph:push-pin',
      checked: win.onTop,
      action: () => desktop.setOnTop(!win.onTop),
    },
    { label: t('player.exitMiniPlayer'), icon: 'ph:arrows-out-simple', action: () => desktop.setMini(false) },
    { divider: true },
    { label: t('window.close'), icon: 'ph:x', action: () => desktop.close() },
  ])
}

let unbind = () => {}
onMounted(() => {
  // Only the bar drags the window: a drag inside the lyrics is a scroll.
  unbind = bindWindowDrag(bar.value, { systemMenu: false })
})
onBeforeUnmount(() => unbind())
</script>

<style scoped>
.mini {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: rgb(var(--c-panel));
  color: #fff;
}
.mini-bg {
  position: absolute;
  inset: -40px;
  background-size: cover;
  background-position: center;
  filter: blur(40px) saturate(1.4);
  opacity: 0.55;
  /* A layer of its own: blurred once and then moved, instead of blurred
     again on every repaint while the page scrolls. */
  will-change: transform;
}
.mini-shade {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgb(0 0 0 / 0.35), rgb(0 0 0 / 0.55));
}
.mini.is-open .mini-shade {
  background: linear-gradient(180deg, rgb(0 0 0 / 0.35), rgb(0 0 0 / 0.72));
}
.mini-bar {
  position: relative;
  display: flex;
  flex: none;
  height: 124px;
  align-items: center;
  gap: 12px;
  padding: 12px;
}
.mini-cover {
  position: relative;
  width: 96px;
  height: 96px;
  box-shadow: 0 6px 18px rgb(0 0 0 / 0.45);
}
.mini-body {
  position: relative;
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  justify-content: space-between;
  align-self: stretch;
  padding: 2px 0;
}
.mini-top {
  display: flex;
  align-items: flex-start;
  gap: 2px;
}
.mini-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 600;
}
.mini-artist {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: rgb(255 255 255 / 0.65);
}
.mini .icon-btn {
  color: rgb(255 255 255 / 0.75);
}
.mini .icon-btn:hover {
  color: #fff;
  background: rgb(255 255 255 / 0.12);
}
.mini .icon-btn.is-active {
  color: rgb(var(--c-accent));
}
.mini-close:hover {
  background: #c42b1c !important;
}
.mini-controls {
  display: flex;
  align-items: center;
  gap: 4px;
}
.mini-play {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 999px;
  background: #fff;
  color: #000;
}
.mini-play:disabled {
  opacity: 0.5;
}
.mini-seek {
  flex: 1;
  min-width: 0;
  margin-left: 8px;
}
.mini-seek :deep(.rs-track) {
  background: rgb(255 255 255 / 0.25);
}
.mini-seek :deep(.rs-fill) {
  background: #fff;
}

/* --- the unfolded half ---------------------------------------------------- */
/* The bar is dark because it sits on the artwork; the panel goes back to the
   app's own surface so the queue rows and the lyrics look the same here as
   they do in the full window, in every theme. */
.mini-panel {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-top: 1px solid rgb(var(--c-tint) / 0.1);
  background: rgb(var(--c-panel));
  color: rgb(var(--c-fg));
}
.mini-lyrics {
  flex: 1;
  min-height: 0;
  padding: 4px 16px;
}
/* Smaller than the side panel's: this window is 420 px wide and the lines
   have to stay readable at two or three words a row. */
.mini-lyrics :deep(.lyric-line) {
  font-size: 1.05rem;
  line-height: 1.3;
}
.mini-lyrics :deep(.lyric-line.active) {
  font-size: 1.2rem;
}
.mini-queue {
  flex: 1;
  min-height: 0;
}
.mini-empty {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: rgb(var(--c-fg) / var(--fg-50));
}
</style>
