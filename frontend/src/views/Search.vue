<template>
  <div class="pb-12">
    <!-- Filter chips stick under the top edge while scrolling results -->
    <div v-if="state.query" class="chips-bar view-pad">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="chip"
        :class="{ 'is-active': state.activeTab === tab.id }"
        @click="setTab(tab.id)"
      >
        {{ t(tab.label) }}
        <span v-if="tab.id !== 'all' && counts[tab.id]" class="opacity-60">{{ counts[tab.id] }}</span>
      </button>
      <!-- Movement while a newer query loads, instead of blanking the page. -->
      <Transition name="soft">
        <span v-if="showSearching" class="chips-busy">
          <span class="chips-busy-dot" />
          {{ t('search.searching') }}
        </span>
      </Transition>
    </div>

    <!-- Nothing typed yet: recent searches -->
    <template v-if="!state.query">
      <ViewHeader :title="t('nav.search')" :subtitle="t('explore.typeToBegin')" />
      <section v-if="recent.searches.value.length" class="view-pad">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-lg font-bold">{{ t('search.recent') }}</h2>
          <button class="btn-ghost h-7 text-xs" @click="recent.clearSearches()">
            {{ t('search.clearRecent') }}
          </button>
        </div>
        <div class="flex flex-wrap gap-2">
          <span v-for="q in recent.searches.value" :key="q" class="recent-chip">
            <button class="recent-chip-main" @click="openQuery(q)">
              <Icon icon="ph:clock-counter-clockwise" class="h-4 w-4 text-fg/45" />
              {{ q }}
            </button>
            <button class="recent-chip-x" :title="t('search.removeRecent')" @click="recent.forgetSearch(q)">
              <Icon icon="ph:x" class="h-3.5 w-3.5" />
            </button>
          </span>
        </div>
      </section>
      <EmptyState
        v-else
        icon="ph:magnifying-glass"
        :title="t('search.emptyTitle')"
        :text="t('search.emptyHintLong')"
      >
        <button class="btn btn-pill" @click="ui.focusSearch()">
          <Icon icon="ph:magnifying-glass" class="h-4 w-4" />
          {{ t('search.startSearching') }}
        </button>
      </EmptyState>
    </template>

    <!-- Loading -->
    <div v-else-if="showSkeleton" class="view-pad pt-6">
      <div class="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div class="skeleton h-56 rounded-lg" />
        <div class="space-y-2">
          <div v-for="n in 4" :key="n" class="skeleton h-12" />
        </div>
      </div>
      <div class="mt-8 grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-4">
        <div v-for="n in 6" :key="n" class="skeleton aspect-square" />
      </div>
    </div>

    <!-- Error -->
    <EmptyState v-else-if="error" icon="ph:warning-circle" :title="t('search.error')" :text="error">
      <button class="btn btn-pill" @click="load(state.query, true)">{{ t('common.retry') }}</button>
    </EmptyState>

    <!-- No results -->
    <EmptyState
      v-else-if="!hasAny && !loading"
      icon="ph:magnifying-glass"
      :title="t('search.noResultsFor', { query: state.query })"
      :text="t('search.emptyHint')"
    />

    <!-- Results -->
    <template v-else-if="hasAny">
      <template v-if="state.activeTab === 'all'">
        <div class="top-grid view-pad rise-in">
          <section v-if="topResult" class="min-w-0">
            <h2 class="section-title">{{ t('search.topResult') }}</h2>
            <div
              class="top-card"
              role="button"
              tabindex="0"
              @click="openTop"
              @keydown.enter="openTop"
              @contextmenu="onTopMenu"
            >
              <CoverImage
                :src="topResult.item.cover_url"
                :kind="topResult.kind === 'song' ? 'track' : topResult.kind"
                :round="topResult.kind === 'artist'"
                radius="md"
                class="top-cover"
              />
              <p class="top-name">{{ topResult.item.name }}</p>
              <p class="mt-1 flex items-center gap-2 text-[13px] text-fg/60">
                <span v-if="topResult.subtitle" class="truncate">{{ topResult.subtitle }}</span>
                <span class="pill-muted shrink-0">{{ topResult.label }}</span>
              </p>
              <button class="top-play play-fab" :title="t('actions.play')" @click.stop="playTop">
                <Icon icon="ph:play-fill" class="h-5 w-5" />
              </button>
            </div>
          </section>
          <section v-if="songRows.length" class="min-w-0">
            <h2 class="section-title flex items-center justify-between">
              <span>{{ t('explore.songs') }}</span>
              <button v-if="songRows.length > 4" class="show-all" @click="setTab('songs')">
                {{ t('explore.showAll') }}
              </button>
            </h2>
            <TrackTable
              :rows="songRows.slice(0, 4)"
              :header="false"
              :show-index="false"
              :show-album="false"
              :on-play="(i) => playRows(songRows, i)"
            />
          </section>
        </div>

        <div class="shelves rise-in rise-delay-1">
          <Shelf
            v-if="data.artists.length"
            :title="t('explore.artists')"
            :more-label="data.artists.length > 5 ? t('explore.showAll') : ''"
            @more="setTab('artists')"
          >
            <MediaCard
              v-for="a in data.artists"
              :key="a.browse_id"
              :item="a"
              kind="artist"
              @open="ex.openArtist(a.browse_id)"
            />
          </Shelf>
          <Shelf
            v-if="data.albums.length"
            :title="t('explore.albums')"
            :more-label="data.albums.length > 5 ? t('explore.showAll') : ''"
            @more="setTab('albums')"
          >
            <MediaCard
              v-for="al in data.albums"
              :key="al.browse_id"
              :item="al"
              kind="album"
              @open="ex.openAlbum(al.browse_id)"
            />
          </Shelf>
          <Shelf
            v-if="data.playlists.length"
            :title="t('explore.playlists')"
            :more-label="data.playlists.length > 5 ? t('explore.showAll') : ''"
            @more="setTab('playlists')"
          >
            <MediaCard
              v-for="p in data.playlists"
              :key="p.browse_id"
              :item="p"
              kind="playlist"
              @open="ex.openPlaylist(p.browse_id)"
            />
          </Shelf>
        </div>
      </template>

      <div v-else-if="state.activeTab === 'songs'" class="view-pad pt-2 rise-in">
        <TrackTable
          :rows="songRows"
          :sticky-offset="56"
          :on-play="(i) => playRows(songRows, i)"
        />
      </div>

      <div v-else class="shelves pt-2 rise-in">
        <Shelf :title="t(tabs.find((x) => x.id === state.activeTab).label)" wrap>
          <MediaCard
            v-for="it in data[state.activeTab]"
            :key="it.browse_id"
            :item="it"
            :kind="kindFor(state.activeTab)"
            @open="openCard(state.activeTab, it)"
          />
        </Shelf>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, inject, onMounted, onActivated, onDeactivated } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { useExplore, useSearchState } from '/src/model/explore'
import { useLibraryIndex } from '/src/model/libraryIndex'
import { useSearchManager } from '/src/model/search'
import { useRecent } from '/src/model/recent'
import { reportNetworkFailure } from '/src/model/connectivity'
import { useUi } from '/src/model/ui'
import { songRow, playRows, trackMenu } from '/src/model/tracks'
import { openContextMenu } from '/src/model/contextMenu'
import { onRefresh } from '/src/model/useRefresh'
import { useI18n } from '/src/i18n'
import TrackTable from '/src/components/ui/TrackTable.vue'
import MediaCard from '/src/components/MediaCard.vue'
import Shelf from '/src/components/ui/Shelf.vue'
import ViewHeader from '/src/components/ui/ViewHeader.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'
import CoverImage from '/src/components/ui/CoverImage.vue'
import { useDeferred } from '/src/model/deferred'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const ex = useExplore()
const state = useSearchState()
const libraryIndex = useLibraryIndex()
const sm = useSearchManager()
const recent = useRecent()
const ui = useUi()
const scroller = inject('viewScroller', ref(null))

const loading = ref(false)
// A request is in flight, whether or not the page is empty. Drives the quiet
// inline indicator; `loading` drives the skeleton.
const searching = ref(false)
// Results now arrive fast enough that a skeleton would flash and vanish.
// This keeps it off screen entirely for a quick load, and steady for a slow one.
const showSkeleton = useDeferred(loading)
// Same idea for the inline indicator: a 200 ms search should not blink a
// spinner at anyone.
const showSearching = useDeferred(searching, { showAfter: 260, keepFor: 260 })
const error = ref('')

const tabs = [
  { id: 'all', label: 'explore.all' },
  { id: 'songs', label: 'explore.songs' },
  { id: 'artists', label: 'explore.artists' },
  { id: 'albums', label: 'explore.albums' },
  { id: 'playlists', label: 'explore.playlists' },
]

const data = computed(() => state.value.data)
const songRows = computed(() => data.value.songs.map(songRow))
const counts = computed(() => ({
  songs: data.value.songs.length,
  artists: data.value.artists.length,
  albums: data.value.albums.length,
  playlists: data.value.playlists.length,
}))
const hasAny = computed(
  () =>
    counts.value.songs || counts.value.artists || counts.value.albums || counts.value.playlists
)

function norm(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
}

// "Top result": the artist when the query names one, else the best song.
const topResult = computed(() => {
  const q = norm(state.value.query)
  const artist = data.value.artists[0]
  const song = data.value.songs[0]
  const album = data.value.albums[0]
  if (artist && (norm(artist.name) === q || (!song && !album))) {
    return { kind: 'artist', item: artist, label: t('explore.artist'), subtitle: '' }
  }
  if (song) {
    return {
      kind: 'song',
      item: song,
      label: t('search.song'),
      subtitle: (song.artists || []).join(', '),
    }
  }
  if (album) {
    return {
      kind: 'album',
      item: album,
      label: t('explore.album'),
      subtitle: (album.artists || []).join(', '),
    }
  }
  return artist ? { kind: 'artist', item: artist, label: t('explore.artist'), subtitle: '' } : null
})

function openTop() {
  const tr = topResult.value
  if (!tr) return
  if (tr.kind === 'artist') ex.openArtist(tr.item.browse_id)
  else if (tr.kind === 'album') ex.openAlbum(tr.item.browse_id)
  else playTop()
}

function playTop() {
  const tr = topResult.value
  if (!tr) return
  if (tr.kind === 'song') {
    const i = data.value.songs.indexOf(tr.item)
    playRows(songRows.value, Math.max(0, i))
  } else if (tr.kind === 'artist') {
    ex.openArtist(tr.item.browse_id)
  } else {
    ex.openAlbum(tr.item.browse_id)
  }
}

function onTopMenu(e) {
  const tr = topResult.value
  if (tr && tr.kind === 'song') openContextMenu(e, trackMenu([songRow(tr.item)]))
}

function kindFor(tab) {
  return tab === 'artists' ? 'artist' : tab === 'playlists' ? 'playlist' : 'album'
}
function openCard(tab, it) {
  if (tab === 'artists') ex.openArtist(it.browse_id)
  else if (tab === 'playlists') ex.openPlaylist(it.browse_id)
  else ex.openAlbum(it.browse_id)
}

function setTab(id) {
  state.value.activeTab = id
  if (scroller.value) scroller.value.scrollTop = 0
}

function openQuery(q) {
  sm.searchTerm.value = q
  recent.rememberSearch(q)
  router.push({ name: 'Search', params: { query: q } })
}

let loadToken = 0
let fetchedAt = 0
const SOFT_AGE_MS = 60_000

async function load(q, force = false) {
  const query = (q || '').trim()
  const sameAsShown = state.value.loaded && state.value.query === query
  if (!force && sameAsShown) {
    // Results are already on screen. Past a minute, refresh them in place so
    // coming back to a search does not show yesterday's answer forever.
    if (Date.now() - fetchedAt > SOFT_AGE_MS) load(query, true)
    return
  }
  const hadResults = hasAny.value
  state.value.query = query
  if (!query) {
    state.value.data = { songs: [], artists: [], albums: [], playlists: [] }
    state.value.loaded = true
    return
  }
  const token = ++loadToken
  // Search-as-you-type fires a request every few hundred milliseconds. If each
  // one blanked the page to a skeleton, typing a title would strobe between
  // grey boxes and results. So results stay put and only the quiet
  // "searching" line in the chips bar moves; the skeleton is for the case
  // where there is genuinely nothing on screen yet.
  const refreshing = sameAsShown && state.value.data.songs.length > 0
  // `loading` is what raises the skeleton, and the skeleton hides the results
  // underneath it. So it is only true when there is nothing to hide.
  loading.value = !refreshing && !hadResults
  searching.value = true
  error.value = ''
  // Resetting to the "All" tab mid-typing yanks the user out of the tab they
  // chose. Only do it when the results they were looking at are gone anyway.
  if (!refreshing && !hadResults) state.value.activeTab = 'all'
  try {
    const res = await API.exploreSearch(query)
    if (token !== loadToken) return // a newer keystroke won
    state.value.data = res.data
    state.value.loaded = true
    fetchedAt = Date.now()
    prefetchTopResult(res.data?.songs || [])
  } catch (e) {
    if (token !== loadToken) return
    if (!e.response) reportNetworkFailure() // no reply at all: the network
    error.value =
      (e.response && e.response.data && e.response.data.detail) || t('search.error')
  } finally {
    if (token === loadToken) {
      loading.value = false
      searching.value = false
    }
  }
}

// Warm the stream URLs of the first few results that are not already on
// disk. Resolving a YouTube stream is the slow half of pressing Play, and
// the user almost always picks from the top of the list, so by the time
// they click the URL is usually already cached server-side.
const PREFETCH_COUNT = 3
function prefetchTopResult(songs) {
  let warmed = 0
  for (const s of songs || []) {
    if (warmed >= PREFETCH_COUNT) return
    const id = s.video_id || s.song_id
    if (typeof id !== 'string' || !/^[A-Za-z0-9_-]{11}$/.test(id)) continue
    try {
      if (libraryIndex.localFileFor(s)) continue // already on disk, nothing to warm
    } catch {
      /* ignore */
    }
    API.prefetchStream(id).catch(() => {})
    warmed += 1
  }
}

function syncFromRoute() {
  const q = route.params.query
  if (q === undefined) return
  if ((sm.searchTerm.value || '').trim() !== q) sm.searchTerm.value = q
  load(q)
}

onMounted(syncFromRoute)
onActivated(syncFromRoute)
// Remember queries the user actually looked at.
onDeactivated(() => {
  if (state.value.query && hasAny.value) recent.rememberSearch(state.value.query)
})
watch(
  () => route.params.query,
  () => {
    if (route.name === 'Search') syncFromRoute()
  }
)
onRefresh(() => {
  if (state.value.query) load(state.value.query, true)
})
</script>

<style scoped>
.chips-busy {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  align-self: center;
  margin-left: 4px;
  font-size: 12px;
  color: rgb(var(--c-fg) / 0.5);
  white-space: nowrap;
}
.chips-busy-dot {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: rgb(var(--c-accent));
  animation: chips-busy-pulse 1s ease-in-out infinite;
}
@keyframes chips-busy-pulse {
  0%,
  100% {
    opacity: 0.25;
    transform: scale(0.8);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}
.chips-bar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  gap: 8px;
  padding-top: 14px;
  padding-bottom: 12px;
  background: rgb(var(--c-panel));
}
.section-title {
  margin-bottom: 10px;
  font-size: 21px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.show-all {
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.55);
}
.show-all:hover {
  color: rgb(var(--c-fg));
  text-decoration: underline;
}
.top-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
  gap: 24px;
  margin: 8px 0 32px;
}
@media (max-width: 900px) {
  .top-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
.top-card {
  position: relative;
  display: flex;
  flex-direction: column;
  height: calc(100% - 42px);
  min-height: 220px;
  padding: 20px;
  border-radius: 10px;
  background: rgb(var(--c-tint) / 0.06);
  outline: none;
  transition: background-color 0.15s ease;
}
.top-card:hover,
.top-card:focus-visible {
  background: rgb(var(--c-tint) / 0.1);
}
.top-cover {
  width: 96px;
  height: 96px;
  margin-bottom: 18px;
  box-shadow: 0 8px 24px rgb(0 0 0 / 0.35);
}
.top-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-display, theme('fontFamily.display'));
  font-size: 30px;
  font-weight: 800;
  letter-spacing: -0.02em;
}
.top-play {
  position: absolute;
  right: 20px;
  bottom: 20px;
  opacity: 0;
  transform: translateY(8px);
  transition:
    opacity 0.18s ease,
    transform 0.22s var(--ease-out);
}
.top-card:hover .top-play {
  opacity: 1;
  transform: none;
}
.shelves {
  padding: 0 14px;
}
@media (min-width: 1024px) {
  .shelves {
    padding: 0 22px;
  }
}
.recent-chip {
  display: inline-flex;
  align-items: center;
  height: 34px;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.07);
  overflow: hidden;
}
.recent-chip-main {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 100%;
  padding: 0 6px 0 14px;
  font-size: 13px;
  font-weight: 500;
}
.recent-chip-x {
  display: grid;
  place-items: center;
  width: 28px;
  height: 100%;
  padding-right: 4px;
  color: rgb(var(--c-fg) / 0.5);
}
.recent-chip:hover {
  background: rgb(var(--c-tint) / 0.11);
}
.recent-chip-x:hover {
  color: rgb(var(--c-fg));
}
</style>
