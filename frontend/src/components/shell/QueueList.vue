<template>
  <div class="ql">
    <template v-if="current">
      <p class="ql-head">{{ t('player.nowPlaying') }}</p>
      <QueueItem
        :row="current"
        :active="true"
        @play="player.toggle()"
        @menu="(e) => openMenu(e, current)"
      />
    </template>

    <div class="ql-head flex items-center justify-between">
      <span>{{ t('player.upNext') }}</span>
      <button
        v-if="upNext.length"
        class="btn-ghost h-6 px-2 text-[11px] normal-case tracking-normal"
        @click="player.clearUpcoming()"
      >
        {{ t('panel.clearQueue') }}
      </button>
    </div>

    <div v-if="!upNext.length" class="ql-empty">
      <Icon icon="ph:queue" class="mb-2 h-8 w-8 text-fg/25" />
      <p>{{ t('panel.emptyQueue') }}</p>
    </div>
    <VirtualList
      v-else
      class="ql-list"
      :items="upNext"
      :item-height="52"
      :item-key="(r) => r.key"
    >
      <template #default="{ item }">
        <QueueItem
          :row="item"
          @play="player.playAt(item.queueIndex)"
          @remove="player.removeFromQueue(item.queueIndex)"
          @menu="(e) => openMenu(e, item)"
        />
      </template>
    </VirtualList>
  </div>
</template>

<script setup>
import { computed, h } from 'vue'
import { Icon } from '@iconify/vue'
import { usePlayer, formatTime } from '/src/model/player'
import { queueRow, trackMenu } from '/src/model/tracks'
import { openContextMenu } from '/src/model/contextMenu'
import { useI18n } from '/src/i18n'
import VirtualList from '../ui/VirtualList.vue'
import CoverImage from '../ui/CoverImage.vue'

const { t } = useI18n()
const player = usePlayer()

const current = computed(() => {
  const tr = player.currentTrack.value
  return tr ? queueRow(tr, player.currentIndex.value) : null
})

const upNext = computed(() => {
  const list = player.playlist.value
  const start = player.currentIndex.value + 1
  const out = []
  for (let i = Math.max(0, start); i < list.length; i++) out.push(queueRow(list[i], i))
  return out
})

function openMenu(e, row) {
  openContextMenu(e, trackMenu([row], { queue: true }))
}

const QueueItem = {
  props: { row: Object, active: Boolean },
  emits: ['play', 'remove', 'menu'],
  setup(props, { emit }) {
    return () => {
      const r = props.row
      const playing = props.active && player.isPlaying.value
      return h(
        'div',
        {
          class: ['ql-item', { 'is-active': props.active }],
          onDblclick: () => emit('play'),
          onContextmenu: (e) => emit('menu', e),
          title: `${r.title}. ${r.artistText}`,
        },
        [
          h(CoverImage, { src: r.cover, radius: 'sm', class: 'ql-cover' }, () => [
            h(
              'button',
              {
                class: 'ql-cover-btn',
                tabindex: -1,
                onClick: (e) => {
                  e.stopPropagation()
                  emit('play')
                },
              },
              [
                playing
                  ? h('span', { class: 'equalizer' }, [h('span'), h('span'), h('span')])
                  : h(Icon, { icon: 'ph:play-fill', class: 'h-4 w-4 text-white' }),
              ]
            ),
          ]),
          h('div', { class: 'min-w-0 flex-1' }, [
            h('div', { class: 'ql-title' }, r.title),
            h('div', { class: 'ql-artist' }, r.artistText),
          ]),
          r.duration ? h('span', { class: 'ql-time' }, formatTime(r.duration)) : null,
          props.active
            ? null
            : h(
                'button',
                {
                  class: 'ql-remove icon-btn h-7 w-7',
                  tabindex: -1,
                  title: t('actions.removeFromQueue'),
                  onClick: (e) => {
                    e.stopPropagation()
                    emit('remove')
                  },
                },
                [h(Icon, { icon: 'ph:x', class: 'h-3.5 w-3.5' })]
              ),
        ]
      )
    }
  },
}
</script>

<style scoped>
.ql {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 0 8px 8px;
}
.ql-head {
  padding: 12px 8px 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / 0.5);
}
.ql-list {
  flex: 1;
  min-height: 0;
}
.ql-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 36px 16px;
  text-align: center;
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.45);
}
.ql :deep(.ql-item) {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 50px;
  padding: 0 8px;
  border-radius: 6px;
}
.ql :deep(.ql-item:hover) {
  background: rgb(var(--c-tint) / 0.06);
}
.ql :deep(.ql-item.is-active .ql-title) {
  color: rgb(var(--c-accent));
}
.ql :deep(.ql-cover) {
  width: 40px;
  height: 40px;
}
.ql :deep(.ql-cover-btn) {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: grid;
  place-items: center;
  background: rgb(0 0 0 / 0.45);
  opacity: 0;
  transition: opacity 0.1s ease;
}
.ql :deep(.ql-item:hover .ql-cover-btn),
.ql :deep(.ql-item.is-active .ql-cover-btn) {
  opacity: 1;
}
.ql :deep(.ql-title) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13.5px;
  font-weight: 500;
}
.ql :deep(.ql-artist) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: rgb(var(--c-fg) / 0.55);
}
.ql :deep(.ql-time) {
  font-size: 12px;
  color: rgb(var(--c-fg) / 0.45);
  font-variant-numeric: tabular-nums;
}
.ql :deep(.ql-remove) {
  display: none;
}
.ql :deep(.ql-item:hover .ql-remove) {
  display: inline-grid;
}
.ql :deep(.ql-item:hover .ql-time) {
  display: none;
}
</style>
