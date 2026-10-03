<template>
  <div class="pb-12">
    <ViewHeader
      :tile="{ icon: 'ph:users-three-fill', kind: 'tile-artists' }"
      :title="t('artists.title')"
      :eyebrow="t('nav.yourLibrary')"
      :subtitle="lib.artists.value.length ? t('artists.count', { count: lib.artists.value.length }) : t('artists.subtitle')"
    >
      <template v-if="lib.artists.value.length" #actions>
        <button class="btn btn-pill h-8 text-xs" :disabled="refreshing" @click="refreshPictures">
          <Icon icon="ph:arrows-clockwise" class="h-4 w-4" :class="{ 'animate-spin': refreshing }" />
          {{ t('details.refreshPictures') }}
        </button>
        <div class="filter">
          <Icon icon="ph:magnifying-glass" class="filter-icon" />
          <input
            v-model="query"
            type="text"
            class="field h-8 w-56 pl-8"
            :placeholder="t('artists.searchPlaceholder')"
            spellcheck="false"
            @keydown.esc="query = ''"
          />
        </div>
      </template>
    </ViewHeader>

    <div v-if="!lib.loaded.value" class="grid-cards view-pad">
      <div v-for="n in 10" :key="n" class="p-2.5">
        <div class="skeleton aspect-square rounded-full" />
        <div class="skeleton mt-3 h-3 w-2/3" />
      </div>
    </div>

    <!-- The load failed. This used to say the library was empty, which sent
         people looking for songs that were sitting right there. -->
    <EmptyState
      v-else-if="lib.error.value && !lib.artists.value.length"
      icon="ph:cloud-warning"
      :title="t('library.failedLoad')"
    >
      <button class="btn-accent btn-pill press" @click="lib.refresh()">
        <Icon icon="ph:arrows-clockwise" class="h-4 w-4" />
        {{ t('common.retry') }}
      </button>
    </EmptyState>

    <EmptyState
      v-else-if="!lib.artists.value.length"
      icon="ph:users-three"
      :title="t('artists.empty')"
      :text="t('library.emptyHint')"
    >
      <button class="btn-accent btn-pill" @click="ui.focusSearch()">{{ t('nav.browse') }}</button>
    </EmptyState>

    <template v-else>
      <div v-if="filtered.length" class="grid-cards">
        <MediaCard
          v-for="a in shownArtists"
          :key="a.name"
          :item="{
            name: a.name,
            cover: artistLinks.artistPhoto(a.name, 336),
            fallback: a.cover ? API.coverFileURL(a.cover, a.cover_v) : '',
          }"
          kind="artist"
          :subtitle-text="t('nav.artistSongs', { count: a.count })"
          playable
          :menu="() => artistMenu(a)"
          @open="open(a)"
          @play="playRows(rowsFor(a.name), 0)"
        />
      </div>
      <EmptyState
        v-else-if="!songMatches.length"
        compact
        icon="ph:magnifying-glass"
        :title="t('artists.noResults')"
      />

      <section v-if="songMatches.length" class="view-pad mt-6">
        <h2 class="mb-3 text-lg font-bold">{{ t('artists.tracks') }}</h2>
        <TrackTable :rows="songMatches" />
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, inject, nextTick, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { useLibrary } from '/src/model/library'
import { useUi } from '/src/model/ui'
import { localRow, playRows, shuffleRows, onArtistPage } from '/src/model/tracks'
import { onRefresh } from '/src/model/useRefresh'
import { useI18n } from '/src/i18n'
import { useArtistLinks } from '/src/model/artistLinks'
import { refreshArtists } from '/src/model/details'
import { sortedBy } from '/src/model/textSort'
import ViewHeader from '/src/components/ui/ViewHeader.vue'
import MediaCard from '/src/components/MediaCard.vue'
import TrackTable from '/src/components/ui/TrackTable.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'

const { t } = useI18n()
const router = useRouter()
const lib = useLibrary()
const ui = useUi()
const query = ref('')

lib.ensureLoaded()
const artistLinks = useArtistLinks()
const refreshing = ref(false)
async function refreshPictures() {
  refreshing.value = true
  try {
    await refreshArtists([])
    await artistLinks.load()
  } finally {
    refreshing.value = false
  }
}
onRefresh(() => lib.refresh())

const sortedArtists = computed(() => sortedBy(lib.artists.value, (a) => a.name))
const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  const list = sortedArtists.value
  return q ? list.filter((a) => a.name.toLowerCase().includes(q)) : list
})

// A batch of cards at a time, more as the page nears the end of them: a
// library of thousands of artists used to draw every card, and fetch every
// picture, the moment the page opened.
const BATCH = 120
const limit = ref(BATCH)
const shownArtists = computed(() => filtered.value.slice(0, limit.value))
watch(query, () => {
  limit.value = BATCH
})
const pageScroller = inject('viewScroller', ref(null))
function moreIfNearEnd() {
  const sc = pageScroller.value
  if (!sc || limit.value >= filtered.value.length) return
  if (sc.scrollTop + sc.clientHeight > sc.scrollHeight - 1200) {
    limit.value += BATCH
    // A tall window may still not be full: look again once these are drawn.
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
// Opened straight onto this page, it is up before the app's scroll pane is:
// bound as soon as that is there.
watch(pageScroller, bindScroll)
onDeactivated(unbindScroll)
onBeforeUnmount(unbindScroll)

const songMatches = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (q.length < 2) return []
  return lib.tracks.value
    .filter((tr) => `${tr.title} ${tr.album}`.toLowerCase().includes(q))
    .slice(0, 50)
    .map(localRow)
})

function rowsFor(name) {
  return lib.tracks.value
    .filter((tr) => onArtistPage(tr, name))
    .map(localRow)
}

function open(a) {
  router.push({ name: 'Artist', params: { name: a.name } })
}

function artistMenu(a) {
  return [
    { label: t('actions.play'), icon: 'ph:play', action: () => playRows(rowsFor(a.name), 0) },
    { label: t('actions.shuffle'), icon: 'ph:shuffle', action: () => shuffleRows(rowsFor(a.name)) },
    { divider: true },
    { label: t('actions.openArtist'), icon: 'ph:user', action: () => open(a) },
    {
      label: t('details.refresh'),
      icon: 'ph:arrows-clockwise',
      action: () => refreshArtists([a.name], rowsFor(a.name).map((r) => r.file)),
    },
    {
      label: t('actions.searchOnline'),
      icon: 'ph:globe',
      action: () => router.push({ name: 'Search', params: { query: a.name } }),
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
  color: rgb(var(--c-fg) / 0.45);
  pointer-events: none;
}
</style>
