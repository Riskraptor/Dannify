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
    </div>

    <div v-overlay-scroll class="sb-scroll">
      <!-- Pinned: the collections that are always there. -->
      <template v-if="!filter || filter === 'playlists'">
        <router-link
          v-for="pin in pins"
          :key="pin.id"
          :to="pin.to"
          class="sb-row"
          :class="{ 'is-active': pin.active }"
          :title="rail ? pin.label : ''"
        >
          <span class="sb-tile" :class="pin.tile">
            <Icon :icon="pin.icon" class="h-[19px] w-[19px]" />
            <span v-if="rail && pin.badge" class="sb-tile-badge">{{ pin.badge }}</span>
          </span>
          <span v-if="!rail" class="sb-row-text">
            <span class="sb-row-title">{{ pin.label }}</span>
            <span class="sb-row-sub">
              <Icon v-if="pin.pinned" icon="ph:push-pin-fill" class="sb-pin" />
              {{ pin.sub }}
            </span>
          </span>
          <span v-if="!rail && pin.badge" class="badge sb-badge">{{ pin.badge }}</span>
        </router-link>
      </template>

      <!-- Playlists made here. Songs dragged out of any list can be dropped
           on one to add them. -->
      <template v-if="!filter || filter === 'playlists'">
        <router-link
          v-for="p in playlists.recent.value"
          :key="p.id"
          :to="{ name: 'Playlist', params: { id: p.id } }"
          class="sb-row"
          :class="{
            'is-active': route.name === 'Playlist' && route.params.id === p.id,
            'is-drop': dropOn === p.id,
          }"
          :title="rail ? p.name : ''"
          @contextmenu="onPlaylistMenu($event, p)"
          @dragenter="onDragOver($event, p)"
          @dragover="onDragOver($event, p)"
          @dragleave="onDragLeave($event, p)"
          @drop="onDrop($event, p)"
        >
          <PlaylistArt :covers="p.covers" :size="44" radius="sm" class="sb-art" />
          <span v-if="!rail" class="sb-row-text">
            <span class="sb-row-title">{{ p.name }}</span>
            <span class="sb-row-sub">
              {{ t('playlists.playlist') }} · {{ t('playlists.songsCount', { count: p.count }) }}
            </span>
          </span>
        </router-link>
        <button
          v-if="!rail && playlists.loaded.value && !playlists.list.value.length"
          class="sb-row sb-row-new"
          @click="playlists.createPlaylist()"
        >
          <span class="sb-tile is-new"><Icon icon="ph:plus" class="h-[18px] w-[18px]" /></span>
          <span class="sb-row-text">
            <span class="sb-row-title">{{ t('playlists.new') }}</span>
            <span class="sb-row-sub">{{ t('playlists.noneShort') }}</span>
          </span>
        </button>

        <!-- The signed-in account's own playlists on YouTube Music. -->
        <router-link
          v-for="p in ytPlaylists"
          :key="p.browse_id"
          :to="{ name: 'ExplorePlaylist', params: { id: p.browse_id } }"
          class="sb-row"
          :class="{ 'is-active': route.name === 'ExplorePlaylist' && route.params.id === p.browse_id }"
          :title="rail ? p.name : ''"
        >
          <CoverImage class="sb-art" :src="p.cover_url" kind="playlist" radius="sm" :size="44" />
          <span v-if="!rail" class="sb-row-text">
            <span class="sb-row-title">{{ p.name }}</span>
            <span class="sb-row-sub">
              <Icon icon="ph:youtube-logo-fill" class="sb-pin" />
              {{ t('explore.playlist') }}{{ p.author ? ` · ${p.author}` : '' }}
            </span>
          </span>
        </router-link>
      </template>

      <template v-if="!filter || filter === 'artists'">
        <router-link
          v-for="a in topArtists"
          :key="a.name"
          :to="{ name: 'Artist', params: { name: a.name } }"
          class="sb-row"
          :class="{ 'is-active': route.name === 'Artist' && route.params.name === a.name }"
          :title="rail ? a.name : ''"
          @contextmenu="onArtistMenu($event, a)"
        >
          <!-- CoverImage, not a bare <img>: a picture that failed is tried
               again when its file changes or the library is read again. -->
          <CoverImage
            class="sb-art is-round"
            :src="artistLinks.artistPhoto(a.name, 96)"
            :fallback="a.cover ? API.coverFileURL(a.cover, a.cover_v) : ''"
            kind="artist"
            round
          />
          <span v-if="!rail" class="sb-row-text">
            <span class="sb-row-title">{{ a.name }}</span>
            <span class="sb-row-sub">{{ t('explore.artist') }} · {{ t('nav.artistSongs', { count: a.count }) }}</span>
          </span>
        </router-link>
      </template>

      <div v-if="lib.loaded.value && !rail && !lib.tracks.value.length && !filter" class="sb-empty">
        <p class="text-[13px] font-semibold">{{ t('nav.emptyLibraryTitle') }}</p>
        <p class="mt-1 text-xs text-fg/55">{{ t('nav.emptyLibraryHint') }}</p>
        <button class="btn btn-pill mt-3 h-7 text-xs" @click="ui.focusSearch()">
          {{ t('nav.browse') }}
        </button>
      </div>
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
import { computed, h, ref, watch } from 'vue'
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

const topArtists = computed(() =>
  [...lib.artists.value]
    .filter((a) => a && a.name)
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
    .slice(0, 40)
)

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
      active: route.name === 'Library',
    },
    account.signedIn.value && {
      id: 'liked',
      to: { name: 'Liked' },
      label: t('account.likedSongs'),
      sub: `${t('playlists.playlist')} · ${t('nav.artistSongs', { count: account.liked.value.length })}`,
      icon: 'ph:heart-fill',
      tile: 'tile-liked',
      pinned: true,
      active: route.name === 'Liked',
    },
    {
      id: 'artists',
      to: { name: 'Artists' },
      label: t('nav.artists'),
      sub: t('nav.artistCount', { count: lib.artists.value.length }),
      icon: 'ph:users-three-fill',
      tile: 'tile-artists',
      pinned: true,
      active: route.name === 'Artists',
    },
    {
      id: 'downloads',
      to: { name: 'Downloads' },
      label: t('nav.downloads'),
      sub: dl.value.active ? t('nav.downloadingNow', { count: dl.value.active }) : t('nav.downloadsSub'),
      icon: 'ph:download-simple-bold',
      tile: 'tile-downloads',
      badge: dl.value.active || null,
      active: route.name === 'Downloads',
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
