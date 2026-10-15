<template>
  <div class="pb-12">
    <ViewHeader
      :tile="{ icon: 'ph:vinyl-record-fill', kind: 'tile-albums' }"
      :title="t('albums.title')"
      :eyebrow="t('nav.yourLibrary')"
      :subtitle="lib.albums.value.length ? t('albums.count', { count: lib.albums.value.length }) : t('albums.subtitle')"
    >
      <template v-if="lib.albums.value.length" #actions>
        <div class="filter">
          <Icon icon="ph:magnifying-glass" class="filter-icon" />
          <input
            v-model="query"
            type="text"
            class="field h-8 w-56 pl-8"
            :placeholder="t('albums.filterPlaceholder')"
            spellcheck="false"
            @keydown.esc="query = ''"
          />
        </div>
        <button class="btn-ghost h-8" @click="openSortMenu">
          {{ t(SORTS[sort]) }}
          <Icon icon="ph:sort-ascending" class="h-4 w-4" />
        </button>
        <button
          v-if="loose.length"
          class="btn-ghost h-8 w-8 justify-center px-0"
          :title="t('albums.more')"
          :aria-label="t('albums.more')"
          @click="openMoreMenu"
        >
          <Icon icon="ph:dots-three-bold" class="h-4 w-4" />
        </button>
      </template>
    </ViewHeader>

    <div v-if="!lib.loaded.value" class="grid-cards">
      <div v-for="n in 10" :key="n" class="p-2.5">
        <div class="skeleton aspect-square rounded-md" />
        <div class="skeleton mt-3 h-3 w-2/3" />
      </div>
    </div>

    <EmptyState
      v-else-if="lib.error.value && !lib.albums.value.length"
      icon="ph:cloud-warning"
      :title="t('library.failedLoad')"
    >
      <button class="btn-accent btn-pill press" @click="lib.refresh()">
        <Icon icon="ph:arrows-clockwise" class="h-4 w-4" />
        {{ t('common.retry') }}
      </button>
    </EmptyState>

    <EmptyState
      v-else-if="!lib.albums.value.length"
      icon="ph:vinyl-record"
      :title="t('albums.empty')"
      :text="loose.length ? t('albums.looseHint', { count: loose.length }) : t('albums.emptyHint')"
    >
      <button
        v-if="loose.length"
        class="btn-accent btn-pill press"
        :disabled="detailsRunning"
        @click="findAlbums"
      >
        <Icon icon="ph:magnifying-glass" class="h-4 w-4" />
        {{ detailsRunning ? t('albums.finding') : t('albums.findMissing') }}
      </button>
      <button v-else class="btn-accent btn-pill" @click="ui.focusSearch()">{{ t('nav.browse') }}</button>
    </EmptyState>

    <EmptyState
      v-else-if="!filtered.length"
      compact
      icon="ph:magnifying-glass"
      :title="t('albums.noResults')"
    />

    <div v-else class="grid-cards">
      <MediaCard
        v-for="a in shownAlbums"
        :key="a.artist + '|' + a.name"
        :item="{ name: a.name, cover: a.cover ? API.coverFileURL(a.cover, a.cover_v) : '' }"
        kind="album"
        :subtitle-text="`${a.artist} · ${t('nav.artistSongs', { count: a.count })}`"
        playable
        :menu="() => albumMenu(a)"
        @open="router.push(albumRoute(a))"
        @play="playRows(rowsOf(a), 0)"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, inject, nextTick, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { useLibrary, albumTracks, albumRoute } from '/src/model/library'
import { useUi } from '/src/model/ui'
import { localRow, playRows, shuffleRows, playNext, addToQueue, refreshRowDetails } from '/src/model/tracks'
import { detailsRunning } from '/src/model/details'
import { usePlaylists } from '/src/model/playlists'
import { openContextMenu } from '/src/model/contextMenu'
import { onRefresh } from '/src/model/useRefresh'
import { sortedBy } from '/src/model/textSort'
import { useI18n } from '/src/i18n'
import ViewHeader from '/src/components/ui/ViewHeader.vue'
import MediaCard from '/src/components/MediaCard.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'

// Every album there are saved songs from (see library._album_list): the
// library by the record, the way the shelf of a record shop has it.

const { t } = useI18n()
const router = useRouter()
const lib = useLibrary()
const ui = useUi()
const playlists = usePlaylists()
const query = ref('')

lib.ensureLoaded()
onRefresh(() => lib.refresh())

const SORTS = { recent: 'albums.sortRecent', name: 'albums.sortName', artist: 'albums.sortArtist' }
const SORT_KEY = 'dn.albumSort'
const sort = ref(
  (() => {
    try {
      const v = localStorage.getItem(SORT_KEY)
      return v && SORTS[v] ? v : 'recent'
    } catch {
      return 'recent'
    }
  })()
)
function setSort(v) {
  sort.value = v
  try {
    localStorage.setItem(SORT_KEY, v)
  } catch {
    // this run only
  }
}
function openSortMenu(e) {
  openContextMenu(
    e,
    [
      { header: t('library.sortBy') },
      ...Object.keys(SORTS).map((key) => ({
        label: t(SORTS[key]),
        checked: sort.value === key,
        action: () => setSort(key),
      })),
    ],
    { anchor: true }
  )
}

const sorted = computed(() => {
  const list = lib.albums.value
  if (sort.value === 'recent') return sortedBy(list, { by: (a) => a.added || 0, desc: true }, (a) => a.name)
  if (sort.value === 'artist') return sortedBy(list, (a) => a.artist, (a) => a.name)
  return sortedBy(list, (a) => a.name, (a) => a.artist)
})
const filtered = computed(() => {
  const terms = query.value.trim().toLowerCase().split(/\s+/).filter(Boolean)
  if (!terms.length) return sorted.value
  return sorted.value.filter((a) => {
    const hay = `${a.name} ${a.artist}`.toLowerCase()
    return terms.every((term) => hay.includes(term))
  })
})

// A batch of cards at a time, more as the page nears the end of them, the
// way Artists does it: no picture is fetched for a card nobody has reached.
const BATCH = 120
const limit = ref(BATCH)
const shownAlbums = computed(() => filtered.value.slice(0, limit.value))
watch([query, sort], () => {
  limit.value = BATCH
})
const pageScroller = inject('viewScroller', ref(null))
function moreIfNearEnd() {
  const sc = pageScroller.value
  if (!sc || limit.value >= filtered.value.length) return
  if (sc.scrollTop + sc.clientHeight > sc.scrollHeight - 1200) {
    limit.value += BATCH
    nextTick(moreIfNearEnd)
  }
}
let bound = null
function bindScroll() {
  unbindScroll()
  bound = pageScroller.value
  if (bound) bound.addEventListener('scroll', moreIfNearEnd, { passive: true })
  nextTick(moreIfNearEnd)
}
function unbindScroll() {
  if (bound) bound.removeEventListener('scroll', moreIfNearEnd)
  bound = null
}
onMounted(bindScroll)
onActivated(bindScroll)
watch(pageScroller, bindScroll)
onDeactivated(unbindScroll)
onBeforeUnmount(unbindScroll)

function rowsOf(album) {
  return albumTracks(album).map(localRow)
}

// Saved songs with no album at all. Most were saved one at a time before
// 4.9, which lost the album on the way in; looking their details up again
// finds it (see details._with_album). Songs that will not play are for a
// repair instead, and a single on no album simply stays loose.
const loose = computed(() =>
  lib.tracks.value.filter((tr) => tr.file && !tr.problem && !String(tr.album || '').trim())
)
function findAlbums() {
  return refreshRowDetails(loose.value.map(localRow))
}
function openMoreMenu(e) {
  openContextMenu(
    e,
    [
      { header: t('albums.looseHint', { count: loose.value.length }) },
      {
        label: t('albums.findMissing'),
        icon: 'ph:magnifying-glass',
        disabled: detailsRunning.value,
        action: findAlbums,
      },
    ],
    { anchor: true }
  )
}

function albumMenu(a) {
  return [
    { label: t('actions.play'), icon: 'ph:play', action: () => playRows(rowsOf(a), 0, { toggle: false }) },
    { label: t('actions.shuffle'), icon: 'ph:shuffle', action: () => shuffleRows(rowsOf(a)) },
    { label: t('actions.playNext'), icon: 'ph:queue', action: () => playNext(rowsOf(a)) },
    { label: t('actions.addToQueue'), icon: 'ph:list-plus', action: () => addToQueue(rowsOf(a)) },
    { label: t('playlists.addTo'), icon: 'ph:playlist', action: () => playlists.pickPlaylist(rowsOf(a)) },
    { divider: true },
    { label: t('albums.open'), icon: 'ph:vinyl-record', action: () => router.push(albumRoute(a)) },
    {
      label: t('actions.goToArtist'),
      icon: 'ph:user',
      action: () => router.push({ name: 'Artist', params: { name: a.artist } }),
    },
  ]
}
</script>

<style scoped>
.grid-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: 4px 6px;
  padding: 0 14px;
}
@media (min-width: 1024px) {
  .grid-cards {
    padding: 0 22px;
  }
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
  color: rgb(var(--c-fg) / var(--fg-45));
  pointer-events: none;
}
</style>
