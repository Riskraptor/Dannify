<template>
  <nav
    class="sidebar"
    :class="{ 'is-rail': rail, 'is-drawer': ui.isCompact.value }"
    :aria-label="t('nav.navigation')"
  >
    <div class="sb-group">
      <SideLink :to="{ name: 'Home' }" icon="ph:house" active-icon="ph:house-fill" :label="t('nav.home')" :rail="rail" :active="route.name === 'Home'" />
      <SideLink
        :to="{ name: 'Search' }"
        icon="ph:magnifying-glass"
        active-icon="ph:magnifying-glass-bold"
        :label="t('nav.search')"
        :rail="rail"
        :active="route.name === 'Search'"
        @click="ui.focusSearch()"
      />
    </div>

    <!-- Your Library, the way a music app has it: one list of what is yours
         (your songs, liked songs, playlists, artists) with chips to narrow
         it, rather than three headed lists and a column of links. -->
    <div class="sb-lib">
      <div class="sb-lib-head" :class="{ 'is-rail': rail }">
        <button
          class="sb-lib-title"
          :title="(rail ? t('nav.expandSidebar') : t('nav.collapseSidebar')) + ' (Ctrl+B)'"
          :disabled="ui.forceRail.value || ui.isCompact.value"
          @click="ui.toggleSidebar()"
        >
          <Icon :icon="rail ? 'ph:books-fill' : 'ph:books'" class="h-5 w-5 shrink-0" />
          <span v-if="!rail">{{ t('nav.yourLibrary') }}</span>
        </button>
        <button
          v-if="!rail"
          class="sb-plus"
          :title="t('playlists.new')"
          @click="playlists.createPlaylist()"
        >
          <Icon icon="ph:plus" class="h-4 w-4" />
        </button>
      </div>
      <div v-if="!rail" class="sb-chips" role="tablist" :aria-label="t('nav.yourLibrary')">
        <button
          v-if="filter"
          class="sb-chip sb-chip-clear"
          :title="t('nav.showEverything')"
          @click="setFilter('')"
        >
          <Icon icon="ph:x" class="h-3.5 w-3.5" />
        </button>
        <button
          v-for="f in filters"
          v-show="!filter || filter === f.id"
          :key="f.id"
          class="sb-chip"
          role="tab"
          :aria-selected="filter === f.id"
          :class="{ 'is-on': filter === f.id }"
          @click="setFilter(filter === f.id ? '' : f.id)"
        >
          {{ t(f.label) }}
        </button>
      </div>
      <div v-if="!rail" class="sb-tools">
        <div class="sb-find" :class="{ 'is-open': searching || query }">
          <button class="sb-tool" :title="t('nav.searchLibrary')" @click="openFind">
            <Icon icon="ph:magnifying-glass" class="h-4 w-4" />
          </button>
          <input
            v-if="searching || query"
            ref="findInput"
            v-model="query"
            class="sb-find-input"
            :placeholder="t('nav.searchLibrary')"
            spellcheck="false"
            @keydown.esc.stop="closeFind"
            @blur="!query && (searching = false)"
          />
        </div>
        <button class="sb-sort" :title="t('nav.sortBy')" @click="onSortMenu">
          {{ t(sort === 'alpha' ? 'nav.sortAlpha' : 'nav.sortRecent') }}
          <Icon icon="ph:list" class="h-4 w-4" />
        </button>
      </div>
    </div>

    <!-- One list, drawn a screen at a time: a library of thousands of
         artists or playlists costs no more than one of ten. -->
    <VirtualList
      class="sb-list"
      :items="rows"
      :item-height="rail ? 52 : 56"
      :item-key="(r) => r.key"
    >
      <template #default="{ item: r }">
        <button
          v-if="r.kind === 'new' || r.kind === 'more'"
          class="sb-row"
          :title="rail ? r.title : ''"
          @click="r.kind === 'new' ? playlists.createPlaylist() : router.push({ name: 'Artists' })"
        >
          <span class="sb-tile is-new">
            <Icon :icon="r.kind === 'new' ? 'ph:plus' : 'ph:arrow-right'" class="h-[18px] w-[18px]" />
          </span>
          <span v-if="!rail" class="sb-row-text">
            <span class="sb-row-title">{{ r.title }}</span>
            <span class="sb-row-sub">{{ r.sub }}</span>
          </span>
        </button>
        <router-link
          v-else
          :to="r.to"
          class="sb-row"
          :class="{ 'is-active': isActive(r), 'is-drop': r.kind === 'playlist' && dropOn === r.id }"
          :title="rail ? r.title : ''"
          @contextmenu="r.menu && r.menu($event)"
          @dragenter="r.kind === 'playlist' && onDragOver($event, r.playlist)"
          @dragover="r.kind === 'playlist' && onDragOver($event, r.playlist)"
          @dragleave="r.kind === 'playlist' && onDragLeave($event, r.playlist)"
          @drop="r.kind === 'playlist' && onDrop($event, r.playlist)"
        >
          <span v-if="r.kind === 'pin'" class="sb-tile" :class="r.tile">
            <Icon :icon="r.icon" class="h-[19px] w-[19px]" />
          </span>
          <PlaylistArt v-else-if="r.kind === 'playlist'" :covers="r.covers" :size="44" radius="sm" class="sb-art" />
          <CoverImage
            v-else
            class="sb-art"
            :class="{ 'is-round': r.round }"
            :src="r.cover"
            :fallback="r.fallback || ''"
            :kind="r.round ? 'artist' : 'playlist'"
            :round="r.round"
            radius="sm"
            :size="44"
          />
          <span v-if="!rail" class="sb-row-text">
            <span class="sb-row-title">{{ r.title }}</span>
            <span class="sb-row-sub">
              <Icon v-if="r.badge" :icon="r.badge" class="sb-pin" />
              {{ r.sub }}
            </span>
          </span>
        </router-link>
      </template>
    </VirtualList>
    <p v-if="!rail && query && !rows.length" class="sb-none">{{ t('nav.libraryNoMatch', { query }) }}</p>
    <div v-if="lib.loaded.value && !rail && !lib.tracks.value.length && !filter && !query" class="sb-empty">
      <p class="text-[13px] font-semibold">{{ t('nav.emptyLibraryTitle') }}</p>
      <p class="mt-1 text-xs text-fg/55">{{ t('nav.emptyLibraryHint') }}</p>
      <button class="btn btn-pill mt-3 h-7 text-xs" @click="ui.focusSearch()">
        {{ t('nav.browse') }}
      </button>
    </div>

    <div class="sb-group sb-foot">
      <div class="sb-foot-row" :class="{ 'is-rail': rail }">
        <SideLink :to="{ name: 'Settings' }" icon="ph:gear-six" active-icon="ph:gear-six-fill" :label="t('nav.settings')" :rail="rail" :active="route.name === 'Settings'" />
        <!-- Supporting the app: always here, never in the way. -->
        <button
          v-if="support.config.configured"
          class="sb-give"
          :title="t('support.sidebar')"
          @click="support.openSupport()"
        >
          <Icon icon="ph:coffee" class="h-[18px] w-[18px]" />
        </button>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { computed, h, ref, watch, nextTick } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { useUi } from '/src/model/ui'
import { useLibrary } from '/src/model/library'
import { useAccount } from '/src/model/account'
import { useDownloadStats } from '/src/model/downloadStats'
import { openContextMenu } from '/src/model/contextMenu'
import { playRows, shuffleRows, localRow, onArtistPage } from '/src/model/tracks'
import { useI18n } from '/src/i18n'
import CoverImage from '/src/components/ui/CoverImage.vue'
import PlaylistArt from '/src/components/ui/PlaylistArt.vue'
import { sortedBy, insertSorted } from '/src/model/textSort'
import VirtualList from '/src/components/ui/VirtualList.vue'
import { useArtistLinks } from '/src/model/artistLinks'
import { usePlaylists, entryRow } from '/src/model/playlists'
import { useSupport } from '/src/model/support'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const ui = useUi()
const lib = useLibrary()
const account = useAccount()
const dlStats = useDownloadStats()
const dl = computed(() => dlStats.value)

lib.ensureLoaded()
// The artists' own pictures, once found (album covers until then).
const artistLinks = useArtistLinks()

const rail = computed(() => ui.sidebarCollapsed.value && !ui.isCompact.value)

// ----- the list -----------------------------------------------------------------
// With nothing narrowed: your collections, your playlists, the artists you
// follow and your most-saved few, and a way to all of them. With the Artists
// chip, or a search: every one, however many there are.
const TOP_ARTISTS = 8
const SORT_KEY = 'dn.libSort'
const sort = ref((() => {
  try {
    return localStorage.getItem(SORT_KEY) === 'alpha' ? 'alpha' : 'recent'
  } catch {
    return 'recent'
  }
})())
function setSort(v) {
  sort.value = v
  try {
    localStorage.setItem(SORT_KEY, v)
  } catch {
    // this session only
  }
}
function onSortMenu(e) {
  openContextMenu(
    e,
    [
      { header: t('nav.sortBy') },
      { label: t('nav.sortRecent'), checked: sort.value === 'recent', action: () => setSort('recent') },
      { label: t('nav.sortAlpha'), checked: sort.value === 'alpha', action: () => setSort('alpha') },
    ],
    { anchor: true }
  )
}

const query = ref('')
const searching = ref(false)
const findInput = ref(null)
async function openFind() {
  searching.value = true
  await nextTick()
  findInput.value && findInput.value.focus()
}
function closeFind() {
  query.value = ''
  searching.value = false
}

const savedArtists = computed(() => lib.artists.value.filter((a) => a && a.name))
// Kept in order until the library itself changes: typing in the find box or
// switching the sort only filters what is already sorted.
const artistsByCount = computed(() =>
  sortedBy(savedArtists.value, { by: (a) => a.count || 0, desc: true }, (a) => a.name)
)
const artistsByName = computed(() => sortedBy(savedArtists.value, (a) => a.name))
const topArtists = computed(() => artistsByCount.value.slice(0, TOP_ARTISTS))

// One of your artists as a row. What it shows under the name and its picture
// are read when the row is drawn, which is a few dozen rows, not for every
// artist in the library each time the list is built.
function artistRow(a) {
  return {
    key: 'ar:' + a.name,
    kind: 'artist',
    name: a.name,
    count: a.count,
    to: { name: 'Artist', params: { name: a.name } },
    title: a.name,
    round: true,
    get sub() {
      return `${t('explore.artist')} · ${t('nav.artistSongs', { count: a.count })}`
    },
    get cover() {
      return artistLinks.artistPhoto(a.name, 96)
    },
    get fallback() {
      return a.cover ? API.coverFileURL(a.cover, a.cover_v) : ''
    },
    menu: (e) => onArtistMenu(e, a),
  }
}

// The row for the page on screen, worked out for the rows drawn only: the
// list itself does not depend on the page, so going from page to page does
// not build (and sort) every row of a big library again.
function isActive(r) {
  const to = r.to
  if (!to || route.name !== to.name) return false
  const want = to.params || {}
  return Object.keys(want).every((k) => route.params[k] === want[k])
}

const rows = computed(() => {
  const q = query.value.trim().toLowerCase()
  const match = (text) => !q || String(text || '').toLowerCase().includes(q)
  const f = filter.value
  // Joined with concat: `push(...list)` passes every row as an argument and
  // runs out of stack with a library of a couple of hundred thousand.
  let out = []

  if (f !== 'artists') {
    for (const pin of pins.value) {
      if (f === 'playlists' && pin.id === 'artists') continue
      if (!match(pin.label)) continue
      out.push({ key: 'pin:' + pin.id, kind: 'pin', to: pin.to, title: pin.label, sub: pin.sub,
        icon: pin.icon, tile: pin.tile, badge: pin.pinned ? 'ph:push-pin-fill' : '' })
    }
    let mine = playlists.recent.value
      .filter((p) => match(p.name))
      .map((p) => ({
        key: 'pl:' + p.id,
        kind: 'playlist',
        id: p.id,
        playlist: p,
        to: { name: 'Playlist', params: { id: p.id } },
        title: p.name,
        sub: `${t('playlists.playlist')} · ${t('playlists.songsCount', { count: p.count })}`,
        covers: p.covers,
        menu: (e) => onPlaylistMenu(e, p),
      }))
    let yt = ytPlaylists.value
      .filter((p) => match(p.name))
      .map((p) => ({
        key: 'yt:' + p.browse_id,
        kind: 'yt',
        to: { name: 'ExplorePlaylist', params: { id: p.browse_id } },
        title: p.name,
        sub: t('explore.playlist') + (p.author ? ` · ${p.author}` : ''),
        cover: p.cover_url,
        badge: 'ph:youtube-logo-fill',
      }))
    if (sort.value === 'alpha') {
      mine = sortedBy(mine, (r) => r.title)
      yt = sortedBy(yt, (r) => r.title)
    }
    out = out.concat(mine, yt)
    if (!q && playlists.loaded.value && !playlists.list.value.length) {
      out.push({ key: 'new', kind: 'new', title: t('playlists.new'), sub: t('playlists.noneShort') })
    }
  }

  if (f !== 'playlists') {
    const everyone = f === 'artists' || q
    const followed = followedArtists.value
      .filter((a) => match(a.name))
      .map((a) => ({
        key: 'fa:' + a.browse_id,
        kind: 'followed',
        to: { name: 'ExploreArtist', params: { id: a.browse_id } },
        title: a.name,
        sub: `${t('explore.artist')} · ${t('account.followingArtist')}`,
        cover: a.cover_url,
        round: true,
        badge: 'ph:youtube-logo-fill',
        menu: (e) => onFollowedMenu(e, a),
      }))
    const alpha = sort.value === 'alpha'
    const source = everyone ? (alpha ? artistsByName.value : artistsByCount.value) : topArtists.value
    const saved = (q ? source.filter((a) => match(a.name)) : source).map(artistRow)
    // Your artists are already in order; the few you follow on YouTube are
    // put in their places among them.
    let artists
    if (!everyone) artists = alpha ? sortedBy([...followed, ...saved], (r) => r.title) : [...followed, ...saved]
    else if (alpha) artists = insertSorted(saved, followed, (r) => r.title)
    else artists = insertSorted(saved, followed, { by: (r) => r.count || 0, desc: true }, (r) => r.title)
    out = out.concat(artists)
    if (!everyone && savedArtists.value.length > TOP_ARTISTS) {
      out.push({
        key: 'more',
        kind: 'more',
        title: t('nav.allArtists', { count: savedArtists.value.length }),
        sub: t('nav.allArtistsHint'),
      })
    }
  }
  return out
})

function artistRows(name) {
  return lib.tracks.value
    .filter((tr) => onArtistPage(tr, name))
    .map(localRow)
}

function onArtistMenu(e, a) {
  openContextMenu(e, [
    { label: t('actions.play'), icon: 'ph:play', action: () => playRows(artistRows(a.name), 0) },
    { label: t('actions.shuffle'), icon: 'ph:shuffle', action: () => shuffleRows(artistRows(a.name)) },
    { divider: true },
    {
      label: t('actions.openArtist'),
      icon: 'ph:user',
      action: () => router.push({ name: 'Artist', params: { name: a.name } }),
    },
  ])
}

const support = useSupport()

// ----- your library ----------------------------------------------------------
const FILTER_KEY = 'dn.libFilter'
const filters = [
  { id: 'playlists', label: 'nav.filterPlaylists' },
  { id: 'artists', label: 'nav.filterArtists' },
]
function readFilter() {
  try {
    const v = localStorage.getItem(FILTER_KEY) || ''
    return filters.some((f) => f.id === v) ? v : ''
  } catch {
    return ''
  }
}
const filter = ref(readFilter())
function setFilter(v) {
  filter.value = v
  try {
    if (v) localStorage.setItem(FILTER_KEY, v)
    else localStorage.removeItem(FILTER_KEY)
  } catch {
    // remembered for this run only
  }
}

// Artists followed on YouTube Music that are not already here as saved ones.
const followedArtists = computed(() => {
  if (!account.signedIn.value) return []
  const saved = new Set(lib.artists.value.map((a) => String(a.name || '').toLowerCase()))
  return (account.following.value || []).filter(
    (a) => a && a.browse_id && !saved.has(String(a.name || '').toLowerCase())
  )
})

// What is always at the top: the collections the app keeps for you.
const pins = computed(() => {
  const n = lib.tracks.value.length
  return [
    {
      id: 'songs',
      to: { name: 'Library' },
      label: t('nav.yourSongs'),
      sub: t('nav.artistSongs', { count: n }),
      icon: 'ph:music-notes-fill',
      tile: 'tile-songs',
      pinned: true,
    },
    account.signedIn.value && {
      id: 'liked',
      to: { name: 'Liked' },
      label: t('account.likedSongs'),
      sub: `${t('playlists.playlist')} · ${t('nav.artistSongs', { count: account.liked.value.length })}`,
      icon: 'ph:heart-fill',
      tile: 'tile-liked',
      pinned: true,
    },
    {
      id: 'artists',
      to: { name: 'Artists' },
      label: t('nav.artists'),
      sub: t('nav.artistCount', { count: lib.artists.value.length }),
      icon: 'ph:users-three-fill',
      tile: 'tile-artists',
      pinned: true,
    },
  ].filter(Boolean)
})

// What the account has on YouTube Music, minus the two it fills itself
// (Liked Music is Liked Songs here; Episodes for Later is podcasts).
const ytPlaylists = computed(() =>
  (account.playlists.value || []).filter(
    (p) => p && p.browse_id && !['LM', 'SE', 'VLLM', 'VLSE'].includes(p.browse_id)
  )
)
watch(
  () => account.signedIn.value,
  (on) => {
    if (!on) return
    if (!(account.playlists.value || []).length) account.loadPlaylists()
    // For the count under Liked Songs.
    account.loadLiked()
  },
  { immediate: true }
)

// ----- playlists -------------------------------------------------------------
const playlists = usePlaylists()
playlists.ensureLoaded()

async function playlistRows(p) {
  try {
    const res = await API.getPlaylist(p.id)
    return (res.data.tracks || []).map(entryRow)
  } catch {
    return []
  }
}

function onPlaylistMenu(e, p) {
  openContextMenu(e, [
    { label: t('actions.play'), icon: 'ph:play', action: async () => playRows(await playlistRows(p), 0) },
    { label: t('actions.shuffle'), icon: 'ph:shuffle', action: async () => shuffleRows(await playlistRows(p)) },
    { divider: true },
    { label: t('playlists.rename'), icon: 'ph:pencil-simple', action: () => playlists.renamePlaylist(p.id) },
    { label: t('playlists.delete'), icon: 'ph:trash', danger: true, action: () => playlists.deletePlaylist(p.id) },
  ])
}

function onFollowedMenu(e, a) {
  openContextMenu(e, [
    {
      label: t('actions.openArtist'),
      icon: 'ph:user',
      action: () => router.push({ name: 'ExploreArtist', params: { id: a.browse_id } }),
    },
    { divider: true },
    {
      label: t('account.unfollowHint'),
      icon: 'ph:user-minus',
      action: () => account.toggleFollow({ browse_id: a.browse_id, name: a.name }),
    },
  ])
}

// Songs dragged from a list onto a playlist here are added to it.
const dropOn = ref(null)
function onDragOver(e, p) {
  if (!playlists.dragging.value) return
  e.preventDefault()
  e.dataTransfer.dropEffect = 'copy'
  dropOn.value = p.id
}
function onDragLeave(e, p) {
  // Leaving for one of its own children is not leaving.
  if (e.currentTarget.contains(e.relatedTarget)) return
  if (dropOn.value === p.id) dropOn.value = null
}
function onDrop(e, p) {
  const rows = playlists.dragging.value
  dropOn.value = null
  if (!rows || !rows.length) return
  e.preventDefault()
  playlists.addRows(p.id, rows)
}

// Compact nav item (icon + label, tooltip-only in rail mode).
const SideLink = {
  props: {
    to: Object,
    icon: String,
    activeIcon: String,
    label: String,
    rail: Boolean,
    active: Boolean,
    count: [Number, null],
    badge: [Number, null],
  },
  emits: ['click'],
  setup(props, { emit }) {
    return () =>
      h(
        RouterLink,
        {
          to: props.to,
          class: ['sb-link', { 'is-active': props.active }],
          title: props.rail ? props.label : undefined,
          'aria-current': props.active ? 'page' : undefined,
          onClick: () => emit('click'),
        },
        () => [
          h(Icon, {
            icon: props.active && props.activeIcon ? props.activeIcon : props.icon,
            class: 'sb-icon',
          }),
          props.rail ? null : h('span', { class: 'sb-label' }, props.label),
          !props.rail && props.count
            ? h('span', { class: 'sb-count' }, String(props.count))
            : null,
          props.badge
            ? h('span', { class: ['badge', props.rail ? 'sb-badge-rail' : 'sb-badge'] }, String(props.badge))
            : null,
        ]
      )
  },
}
</script>

<style scoped>

.sb-list {
  flex: 1;
  min-height: 0;
  margin: 2px -4px 0;
  padding: 0 4px;
}
.sb-list :deep(.sb-row) {
  height: 100%;
  min-height: 0;
}
.sb-tools {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 4px;
}
.sb-find {
  display: flex;
  align-items: center;
  min-width: 0;
  flex: 1;
  height: 32px;
  border-radius: 6px;
  transition: background-color 0.15s ease;
}
.sb-find.is-open {
  background: rgb(var(--c-tint) / 0.08);
}
.sb-tool {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: 999px;
  color: rgb(var(--c-fg) / 0.65);
}
.sb-tool:hover {
  color: rgb(var(--c-fg));
  background: rgb(var(--c-tint) / 0.08);
}
.sb-find-input {
  min-width: 0;
  flex: 1;
  height: 100%;
  padding-right: 8px;
  background: transparent;
  border: 0;
  outline: none;
  font-size: 13px;
  color: rgb(var(--c-fg));
}
.sb-sort {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  font-size: 12.5px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.65);
}
.sb-sort:hover {
  color: rgb(var(--c-fg));
}
.sb-none {
  padding: 8px 12px;
  font-size: 12.5px;
  color: rgb(var(--c-fg) / 0.5);
}
/* --- Your Library ---------------------------------------------------------- */
.sb-lib {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 4px 6px;
  border-top: 1px solid rgb(var(--c-tint) / 0.07);
  margin-top: 6px;
}
.sb-lib-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.sb-lib-head.is-rail {
  justify-content: center;
}
.sb-lib-title {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 36px;
  padding: 0 8px;
  border-radius: 6px;
  font-size: 15px;
  font-weight: 700;
  color: rgb(var(--c-fg) / 0.72);
  transition: color 0.12s ease;
}
.sb-lib-title:hover:not(:disabled) {
  color: rgb(var(--c-fg));
}
.sb-lib-title:disabled {
  cursor: default;
}
.sb-plus {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 999px;
  color: rgb(var(--c-fg) / 0.7);
  transition:
    background-color 0.12s ease,
    color 0.12s ease,
    transform 0.12s ease;
}
.sb-plus:hover {
  color: rgb(var(--c-fg));
  background: rgb(var(--c-tint) / 0.1);
  transform: scale(1.04);
}
.sb-chips {
  display: flex;
  gap: 8px;
  padding: 0 4px;
}
.sb-chip {
  height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  background: rgb(var(--c-tint) / 0.07);
  color: rgb(var(--c-fg) / 0.9);
  transition: background-color 0.12s ease;
}
.sb-chip:hover {
  background: rgb(var(--c-tint) / 0.12);
}
.sb-chip.is-on {
  background: rgb(var(--c-fg));
  color: rgb(var(--c-panel));
}
.sb-chip-clear {
  display: grid;
  place-items: center;
  width: 30px;
  padding: 0;
}
.sb-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 56px;
  padding: 6px 8px;
  border-radius: 6px;
  text-align: left;
  transition: background-color 0.1s ease;
}
.sb-row:hover {
  background: rgb(var(--c-tint) / 0.06);
}
.sb-row.is-active {
  background: rgb(var(--c-tint) / 0.1);
}
.sb-row.is-active .sb-row-title {
  color: rgb(var(--c-accent));
}
.sb-row.is-drop {
  background: rgb(var(--c-accent) / 0.18);
  box-shadow: inset 0 0 0 1px rgb(var(--c-accent));
}
.sb-art,
.sb-tile {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  border-radius: 4px;
}
.sb-art.is-round {
  border-radius: 999px;
  overflow: hidden;
}
.sb-tile {
  position: relative;
  display: grid;
  place-items: center;
  color: #fff;
}
/* The pinned collections, each with a colour of its own. */
.sb-tile.is-new {
  background: rgb(var(--c-tint) / 0.08);
  color: rgb(var(--c-fg) / 0.75);
}
.sb-tile-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 999px;
  font-size: 9.5px;
  font-weight: 700;
  line-height: 16px;
  text-align: center;
  background: rgb(var(--c-accent));
  color: #000;
}
.sb-row-text {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}
.sb-row-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14.5px;
  font-weight: 500;
  color: rgb(var(--c-fg));
}
.sb-row-sub {
  display: flex;
  align-items: center;
  gap: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12.5px;
  color: rgb(var(--c-fg) / 0.55);
}
.sb-pin {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  color: rgb(var(--c-accent));
}
.sb-badge {
  flex-shrink: 0;
}
.sidebar.is-rail .sb-row {
  justify-content: center;
  padding: 6px 0;
}
.sidebar.is-rail .sb-lib {
  padding-left: 0;
  padding-right: 0;
}
.sidebar {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 8px;
  gap: 2px;
  border-radius: var(--radius-panel);
  background: rgb(var(--c-panel));
  overflow: hidden;
}
.sb-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.sb-divider {
  height: 1px;
  margin: 6px 8px;
  background: rgb(var(--c-tint) / 0.07);
}
.sb-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 32px;
  padding: 0 4px 0 12px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / 0.5);
}
.sb-subheading {
  padding: 12px 12px 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / 0.5);
}
.sidebar :deep(.sb-link) {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  height: 38px;
  padding: 0 12px;
  border-radius: 6px;
  font-size: 13.5px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.68);
  transition:
    background-color 0.1s ease,
    color 0.1s ease;
}
.sidebar :deep(.sb-link:hover) {
  color: rgb(var(--c-fg));
  background: rgb(var(--c-tint) / 0.05);
}
.sidebar :deep(.sb-link.is-active) {
  color: rgb(var(--c-fg));
  background: rgb(var(--c-tint) / 0.08);
}
.sidebar :deep(.sb-link.is-active::before) {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  width: 3px;
  height: 16px;
  border-radius: 3px;
  background: rgb(var(--c-accent));
  transform: translateY(-50%);
}
.sidebar :deep(.sb-icon) {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}
.sidebar :deep(.sb-link.is-active .sb-icon) {
  color: rgb(var(--c-accent));
}
.sidebar :deep(.sb-label) {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sidebar :deep(.sb-count) {
  font-size: 11px;
  font-weight: 500;
  color: rgb(var(--c-fg) / 0.4);
  font-variant-numeric: tabular-nums;
}
.sidebar :deep(.sb-badge-rail) {
  position: absolute;
  top: 3px;
  right: 6px;
  height: 15px;
  min-width: 15px;
  font-size: 9px;
}
.sb-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  margin: 4px -4px 0;
  padding: 0 4px;
}
.sb-artist {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 48px;
  padding: 0 8px;
  border-radius: 6px;
}
.sb-artist:hover {
  background: rgb(var(--c-tint) / 0.05);
}
.sb-artist.is-active {
  background: rgb(var(--c-tint) / 0.08);
}
.sb-avatar {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.08);
}
.sb-subrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 4px;
}
.sb-artist.is-drop {
  background: rgb(var(--c-accent) / 0.18);
  box-shadow: inset 0 0 0 1px rgb(var(--c-accent));
}
.sb-plart {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
}
.sb-new {
  width: 100%;
}
.sb-new-mark {
  color: rgb(var(--c-fg) / 0.7);
}
.sb-note {
  margin: 0 12px 4px;
  font-size: 11.5px;
  line-height: 1.45;
  color: rgb(var(--c-fg) / 0.45);
}
.sb-empty {
  margin: 12px 4px;
  padding: 14px;
  border-radius: 8px;
  background: rgb(var(--c-tint) / 0.05);
}
.sb-foot-row {
  display: flex;
  align-items: center;
  gap: 2px;
}
.sb-foot-row > :first-child {
  flex: 1;
  min-width: 0;
}
.sb-foot-row.is-rail {
  flex-direction: column;
  align-items: stretch;
}
.sb-give {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  border-radius: 6px;
  color: rgb(var(--c-fg) / 0.5);
  transition:
    color 0.12s ease,
    background-color 0.12s ease;
}
.sb-give:hover {
  color: rgb(var(--c-accent));
  background: rgb(var(--c-accent) / 0.1);
}
.sb-foot-row.is-rail .sb-give {
  width: auto;
  height: 40px;
}
.sb-foot {
  padding-top: 6px;
  border-top: 1px solid rgb(var(--c-tint) / 0.07);
}

/* Icon rail */
.sidebar.is-rail {
  align-items: stretch;
  padding: 8px 6px;
}
.sidebar.is-rail :deep(.sb-link) {
  justify-content: center;
  padding: 0;
  height: 44px;
}
.sidebar.is-rail .sb-artist {
  justify-content: center;
  padding: 0;
}
.sidebar.is-rail .sb-heading {
  display: none;
}
</style>
