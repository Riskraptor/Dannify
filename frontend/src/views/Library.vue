<template>
  <div class="pb-12">
    <ViewHeader :title="t('library.title')" :eyebrow="t('nav.yourLibrary')">
      <template #meta>
        <template v-if="lib.tracks.value.length">
          {{ t('library.summary', { count: lib.tracks.value.length, duration: totalDuration }) }}
        </template>
        <template v-else>{{ t('library.subtitle') }}</template>
      </template>
    </ViewHeader>

    <div v-if="lib.tracks.value.length" class="toolbar view-pad">
      <button class="play-fab" :title="t('library.play')" @click="playAll">
        <Icon :icon="playingHere ? 'ph:pause-fill' : 'ph:play-fill'" class="h-5 w-5" />
      </button>
      <button class="icon-btn is-round h-10 w-10" :title="t('actions.shuffle')" @click="shuffleRows(rows)">
        <Icon icon="ph:shuffle" class="h-6 w-6" />
      </button>
      <button
        v-if="desktop.isDesktop"
        class="icon-btn is-round h-10 w-10"
        :title="t('settings.openFolder')"
        @click="desktop.openLibraryFolder()"
      >
        <Icon icon="ph:folder-open" class="h-[22px] w-[22px]" />
      </button>
      <button
        class="icon-btn is-round h-10 w-10"
        :title="`${t('common.refresh')} (F5)`"
        :disabled="lib.loading.value"
        @click="lib.refresh()"
      >
        <Icon icon="ph:arrows-clockwise" class="h-5 w-5" :class="{ 'animate-spin': lib.loading.value }" />
      </button>

      <div class="ml-auto flex items-center gap-2">
        <div class="filter">
          <Icon icon="ph:magnifying-glass" class="filter-icon" />
          <input
            v-model="query"
            type="text"
            class="field h-8 w-56 pl-8 pr-7"
            :placeholder="t('library.filterPlaceholder')"
            spellcheck="false"
            @keydown.esc="query = ''"
          />
          <button v-if="query" class="filter-clear" @click="query = ''">
            <Icon icon="ph:x" class="h-3.5 w-3.5" />
          </button>
        </div>
        <button class="btn-ghost h-8" @click="openSortMenu">
          {{ t('library.sort.' + sortKey) }}
          <Icon :icon="sortDir === 'asc' ? 'ph:sort-ascending' : 'ph:sort-descending'" class="h-4 w-4" />
        </button>
      </div>
    </div>

    <div class="view-pad">
      <div v-if="!lib.loaded.value" class="space-y-2 pt-2">
        <div v-for="n in 8" :key="n" class="skeleton h-12" />
      </div>

      <!-- The load failed. Before this the view just kept its skeleton rows
           and there was nothing to press. -->
      <EmptyState
        v-else-if="lib.error.value && !lib.tracks.value.length"
        icon="ph:cloud-warning"
        :title="t('library.failedLoad')"
      >
        <button class="btn-accent btn-pill press" @click="lib.refresh()">
          <Icon icon="ph:arrows-clockwise" class="h-4 w-4" />
          {{ t('common.retry') }}
        </button>
      </EmptyState>

      <EmptyState
        v-else-if="!lib.tracks.value.length"
        icon="ph:music-notes"
        :title="t('library.empty')"
        :text="t('library.emptyHint')"
      >
        <button class="btn-accent btn-pill" @click="ui.focusSearch()">
          <Icon icon="ph:magnifying-glass" class="h-4 w-4" />
          {{ t('nav.browse') }}
        </button>
      </EmptyState>

      <EmptyState
        v-else-if="!rows.length"
        compact
        icon="ph:magnifying-glass"
        :title="t('library.noResults')"
      />

      <TrackTable
        v-else
        :rows="rows"
        show-added
        sortable
        deletable
        :sort-key="sortKey"
        :sort-dir="sortDir"
        @sort="setSort"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onActivated } from 'vue'
import { useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useLibrary } from '/src/model/library'
import { usePlayer } from '/src/model/player'
import { useUi } from '/src/model/ui'
import { localRow, playRows, shuffleRows } from '/src/model/tracks'
import { openContextMenu } from '/src/model/contextMenu'
import { onRefresh } from '/src/model/useRefresh'
import { desktop } from '/src/desktop/bridge'
import { useI18n } from '/src/i18n'
import ViewHeader from '/src/components/ui/ViewHeader.vue'
import TrackTable from '/src/components/ui/TrackTable.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'

const { t } = useI18n()
const route = useRoute()
const lib = useLibrary()
const player = usePlayer()
const ui = useUi()

const SORT_KEY = 'dn.librarySort'
const saved = (() => {
  try {
    return JSON.parse(localStorage.getItem(SORT_KEY) || 'null')
  } catch {
    return null
  }
})()
const sortKey = ref(saved?.key || 'title') // title | artist | album | duration | added
const sortDir = ref(saved?.dir || 'asc')
const query = ref('')

lib.ensureLoaded()
onRefresh(() => lib.refresh())
onActivated(() => {
  lib.ensureLoaded()
  if (route.query.sort === 'added') {
    sortKey.value = 'added'
    sortDir.value = 'desc'
  }
})

function norm(s) {
  return String(s || '').toLowerCase()
}

const rows = computed(() => {
  let list = lib.tracks.value
  const q = query.value.trim().toLowerCase()
  if (q) {
    const terms = q.split(/\s+/)
    list = list.filter((tr) => {
      const hay = `${tr.title} ${tr.artist_display || tr.artist} ${tr.album}`.toLowerCase()
      return terms.every((term) => hay.includes(term))
    })
  }
  const dir = sortDir.value === 'asc' ? 1 : -1
  const key = sortKey.value
  const sorted = [...list].sort((a, b) => {
    if (key === 'duration' || key === 'added') return ((a[key] || 0) - (b[key] || 0)) * dir
    const av = key === 'artist' ? norm(a.artist_display || a.artist) : norm(a[key])
    const bv = key === 'artist' ? norm(b.artist_display || b.artist) : norm(b[key])
    return av.localeCompare(bv) * dir || norm(a.title).localeCompare(norm(b.title))
  })
  return sorted.map(localRow)
})

const totalDuration = computed(() => {
  const secs = lib.tracks.value.reduce((s, tr) => s + (tr.duration || 0), 0)
  const h = Math.floor(secs / 3600)
  const m = Math.round((secs % 3600) / 60)
  return h ? t('common.hoursMinutes', { h, m }) : t('common.minutes', { m })
})

const playingHere = computed(() => {
  const cur = player.currentTrack.value
  return !!cur && cur.type === 'local' && player.isPlaying.value
})

function playAll() {
  if (playingHere.value) {
    player.toggle()
    return
  }
  playRows(rows.value, 0)
}

function setSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = key === 'added' || key === 'duration' ? 'desc' : 'asc'
  }
  try {
    localStorage.setItem(SORT_KEY, JSON.stringify({ key: sortKey.value, dir: sortDir.value }))
  } catch {
    // ignore
  }
}

function openSortMenu(e) {
  openContextMenu(
    e,
    [
      { header: t('library.sortBy') },
      ...['title', 'artist', 'album', 'added', 'duration'].map((key) => ({
        label: t('library.sort.' + key),
        checked: sortKey.value === key,
        action: () => setSort(key),
      })),
    ],
    { anchor: true }
  )
}
</script>

<style scoped>
.toolbar {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding-bottom: 16px;
}
.filter {
  position: relative;
}
.filter-icon {
  position: absolute;
  left: 9px;
  top: 50%;
  width: 15px;
  height: 15px;
  transform: translateY(-50%);
  color: rgb(var(--c-fg) / 0.45);
  pointer-events: none;
}
.filter-clear {
  position: absolute;
  right: 5px;
  top: 50%;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  transform: translateY(-50%);
  border-radius: 4px;
  color: rgb(var(--c-fg) / 0.55);
}
.filter-clear:hover {
  background: rgb(var(--c-tint) / 0.1);
}
</style>
