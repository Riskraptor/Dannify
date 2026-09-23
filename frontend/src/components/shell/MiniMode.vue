<template>
  <div ref="root" class="mini" @contextmenu.prevent="onMenu">
    <div
      v-if="cur && cur.cover"
      class="mini-bg"
      :style="{ backgroundImage: `url('${cur.cover}')` }"
      aria-hidden="true"
    />
    <div class="mini-shade" aria-hidden="true" />

    <CoverImage :src="cur ? cur.cover : ''" radius="md" class="mini-cover" eager />

    <div class="mini-body">
      <div class="mini-top">
        <div class="min-w-0 flex-1">
          <p class="mini-title">{{ cur ? cur.title : t('player.nothingPlaying') }}</p>
          <p class="mini-artist">{{ cur ? cur.artist || t('common.unknownArtist') : '' }}</p>
        </div>
        <button
          class="icon-btn h-7 w-7"
          :class="{ 'is-active': win.onTop }"
          :title="t('player.keepOnTop')"
          @click="desktop.setOnTop(!win.onTop)"
        >
          <Icon :icon="win.onTop ? 'ph:push-pin-fill' : 'ph:push-pin'" class="h-4 w-4" />
        </button>
        <button
          class="icon-btn h-7 w-7"
          :title="t('player.exitMiniPlayer')"
          @click="desktop.setMini(false)"
        >
          <Icon icon="ph:arrows-out-simple" class="h-4 w-4" />
        </button>
        <button class="icon-btn h-7 w-7 mini-close" :title="t('window.close')" @click="desktop.close()">
          <Icon icon="ph:x" class="h-4 w-4" />
        </button>
      </div>

      <div class="mini-controls">
        <button class="icon-btn is-round h-8 w-8" :disabled="!cur" :title="t('player.previous')" @click="player.prev()">
          <Icon icon="ph:skip-back-fill" class="h-[18px] w-[18px]" />
        </button>
        <button class="mini-play" :disabled="!cur" :title="player.isPlaying.value ? t('player.pause') : t('player.play')" @click="player.toggle()">
          <Icon :icon="player.isPlaying.value ? 'ph:pause-fill' : 'ph:play-fill'" class="h-4 w-4" />
        </button>
        <button class="icon-btn is-round h-8 w-8" :disabled="!cur" :title="t('player.next')" @click="player.next()">
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
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { Icon } from '@iconify/vue'
import { usePlayer, formatTime } from '/src/model/player'
import { desktop, bindWindowDrag } from '/src/desktop/bridge'
import { openContextMenu } from '/src/model/contextMenu'
import { useI18n } from '/src/i18n'
import CoverImage from '../ui/CoverImage.vue'
import RangeSlider from '../ui/RangeSlider.vue'

const { t } = useI18n()
const player = usePlayer()
const win = desktop.state
const root = ref(null)
const cur = computed(() => player.currentTrack.value)

function onMenu(e) {
  openContextMenu(e, [
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
  // The mini player has its own right-click menu.
  unbind = bindWindowDrag(root.value, { systemMenu: false })
})
onBeforeUnmount(() => unbind())
</script>

<style scoped>
.mini {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
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
}
.mini-shade {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgb(0 0 0 / 0.35), rgb(0 0 0 / 0.55));
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
</style>
