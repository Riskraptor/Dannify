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
      <span class="flex items-center gap-1">
        <button
          v-if="player.playlist.value.length > 1"
          class="btn-ghost h-6 px-2 text-[11px] normal-case tracking-normal"
          :title="t('playlists.saveQueue')"
          @click="saveAsPlaylist"
        >
          <Icon icon="ph:playlist" class="h-3.5 w-3.5" />
          {{ t('playlists.saveQueue') }}
        </button>
        <button
          v-if="upNext.length"
          class="btn-ghost h-6 px-2 text-[11px] normal-case tracking-normal"
          @click="player.clearUpcoming()"
        >
          {{ t('panel.clearQueue') }}
        </button>
      </span>
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
      <template #default="{ item, index }">
        <QueueItem
          :row="item"
          :pos="index"
          @play="player.playAt(item.queueIndex)"
          @remove="player.removeFromQueue(item.queueIndex)"
          @menu="(e) => openMenu(e, item)"
        />
      </template>
    </VirtualList>
  </div>
</template>

<script setup>
import { computed, h, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { usePlayer, formatTime } from '/src/model/player'
import { queueRow, trackMenu } from '/src/model/tracks'
import { usePlaylists } from '/src/model/playlists'
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

// In the order the tracks will actually play: under shuffle that is the
// shuffled order, not the rows below the current one.
const upNext = computed(() => {
  const list = player.playlist.value
  return player.upcoming.value.map((i) => queueRow(list[i], i))
})

function openMenu(e, row) {
  openContextMenu(e, trackMenu([row], { queue: true }))
}

// The whole queue, in the order it is listed, as a playlist of its own.
const playlists = usePlaylists()
function saveAsPlaylist() {
  const rows = player.playlist.value.map((tr, i) => queueRow(tr, i))
  const date = new Date().toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
  playlists.createPlaylist(rows, { name: t('playlists.queueName', { date }) })
}

// ----- dragging -----------------------------------------------------------------
// A song in "Up next" can be dragged to another place in it, and any song
// here onto a playlist in the side bar.
const dragFrom = ref(-1)
const dropAt = ref(null) // { pos, after }

function onDragStart(e, row, pos) {
  dragFrom.value = pos
  playlists.dragging.value = [row]
  e.dataTransfer.effectAllowed = pos >= 0 ? 'copyMove' : 'copy'
  e.dataTransfer.setData('text/plain', `${row.artistText} - ${row.title}`)
}
function onDragOver(e, pos) {
  if (dragFrom.value < 0 || pos < 0) return
  e.preventDefault()
  e.dataTransfer.dropEffect = 'move'
  const r = e.currentTarget.getBoundingClientRect()
  const after = e.clientY > r.top + r.height / 2
  if (!dropAt.value || dropAt.value.pos !== pos || dropAt.value.after !== after) {
    dropAt.value = { pos, after }
  }
}
function onDrop(e) {
  if (dragFrom.value < 0 || !dropAt.value) return
  e.preventDefault()
  const from = dragFrom.value
  const to = dropAt.value.pos + (dropAt.value.after ? 1 : 0)
  player.moveUpcoming(from, to > from ? to - 1 : to)
  onDragEnd()
}
function onDragEnd() {
  dragFrom.value = -1
  dropAt.value = null
  playlists.dragging.value = null
}

const QueueItem = {
  props: { row: Object, active: Boolean, pos: { type: Number, default: -1 } },
  emits: ['play', 'remove', 'menu'],
  setup(props, { emit }) {
    return () => {
      const r = props.row
      const playing = props.active && player.isPlaying.value
      const drop = dropAt.value && dropAt.value.pos === props.pos ? dropAt.value : null
      return h(
        'div',
        {
          class: [
            'ql-item',
            {
              'is-active': props.active,
              'is-drop-before': drop && !drop.after,
              'is-drop-after': drop && drop.after,
            },
          ],
          draggable: 'true',
          onDragstart: (e) => onDragStart(e, r, props.active ? -1 : props.pos),
          onDragover: (e) => onDragOver(e, props.active ? -1 : props.pos),
          onDrop,
          onDragend: onDragEnd,
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
  color: rgb(var(--c-fg) / var(--fg-50));
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
  color: rgb(var(--c-fg) / var(--fg-45));
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
  color: rgb(var(--c-fg) / var(--fg-55));
}
.ql :deep(.ql-time) {
  font-size: 12px;
  color: rgb(var(--c-fg) / var(--fg-45));
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
.ql :deep(.ql-item.is-drop-before) {
  box-shadow: inset 0 2px 0 rgb(var(--c-accent));
}
.ql :deep(.ql-item.is-drop-after) {
  box-shadow: inset 0 -2px 0 rgb(var(--c-accent));
}
</style>
