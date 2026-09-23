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

    <div class="sb-divider" />

    <div class="sb-group">
      <div v-if="!rail" class="sb-heading">
        <span>{{ t('nav.yourLibrary') }}</span>
        <button
          v-if="!ui.forceRail.value && !ui.isCompact.value"
          class="icon-btn h-7 w-7"
          :title="t('nav.collapseSidebar') + ' (Ctrl+B)'"
          @click="ui.toggleSidebar()"
        >
          <Icon icon="ph:sidebar-simple" class="h-4 w-4" />
        </button>
      </div>
      <SideLink :to="{ name: 'Library' }" icon="ph:music-notes" active-icon="ph:music-notes-fill" :label="t('nav.songs')" :rail="rail" :active="route.name === 'Library'" :count="lib.tracks.value.length || null" />
      <SideLink :to="{ name: 'Artists' }" icon="ph:users-three" active-icon="ph:users-three-fill" :label="t('nav.artists')" :rail="rail" :active="route.name === 'Artists' || route.name === 'Artist'" />
      <SideLink v-if="account.signedIn.value" :to="{ name: 'Liked' }" icon="ph:heart" active-icon="ph:heart-fill" :label="t('account.likedSongs')" :rail="rail" :active="route.name === 'Liked'" :count="account.liked.value.length || null" />
      <SideLink :to="{ name: 'Downloads' }" icon="ph:download-simple" active-icon="ph:download-simple-bold" :label="t('nav.downloads')" :rail="rail" :active="route.name === 'Downloads'" :badge="dl.active || null" />
    </div>

    <!-- Your artists: a quick-access list, like a streaming app's library -->
    <div class="sb-scroll">
      <template v-if="topArtists.length">
        <p v-if="!rail" class="sb-subheading">{{ t('nav.yourArtists') }}</p>
        <router-link
          v-for="a in topArtists"
          :key="a.name"
          :to="{ name: 'Artist', params: { name: a.name } }"
          class="sb-artist"
          :class="{ 'is-active': route.name === 'Artist' && route.params.name === a.name }"
          :title="rail ? a.name : ''"
          @contextmenu="onArtistMenu($event, a)"
        >
          <span class="sb-avatar">
            <img
              v-if="a.cover && !failed[a.name]"
              :src="API.coverFileURL(a.cover)"
              alt=""
              loading="lazy"
              class="drag-none"
              @error="failed[a.name] = true"
            />
            <Icon v-else icon="ph:user" class="h-4 w-4 text-fg/40" />
          </span>
          <span v-if="!rail" class="min-w-0 flex-1">
            <span class="block truncate text-[13px] font-medium">{{ a.name }}</span>
            <span class="block truncate text-[11px] text-fg/50">
              {{ t('nav.artistSongs', { count: a.count }) }}
            </span>
          </span>
        </router-link>
      </template>
      <div v-else-if="lib.loaded.value && !rail" class="sb-empty">
        <p class="text-[13px] font-semibold">{{ t('nav.emptyLibraryTitle') }}</p>
        <p class="mt-1 text-xs text-fg/55">{{ t('nav.emptyLibraryHint') }}</p>
        <button class="btn btn-pill mt-3 h-7 text-xs" @click="ui.focusSearch()">
          {{ t('nav.browse') }}
        </button>
      </div>
    </div>

    <div class="sb-group sb-foot">
      <button
        v-if="rail && !ui.forceRail.value && !ui.isCompact.value"
        class="sb-link"
        :title="t('nav.expandSidebar') + ' (Ctrl+B)'"
        @click="ui.toggleSidebar()"
      >
        <Icon icon="ph:sidebar-simple" class="sb-icon" />
      </button>
      <SideLink :to="{ name: 'Settings' }" icon="ph:gear-six" active-icon="ph:gear-six-fill" :label="t('nav.settings')" :rail="rail" :active="route.name === 'Settings'" />
    </div>
  </nav>
</template>

<script setup>
import { computed, reactive, h } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { useUi } from '/src/model/ui'
import { useLibrary } from '/src/model/library'
import { useAccount } from '/src/model/account'
import { useDownloadStats } from '/src/model/downloadStats'
import { openContextMenu } from '/src/model/contextMenu'
import { playRows, shuffleRows, localRow } from '/src/model/tracks'
import { useI18n } from '/src/i18n'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const ui = useUi()
const lib = useLibrary()
const account = useAccount()
const dlStats = useDownloadStats()
const dl = computed(() => dlStats.value)
const failed = reactive({})

lib.ensureLoaded()

const rail = computed(() => ui.sidebarCollapsed.value && !ui.isCompact.value)

const topArtists = computed(() =>
  [...lib.artists.value]
    .filter((a) => a && a.name)
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
    .slice(0, 40)
)

function artistRows(name) {
  return lib.tracks.value
    .filter((tr) => tr.artist === name || (tr.artists || []).includes(name))
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
.sb-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.sb-empty {
  margin: 12px 4px;
  padding: 14px;
  border-radius: 8px;
  background: rgb(var(--c-tint) / 0.05);
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
