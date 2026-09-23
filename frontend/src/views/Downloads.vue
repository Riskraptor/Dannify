<template>
  <div class="pb-12">
    <ViewHeader :title="t('downloads.title')" :subtitle="summary">
      <template #actions>
        <button
          v-if="desktop.isDesktop"
          class="btn"
          @click="desktop.openLibraryFolder()"
        >
          <Icon icon="ph:folder-open" class="h-4 w-4" />
          {{ t('settings.openFolder') }}
        </button>
        <button v-if="stats.done > 0" class="btn" @click="clearFinished">
          <Icon icon="ph:broom" class="h-4 w-4" />
          {{ t('downloads.clearFinished') }}
        </button>
        <button v-if="items.length" class="btn-ghost text-danger hover:text-danger" @click="clearAll">
          <Icon icon="ph:trash" class="h-4 w-4" />
          {{ t('queue.clearAll') }}
        </button>
      </template>
    </ViewHeader>

    <div v-if="items.length" class="chips view-pad">
      <button
        v-for="f in filters"
        :key="f.id"
        class="chip"
        :class="{ 'is-active': filter === f.id }"
        @click="filter = f.id"
      >
        {{ f.label }}
        <span class="opacity-60">{{ f.count }}</span>
      </button>
    </div>

    <EmptyState
      v-if="!items.length"
      icon="ph:download-simple"
      :title="t('queue.empty')"
      :text="t('queue.emptyHint')"
    >
      <button class="btn-accent btn-pill" @click="ui.focusSearch()">
        <Icon icon="ph:magnifying-glass" class="h-4 w-4" />
        {{ t('nav.browse') }}
      </button>
    </EmptyState>

    <EmptyState v-else-if="!visible.length" compact icon="ph:funnel" :title="t('downloads.nothingHere')" />

    <div v-else class="view-pad">
      <VirtualList :items="visible" :item-height="64" :scroller="scroller" :item-key="(it) => keyOf(it)">
        <template #default="{ item }">
          <div class="dl-row" @contextmenu="onMenu($event, item)" @dblclick="playItem(item)">
            <CoverImage :src="item.song.cover_url" radius="sm" class="h-11 w-11" />
            <div class="min-w-0 flex-1">
              <p class="truncate text-[14px] font-medium">{{ item.song.name }}</p>
              <p class="truncate text-[12.5px] text-fg/55">{{ artistsOf(item.song) }}</p>
            </div>

            <div class="dl-status">
              <template v-if="stateOf(item) === 'active'">
                <div class="flex items-center justify-between text-[11.5px] text-fg/55">
                  <span class="truncate">{{ stageLabel(item) }}</span>
                  <span v-if="!isWarmingUp(item)" class="font-tnum">
                    {{ Math.round(item.progress || 0) }}%
                  </span>
                </div>
                <!-- Finding the source and solving the player take ten-odd
                     seconds before a byte arrives. A sweeping bar says
                     "working" where a 0% bar said "stuck". -->
                <div class="progress-track mt-1.5" :class="{ 'is-indeterminate': isWarmingUp(item) }">
                  <div
                    class="progress-fill"
                    :style="isWarmingUp(item) ? null : { width: `${Math.max(2, item.progress || 0)}%` }"
                  />
                </div>
              </template>
              <span v-else-if="stateOf(item) === 'queued'" class="pill-muted">
                <Icon icon="ph:clock" class="h-3 w-3" /> {{ t('downloads.statusQueued') }}
              </span>
              <span v-else-if="stateOf(item) === 'done'" class="pill-accent">
                <Icon icon="ph:check-bold" class="h-3 w-3" /> {{ t('downloads.statusDone') }}
              </span>
              <span v-else class="pill-danger" :title="t('downloads.statusErrorHint')">
                <Icon icon="ph:warning-bold" class="h-3 w-3" /> {{ t('downloads.statusError') }}
              </span>
            </div>

            <div class="dl-actions">
              <button
                v-if="stateOf(item) === 'done' && item.filename"
                class="icon-btn"
                :title="t('actions.play')"
                @click="playItem(item)"
              >
                <Icon icon="ph:play-fill" class="h-4 w-4" />
              </button>
              <button
                v-if="stateOf(item) === 'done' && item.filename && desktop.isDesktop"
                class="icon-btn"
                :title="t('actions.showInFolder')"
                @click="desktop.revealInFolder(item.filename)"
              >
                <Icon icon="ph:folder-open" class="h-4 w-4" />
              </button>
              <button
                v-if="stateOf(item) === 'error'"
                class="icon-btn"
                :title="t('common.retry')"
                @click="retry(item)"
              >
                <Icon icon="ph:arrow-clockwise" class="h-4 w-4" />
              </button>
              <button
                class="icon-btn hover:text-danger"
                :title="t('queue.removeFromQueue')"
                @click="dm.remove(item.song)"
              >
                <Icon icon="ph:x" class="h-4 w-4" />
              </button>
            </div>
          </div>
        </template>
      </VirtualList>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject } from 'vue'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { useProgressTracker, useDownloadManager } from '/src/model/download'
import { useDownloadStats } from '/src/model/downloadStats'
import { usePlayer } from '/src/model/player'
import { useUi } from '/src/model/ui'
import { openContextMenu } from '/src/model/contextMenu'
import { confirmDialog } from '/src/model/dialog'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'
import ViewHeader from '/src/components/ui/ViewHeader.vue'
import VirtualList from '/src/components/ui/VirtualList.vue'
import CoverImage from '/src/components/ui/CoverImage.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'

const { t } = useI18n()
const pt = useProgressTracker()
const dm = useDownloadManager()
const statsRef = useDownloadStats()
const stats = computed(() => statsRef.value)
const player = usePlayer()
const ui = useUi()
const scroller = inject('viewScroller', ref(null))

const filter = ref('all')
const items = computed(() => pt.downloadQueue.value)

// True while we are still working out what to fetch: there is no byte
// count to show yet, so the bar sweeps instead of sitting at zero.
function isWarmingUp(item) {
  return (item.progress || 0) < 4
}

const STAGE_KEYS = {
  'Finding source': 'downloads.stageFinding',
  Preparing: 'downloads.stagePreparing',
  Connecting: 'downloads.stageConnecting',
  Downloading: 'downloads.statusDownloading',
  Converting: 'downloads.stageConverting',
  Tagging: 'downloads.stageTagging',
  Done: 'downloads.statusDone',
}

function stageLabel(item) {
  const key = STAGE_KEYS[item.message]
  if (key) return t(key)
  return item.message || t('downloads.statusDownloading')
}

function stateOf(item) {
  if (item.isErrored()) return 'error'
  if (item.isDownloaded()) return 'done'
  if (item.isDownloading() || (item.progress || 0) > 0) return 'active'
  return 'queued'
}

const filters = computed(() => [
  { id: 'all', label: t('downloads.filterAll'), count: items.value.length },
  { id: 'active', label: t('downloads.filterActive'), count: stats.value.active },
  { id: 'done', label: t('downloads.filterDone'), count: stats.value.done },
  { id: 'error', label: t('downloads.filterFailed'), count: stats.value.failed },
])

const visible = computed(() => {
  // Newest first; failures and active downloads float to the top.
  const rank = { error: 0, active: 1, queued: 2, done: 3 }
  const list = [...items.value].reverse()
  const filtered =
    filter.value === 'all'
      ? list
      : list.filter((it) => {
          const s = stateOf(it)
          return filter.value === 'active' ? s === 'active' || s === 'queued' : s === filter.value
        })
  return filtered.sort((a, b) => rank[stateOf(a)] - rank[stateOf(b)])
})

const summary = computed(() => {
  const s = stats.value
  if (!s.total) return t('queue.subtitle')
  const parts = []
  if (s.active) parts.push(t('downloads.summaryActive', { count: s.active }))
  if (s.done) parts.push(t('downloads.summaryDone', { count: s.done }))
  if (s.failed) parts.push(t('downloads.summaryFailed', { count: s.failed }))
  return parts.join(' · ')
})

function keyOf(item) {
  return String(item.song.song_id || item.song.url || item.song.name)
}

function artistsOf(song) {
  if (Array.isArray(song.artists) && song.artists.length) return song.artists.join(', ')
  return song.artist || t('common.unknownArtist')
}

function playItem(item) {
  if (!item.filename) return
  player.setPlaylist(
    [
      {
        type: 'local',
        file: item.filename,
        url: API.downloadFileURL(item.filename),
        cover: API.coverFileURL(item.filename),
        title: item.song.name,
        artist: artistsOf(item.song),
        album: item.song.album_name || '',
        duration: item.song.duration || 0,
      },
    ],
    { startIndex: 0 }
  )
}

function retry(item) {
  item.setDownloading()
  item.progress = 0
  item.message = ''
  dm.downloadSongs([item.song])
}

function onMenu(e, item) {
  const s = stateOf(item)
  openContextMenu(e, [
    s === 'done' && item.filename && { label: t('actions.play'), icon: 'ph:play', action: () => playItem(item) },
    s === 'done' &&
      item.filename &&
      desktop.isDesktop && {
        label: t('actions.showInFolder'),
        icon: 'ph:folder-open',
        action: () => desktop.revealInFolder(item.filename),
      },
    s === 'error' && { label: t('common.retry'), icon: 'ph:arrow-clockwise', action: () => retry(item) },
    { divider: true },
    { label: t('queue.removeFromQueue'), icon: 'ph:x', action: () => dm.remove(item.song) },
  ])
}

function clearFinished() {
  for (const it of [...items.value]) {
    if (it.isDownloaded()) dm.remove(it.song)
  }
}

async function clearAll() {
  const ok = await confirmDialog({
    title: t('queue.clearAll'),
    message: t('queue.clearAllPrompt'),
    confirmText: t('queue.clearAll'),
    danger: true,
    icon: 'ph:trash',
  })
  if (ok) await dm.clearAll()
}
</script>

<style scoped>
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-bottom: 12px;
}
.dl-row {
  display: flex;
  align-items: center;
  gap: 14px;
  height: 60px;
  padding: 0 12px;
  border-radius: 6px;
}
.dl-row:hover {
  background: rgb(var(--c-tint) / 0.05);
}
.dl-status {
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: clamp(120px, 26%, 260px);
  flex-shrink: 0;
}
.dl-status .pill-muted,
.dl-status .pill-accent,
.dl-status .pill-danger {
  align-self: flex-start;
}
.dl-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  width: 112px;
  flex-shrink: 0;
}
</style>
