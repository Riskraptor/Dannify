<template>
  <div
    class="stile press"
    role="button"
    tabindex="0"
    :class="{ 'is-current': current }"
    :title="`${row.title}. ${row.artistText}`"
    @click="$emit('play')"
    @keydown.enter.prevent="$emit('play')"
    @keydown.space.self.prevent="$emit('play')"
    @contextmenu="onMenu"
    @mouseenter="warmOnHover(row.raw)"
    @mouseleave="cancelHoverWarm()"
  >
    <CoverImage :src="row.cover" radius="sm" :size="60" class="stile-cover" />
    <span class="min-w-0 flex-1">
      <span class="stile-title">{{ row.title }}</span>
      <span class="stile-sub">{{ row.artistText || t('common.unknownArtist') }}</span>
    </span>
    <span v-if="row.duration" class="stile-time">{{ formatTime(row.duration) }}</span>
    <span class="stile-play">
      <span v-if="current && player.isPlaying.value" class="equalizer"><span /><span /><span /></span>
      <Icon v-else icon="ph:play-fill" class="h-4 w-4" />
    </span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import CoverImage from './CoverImage.vue'
import { usePlayer, formatTime } from '/src/model/player'
import { isRowCurrent, trackMenu } from '/src/model/tracks'
import { openContextMenu } from '/src/model/contextMenu'
import { cancelHoverWarm, warmOnHover } from '/src/model/prefetch'
import { useI18n } from '/src/i18n'

// One song, laid out as a wide tile: the shape Home uses for "jump back in"
// and for every song shelf coming out of the YouTube Music feed.
const props = defineProps({
  row: { type: Object, required: true },
  // Rows the tile belongs to, so the context menu's "Play" matches the grid.
  source: { type: Array, default: () => [] },
  menu: { type: Function, default: null },
})
defineEmits(['play'])

const { t } = useI18n()
const player = usePlayer()
const current = computed(() => isRowCurrent(props.row))

function onMenu(e) {
  const items = props.menu ? props.menu() : trackMenu([props.row], { source: props.source })
  openContextMenu(e, items)
}
</script>

<style scoped>
.stile {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  height: 60px;
  padding-right: 12px;
  overflow: hidden;
  border-radius: 6px;
  background: rgb(var(--c-tint) / 0.07);
  outline: none;
  transition: background-color 0.15s ease;
}
.stile:hover,
.stile:focus-visible {
  background: rgb(var(--c-tint) / 0.13);
}
.stile:focus-visible {
  box-shadow: inset 0 0 0 2px rgb(var(--c-accent) / 0.7);
}
.stile-cover {
  width: 60px;
  height: 60px;
  flex-shrink: 0;
  border-radius: 0;
  box-shadow: 4px 0 12px rgb(0 0 0 / 0.2);
}
.stile-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 600;
}
.is-current .stile-title {
  color: rgb(var(--c-accent));
}
.stile-sub {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12.5px;
  color: rgb(var(--c-fg) / 0.55);
}
.stile-time {
  flex-shrink: 0;
  font-size: 12.5px;
  color: rgb(var(--c-fg) / 0.45);
  font-variant-numeric: tabular-nums;
  transition: opacity 0.15s ease;
}
.stile:hover .stile-time,
.stile:focus-visible .stile-time {
  opacity: 0;
}
.stile-play {
  position: absolute;
  right: 12px;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: 999px;
  background: rgb(var(--c-accent));
  color: rgb(var(--c-accent-fg));
  opacity: 0;
  transform: scale(0.9);
  transition:
    opacity 0.15s ease,
    transform 0.15s ease;
}
.stile-play .equalizer span {
  background: rgb(var(--c-accent-fg));
}
.stile:hover .stile-play,
.stile:focus-visible .stile-play,
.is-current .stile-play {
  opacity: 1;
  transform: none;
}
</style>
