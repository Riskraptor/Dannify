<template>
  <div class="pb-12">
    <div v-if="state === 'loading'" class="view-pad space-y-2 pt-10">
      <div class="skeleton mb-8 h-48 w-48" />
      <div v-for="n in 6" :key="n" class="skeleton h-14" />
    </div>

    <EmptyState
      v-else-if="state === 'missing'"
      icon="ph:playlist"
      :title="t('playlists.notFound')"
      :text="t('playlists.notFoundHint')"
    >
      <router-link :to="{ name: 'Library' }" class="btn btn-pill">{{ t('nav.songs') }}</router-link>
    </EmptyState>

    <EmptyState
      v-else-if="state === 'error'"
      icon="ph:warning"
      :title="t('playlists.couldNotLoad')"
    >
      <button class="btn btn-pill" @click="load">{{ t('common.retry') }}</button>
    </EmptyState>

    <template v-else>
      <CollectionHero
        :title="data.name"
        :label="t('playlists.playlist')"
        :cover="heroCover"
        kind="playlist"
        :playable="rows.length > 0"
        :playing="playingHere"
        @play="playAll"
      >
        <template #cover>
          <button class="pl-cover" :title="t('playlists.rename')" @click="rename">
            <PlaylistArt :covers="data.covers" :size="232" eager class="h-full w-full" />
          </button>
        </template>
        <template #meta>
          <span>{{ t('playlists.songsCount', { count: rows.length }) }}</span>
          <template v-if="totalDuration">
            <span class="opacity-50">•</span>
            <span class="text-fg/60">{{ totalDuration }}</span>
          </template>
        </template>
        <template #actions>
          <button class="play-fab" :disabled="!rows.length" :title="t('explore.play')" @click="playAll">
            <Icon :icon="playingHere ? 'ph:pause-fill' : 'ph:play-fill'" class="h-5 w-5" />
          </button>
          <button
            class="icon-btn is-round h-10 w-10"
            :disabled="!rows.length"
            :title="t('actions.shuffle')"
            @click="shuffleRows(rows)"
          >
            <Icon icon="ph:shuffle" class="h-6 w-6" />
          </button>
          <button v-if="pendingCount > 0" class="btn btn-pill" @click="downloadRows(rows)">
            <Icon icon="ph:download-simple" class="h-4 w-4" />
            {{ t('explore.downloadRemaining', { count: pendingCount }) }}
          </button>
          <span v-else-if="rows.length" class="pill-accent h-7 px-3 text-xs">
            <Icon icon="ph:check-circle-fill" class="h-4 w-4" />
            {{ t('explore.allInLibrary') }}
          </span>
          <button class="icon-btn is-round h-10 w-10" :title="t('actions.more')" @click="onMore">
            <Icon icon="ph:dots-three-bold" class="h-6 w-6" />
          </button>
        </template>
      </CollectionHero>

      <EmptyState
        v-if="!rows.length"
        icon="ph:music-notes-plus"
        :title="t('playlists.empty')"
        :text="t('playlists.emptyHint')"
      >
        <button class="btn-accent btn-pill" @click="ui.focusSearch()">
          <Icon icon="ph:magnifying-glass" class="h-4 w-4" />
          {{ t('playlists.findSongs') }}
        </button>
      </EmptyState>
      <div v-else class="view-pad">
        <p v-if="rows.length > 1" class="pl-hint">
          <Icon icon="ph:dots-six-vertical" class="h-3.5 w-3.5" />
          {{ t('playlists.dragToReorder') }}
        </p>
        <TrackTable
          :rows="rows"
          :sticky-offset="56"
          selectable
          selection-bar
          reorderable
          :on-play="(i) => playRows(rows, i)"
          :on-remove="removeRows"
          :menu-context="{ playlist: { remove: removeRows } }"
          @reorder="reorder"
        />
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { usePlayer } from '/src/model/player'
import { useUi } from '/src/model/ui'
import { useLibrary } from '/src/model/library'
import { useLibraryIndex } from '/src/model/libraryIndex'
import { usePlaylists, entryRow, coverURL } from '/src/model/playlists'
import { openContextMenu } from '/src/model/contextMenu'
import { toast } from '/src/model/toast'
import {
  playRows,
  shuffleRows,
  downloadRows,
  isRowCurrent,
  isRowDownloaded,
  isRowDownloading,
  addToQueue,
} from '/src/model/tracks'
import { onRefresh } from '/src/model/useRefresh'
import { useI18n } from '/src/i18n'
import CollectionHero from '/src/components/ui/CollectionHero.vue'
import TrackTable from '/src/components/ui/TrackTable.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'
import PlaylistArt from '/src/components/ui/PlaylistArt.vue'

const { t } = useI18n()
const route = useRoute()
const player = usePlayer()
const ui = useUi()
const lib = useLibrary()
const libIndex = useLibraryIndex()
const playlists = usePlaylists()

lib.ensureLoaded()
libIndex.load()

const pid = computed(() => String(route.params.id || ''))
const state = ref('loading')
const data = ref({ name: '', covers: [], tracks: [] })

async function load() {
  const id = pid.value
  if (!id) return
  if (!data.value.tracks.length) state.value = 'loading'
  try {
    const res = await API.getPlaylist(id)
    if (id !== pid.value) return
    data.value = res.data
    playlists.remember(res.data)
    state.value = 'ready'
  } catch (err) {
    if (id !== pid.value) return
    state.value = err && err.response && err.response.status === 404 ? 'missing' : 'error'
  }
}

watch(pid, () => {
  data.value = { name: '', covers: [], tracks: [] }
  load()
}, { immediate: true })

// Songs added from somewhere else (a menu, a drop on the side bar) while
// this page is open: its summary moves on, and the page follows.
watch(
  () => {
    const p = playlists.list.value.find((x) => x.id === pid.value)
    return p ? p.updated : null
  },
  (updated) => {
    if (state.value === 'ready' && updated && updated > (data.value.updated || 0)) load()
  }
)
onRefresh(load)

// Rebuilt when the library changes: a song saved since it was added plays
// from disk, and one deleted plays from YouTube again.
const rows = computed(() => {
  void lib.tracks.value
  void libIndex.byVideoId.value
  return (data.value.tracks || []).map(entryRow)
})

const heroCover = computed(() => coverURL((data.value.covers || [])[0] || ''))

const pendingCount = computed(() => {
  void libIndex.byVideoId.value
  return rows.value.filter((r) => !r.gone && !isRowDownloaded(r) && !isRowDownloading(r)).length
})

const totalDuration = computed(() => {
  const secs = rows.value.reduce((s, r) => s + (r.duration || 0), 0)
  if (!secs) return ''
  const h = Math.floor(secs / 3600)
  const m = Math.round((secs % 3600) / 60)
  return h ? t('common.hoursMinutes', { h, m }) : t('common.minutes', { m })
})

const currentHere = computed(() => rows.value.some((r) => isRowCurrent(r)))
const playingHere = computed(() => currentHere.value && player.isPlaying.value)

function playAll() {
  if (currentHere.value) return player.toggle()
  playRows(rows.value, 0)
}

async function save(entries) {
  const saved = await playlists.setEntries(pid.value, entries)
  if (saved) data.value = saved
  return saved
}

async function removeRows(chosen) {
  const drop = new Set(chosen.map((r) => r.playlistIndex).filter((i) => i != null))
  if (!drop.size) return
  const before = data.value.tracks
  const kept = before.filter((_, i) => !drop.has(i))
  // Gone from the page at once; the server catches up.
  data.value = { ...data.value, tracks: kept }
  const saved = await save(kept)
  if (!saved) {
    data.value = { ...data.value, tracks: before }
    return
  }
  toast(t('playlists.removed', { name: saved.name }), {
    icon: 'ph:minus-circle',
    action: { label: t('actions.undo'), run: () => save(before) },
  })
}

// Rows dragged to a new place. `to` is where they go in the list as it was
// shown, before they were taken out.
async function reorder({ rows: moved, to }) {
  const picked = new Set(moved.map((r) => r.playlistIndex))
  const before = data.value.tracks
  const taken = before.filter((_, i) => picked.has(i))
  const rest = before.filter((_, i) => !picked.has(i))
  const at = to - [...picked].filter((i) => i < to).length
  const next = [...rest.slice(0, at), ...taken, ...rest.slice(at)]
  if (next.every((e, i) => e === before[i])) return
  data.value = { ...data.value, tracks: next }
  if (!(await save(next))) data.value = { ...data.value, tracks: before }
}

async function rename() {
  const saved = await playlists.renamePlaylist(pid.value)
  if (saved) data.value = { ...data.value, name: saved.name }
}

function onMore(e) {
  openContextMenu(
    e,
    [
      { label: t('playlists.rename'), icon: 'ph:pencil-simple', action: rename },
      rows.value.length && {
        label: t('actions.addToQueue'),
        icon: 'ph:list-plus',
        action: () => addToQueue(rows.value),
      },
      { divider: true },
      {
        label: t('playlists.delete'),
        icon: 'ph:trash',
        danger: true,
        action: () => playlists.deletePlaylist(pid.value),
      },
    ],
    { anchor: true }
  )
}
</script>

<style scoped>
.pl-cover {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: 6px;
  overflow: hidden;
  box-shadow: 0 8px 24px rgb(0 0 0 / 0.35);
}
.pl-cover:focus-visible {
  outline: 2px solid rgb(var(--c-accent));
  outline-offset: 2px;
}
.pl-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 0 0 6px;
  font-size: 11.5px;
  color: rgb(var(--c-fg) / 0.4);
}
</style>
