<template>
  <aside
    class="spanel"
    :class="{ 'is-floating': ui.panelFloating.value }"
    :style="{ width: `${ui.panelWidth.value}px` }"
    :aria-label="tab === 'lyrics' ? t('lyrics.title') : tab === 'about' ? t('panel.about') : t('player.queue')"
  >
    <div
      v-if="!ui.panelFloating.value"
      class="sp-resizer"
      :title="t('panel.resize')"
      @pointerdown="startResize"
      @dblclick="ui.setPanelWidth(340)"
    />

    <header class="sp-head">
      <div class="seg">
        <button
          class="seg-item"
          :class="{ 'is-active': tab === 'lyrics' }"
          @click="ui.openPanel('lyrics')"
        >
          <Icon icon="ph:microphone-stage" class="h-4 w-4" />
          {{ t('lyrics.title') }}
        </button>
        <button
          class="seg-item"
          :class="{ 'is-active': tab === 'queue' }"
          @click="ui.openPanel('queue')"
        >
          <Icon icon="ph:queue" class="h-4 w-4" />
          {{ t('player.queue') }}
        </button>
        <button
          class="seg-item"
          :class="{ 'is-active': tab === 'about' }"
          @click="ui.openPanel('about')"
        >
          <Icon icon="ph:vinyl-record" class="h-4 w-4" />
          {{ t('panel.about') }}
        </button>
      </div>
      <button
        class="icon-btn ml-auto"
        :title="t('common.close') + ' (Esc)'"
        :aria-label="t('common.close') + ' (Esc)'"
        @click="ui.closePanel()"
      >
        <Icon icon="ph:x" class="h-4 w-4" />
      </button>
    </header>

    <template v-if="tab === 'lyrics'">
      <div v-if="cur" class="sp-now">
        <div class="sp-now-art">
          <CoverImage :src="cur.cover" radius="sm" :size="44" class="h-full w-full" />
          <span class="sp-now-ring" :style="{ '--p': `${player.progressPct.value}%` }" />
        </div>
        <div class="min-w-0 flex-1">
          <p class="truncate text-[13.5px] font-semibold">{{ cur.title }}</p>
          <p class="truncate text-xs text-fg/55">{{ cur.artist || t('common.unknownArtist') }}</p>
        </div>
        <button
          v-if="videoId"
          class="icon-btn is-round press shrink-0"
          :class="{ 'is-liked': liked }"
          :title="liked ? t('account.removeFromLiked') : t('account.addToLiked')"
          :aria-label="liked ? t('account.removeFromLiked') : t('account.addToLiked')"
          @click="account.toggleLike(row.raw)"
        >
          <Icon :icon="liked ? 'ph:heart-fill' : 'ph:heart'" class="h-[17px] w-[17px]" />
        </button>
      </div>
      <div class="sp-lyrics">
        <LyricsView v-if="cur" />
        <div v-else class="sp-empty">
          <Icon icon="ph:microphone-stage" class="mb-2 h-9 w-9 text-fg/25" />
          <p>{{ t('panel.lyricsIdle') }}</p>
        </div>
      </div>
      <LyricsToolbar v-if="cur" bar class="sp-tools" />
    </template>
    <NowPlayingAbout v-else-if="tab === 'about'" />
    <QueueList v-else class="min-h-0 flex-1" />
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import { useUi } from '/src/model/ui'
import { usePlayer } from '/src/model/player'
import { useAccount } from '/src/model/account'
import { queueRow, songVideoId } from '/src/model/tracks'
import { useI18n } from '/src/i18n'
import CoverImage from '../ui/CoverImage.vue'
import LyricsView from '../lyrics/LyricsView.vue'
import LyricsToolbar from '../lyrics/LyricsToolbar.vue'
import QueueList from './QueueList.vue'
import NowPlayingAbout from './NowPlayingAbout.vue'

const { t } = useI18n()
const ui = useUi()
const player = usePlayer()
const account = useAccount()

const tab = computed(() => ui.panel.value || 'lyrics')
const cur = computed(() => player.currentTrack.value)
const row = computed(() => (cur.value ? queueRow(cur.value, player.currentIndex.value) : null))
const videoId = computed(() => (row.value ? songVideoId(row.value) : ''))
const liked = computed(() => account.isLiked(videoId.value))

function startResize(e) {
  if (e.button !== 0) return
  e.preventDefault()
  const el = e.currentTarget
  el.setPointerCapture(e.pointerId)
  const startX = e.clientX
  const startW = ui.panelWidth.value
  document.documentElement.classList.add('is-col-resizing')
  const move = (ev) => ui.setPanelWidth(startW + (startX - ev.clientX))
  const up = () => {
    el.removeEventListener('pointermove', move)
    el.removeEventListener('pointerup', up)
    el.removeEventListener('pointercancel', up)
    document.documentElement.classList.remove('is-col-resizing')
  }
  el.addEventListener('pointermove', move)
  el.addEventListener('pointerup', up)
  el.addEventListener('pointercancel', up)
}
</script>

<style scoped>
.spanel {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-radius: var(--radius-panel);
  background: rgb(var(--c-panel));
  /* The lyrics toolbar at the foot sizes itself against this. */
  container: lyricsbar / inline-size;
}
.spanel.is-floating {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 40;
  max-width: calc(100% - 24px);
  box-shadow: var(--shadow-pop);
  animation: sp-in 0.22s var(--ease-out);
}
@keyframes sp-in {
  from {
    transform: translateX(24px);
    opacity: 0;
  }
}
.sp-resizer {
  position: absolute;
  top: 12px;
  bottom: 12px;
  left: -6px;
  z-index: 5;
  width: 8px;
  cursor: ew-resize;
}
.sp-resizer::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 3px;
  width: 2px;
  border-radius: 2px;
  background: rgb(var(--c-accent));
  opacity: 0;
  transition: opacity 0.15s ease;
}
.sp-resizer:hover::after {
  opacity: 0.8;
}
.sp-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 10px 6px 12px;
}
.sp-now {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 4px 12px 0;
  padding: 8px;
  border-radius: 8px;
  background: rgb(var(--c-tint) / 0.05);
}
.sp-now-art {
  position: relative;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
}
/* A hairline under the artwork tracks playback: the panel always says
   where in the song you are, even with the player bar out of view. */
.sp-now-ring {
  position: absolute;
  left: 0;
  right: 0;
  bottom: -4px;
  height: 2px;
  border-radius: 2px;
  background: linear-gradient(
    to right,
    rgb(var(--c-accent)) var(--p, 0%),
    rgb(var(--c-tint) / 0.18) var(--p, 0%)
  );
}
.sp-now .is-liked,
.sp-now .is-liked:hover {
  color: rgb(var(--c-accent));
}
.sp-lyrics {
  flex: 1;
  min-height: 0;
  padding: 8px 18px 4px;
}
.sp-tools {
  margin: 0 12px 8px;
}
.sp-empty {
  display: flex;
  height: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  font-size: 13px;
  color: rgb(var(--c-fg) / var(--fg-45));
}
</style>
