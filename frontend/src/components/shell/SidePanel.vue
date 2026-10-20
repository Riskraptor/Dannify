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
      <!-- Tabs the way a desktop app draws them: the labels side by side,
           a bar under the one that is open. Arrows move between them. -->
      <div class="sp-tabs" role="tablist" :aria-label="t('panel.tabs')" @keydown="onTabKey">
        <button
          v-for="tb in TABS"
          :key="tb.id"
          class="sp-tab"
          role="tab"
          :aria-selected="tab === tb.id"
          :tabindex="tab === tb.id ? 0 : -1"
          :class="{ 'is-active': tab === tb.id }"
          @click="ui.openPanel(tb.id)"
        >
          <Icon :icon="tab === tb.id ? tb.activeIcon : tb.icon" class="h-4 w-4 shrink-0" />
          <span class="sp-tab-label">{{ t(tb.label) }}</span>
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
import { computed, defineAsyncComponent } from 'vue'
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
// The About tab is fetched the first time it is shown.
const NowPlayingAbout = defineAsyncComponent(() => import('./NowPlayingAbout.vue'))

const { t } = useI18n()
const ui = useUi()
const player = usePlayer()
const account = useAccount()

const tab = computed(() => ui.panel.value || 'lyrics')
const TABS = [
  { id: 'lyrics', label: 'lyrics.title', icon: 'ph:microphone-stage', activeIcon: 'ph:microphone-stage-fill' },
  { id: 'queue', label: 'player.queue', icon: 'ph:queue', activeIcon: 'ph:queue-fill' },
  { id: 'about', label: 'panel.about', icon: 'ph:vinyl-record', activeIcon: 'ph:vinyl-record-fill' },
]
// Left and right move along the tabs and open the one reached, the way a
// tab bar works anywhere else.
function onTabKey(e) {
  const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key]
  if (!step) return
  e.preventDefault()
  const at = TABS.findIndex((tb) => tb.id === tab.value)
  const next = TABS[(at + step + TABS.length) % TABS.length]
  ui.openPanel(next.id)
  const el = e.currentTarget.querySelectorAll('.sp-tab')[TABS.indexOf(next)]
  if (el) el.focus()
}
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
.sp-tabs {
  display: flex;
  flex: 1;
  min-width: 0;
  gap: 2px;
}
.sp-tab {
  position: relative;
  display: inline-flex;
  flex: 1 1 0;
  min-width: 0;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 34px;
  padding: 0 6px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--c-fg) / var(--fg-55));
  transition:
    color 0.15s ease,
    background-color 0.15s ease;
}
.sp-tab:hover {
  color: rgb(var(--c-fg) / 0.9);
  background: rgb(var(--c-tint) / 0.05);
}
.sp-tab.is-active {
  color: rgb(var(--c-fg));
}
/* The bar under the open tab, grown from its middle. */
.sp-tab::after {
  content: '';
  position: absolute;
  left: 22%;
  right: 22%;
  bottom: -3px;
  height: 2px;
  border-radius: 2px;
  background: rgb(var(--c-accent));
  transform: scaleX(0);
  transition: transform 0.2s var(--ease-out);
}
.sp-tab.is-active::after {
  transform: scaleX(1);
}
.sp-tab-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Too narrow for words: the marks alone, each one still named. */
@container lyricsbar (max-width: 300px) {
  .sp-tab-label {
    display: none;
  }
}
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
  padding: 8px 8px 6px 10px;
  border-bottom: 1px solid rgb(var(--c-tint) / 0.07);
}
.sp-now {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 12px 0;
  padding: 8px;
  border-radius: 10px;
  background: rgb(var(--c-tint) / 0.045);
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
