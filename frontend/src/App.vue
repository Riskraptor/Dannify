<template>
  <MiniMode v-if="win.mini" />
  <div
    v-else
    class="shell"
    :class="{
      'is-rail': ui.sidebarCollapsed.value,
      'is-compact': ui.isCompact.value,
      'is-maximized': win.maximized || win.fullscreen,
    }"
  >
    <TitleBar class="shell-title" />

    <transition name="scrim">
      <div
        v-if="ui.isCompact.value && ui.drawerOpen.value"
        class="shell-scrim"
        @click="ui.drawerOpen.value = false"
      />
    </transition>
    <Sidebar
      class="shell-side"
      :class="{ 'is-open': ui.drawerOpen.value }"
      @click="ui.isCompact.value && (ui.drawerOpen.value = false)"
    />

    <div class="shell-center">
      <main
        ref="scroller"
        v-overlay-scroll
        class="shell-main"
        :class="{ 'is-immersive': isNowPlaying }"
        tabindex="-1"
      >
        <!-- Not on Now Playing: that screen is the music and nothing else. -->
        <HealthBanner :away="isNowPlaying" />
        <router-view v-slot="{ Component, route: r }">
          <!-- Views cross-fade instead of snapping in. `out-in` keeps the
               scroll container from having two children at once, which would
               fight scroll restoration. -->
          <transition name="view" mode="out-in">
            <keep-alive :include="cachedViews" :max="12">
              <component :is="Component" :key="viewKey(r)" />
            </keep-alive>
          </transition>
        </router-view>
      </main>
      <SidePanel v-if="showPanel && ui.panelFloating.value" />
    </div>

    <SidePanel v-if="showPanel && !ui.panelFloating.value" class="shell-panel" />

    <PlayerBar class="shell-player" />
  </div>

  <ResizeHandles v-if="showResizeHandles" />
  <ContextMenuHost />
  <DialogHost />
  <ToastHost />
  <ShortcutsDialog />
  <ReportDialog />
  <LyricsSubmit :open="submitOpen" @close="submitOpen = false" />
  <Onboarding />
</template>

<script setup>
import { ensureFullWindow } from '/src/desktop/fullWindow'
import { ref, computed, provide, nextTick, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TitleBar from './components/shell/TitleBar.vue'
import HealthBanner from '/src/components/shell/HealthBanner.vue'
import Sidebar from './components/shell/Sidebar.vue'
import PlayerBar from './components/shell/PlayerBar.vue'
import SidePanel from './components/shell/SidePanel.vue'
import MiniMode from './components/shell/MiniMode.vue'
import ResizeHandles from './components/shell/ResizeHandles.vue'
import ContextMenuHost from './components/ui/ContextMenuHost.vue'
import DialogHost from './components/ui/DialogHost.vue'
import ToastHost from './components/ui/ToastHost.vue'
import ReportDialog from '/src/components/ui/ReportDialog.vue'
import ShortcutsDialog from './components/ui/ShortcutsDialog.vue'
import LyricsSubmit from './components/LyricsSubmit.vue'
import Onboarding from './components/Onboarding.vue'
import { startOnboarding } from './model/onboarding'
import { useUi } from './model/ui'
import { usePlayer } from './model/player'
import { desktop } from './desktop/bridge'

const route = useRoute()
const router = useRouter()
const ui = useUi()
const player = usePlayer()
const win = desktop.state

// The main pane is THE scroll container for views (the window never
// scrolls). Views and virtualized lists inject it.
const scroller = ref(null)
provide('viewScroller', scroller)

const isNowPlaying = computed(() => route.name === 'NowPlaying')
// The panel only earns its space once something is loaded in the player.
const showPanel = computed(
  () =>
    !!ui.panel.value &&
    !isNowPlaying.value &&
    (!!player.currentTrack.value || player.playlist.value.length > 0)
)
const showResizeHandles = computed(
  () =>
    desktop.isDesktop &&
    !win.nativeFrame &&
    !win.maximized &&
    !win.fullscreen &&
    !win.mini
)

// Views that keep their state (results, scroll, filters) between visits.
const cachedViews = [
  'Home',
  'Search',
  'Library',
  'Artists',
  'Artist',
  'ExploreArtist',
  'ExploreCollection',
  'Downloads',
  'Liked',
]

function viewKey(r) {
  // One instance per artist/album; a single Search instance whose query
  // changes in place (search-as-you-type).
  return r.name === 'Search' ? 'search' : r.fullPath.split('?')[0]
}

// --- Scroll restoration: Back/Forward return to where you were -------------
const positions = new Map()
let popNavigation = false
function onPopState() {
  popNavigation = true
}
function restoreScroll(y) {
  const el = scroller.value
  if (!el) return
  if (!y) {
    el.scrollTop = 0
    return
  }
  const started = performance.now()
  const attempt = () => {
    el.scrollTop = y
    // Content may still be loading: keep trying briefly.
    if (Math.abs(el.scrollTop - y) > 2 && performance.now() - started < 1500) {
      requestAnimationFrame(attempt)
    }
  }
  attempt()
}
const removeBefore = router.beforeEach((to, from) => {
  if (scroller.value && from.name) positions.set(from.fullPath, scroller.value.scrollTop)
})
const removeAfter = router.afterEach((to, from) => {
  const pop = popNavigation
  popNavigation = false
  // Live search replaces the route in place: keep the scroll untouched.
  if (to.name === 'Search' && from.name === 'Search' && !pop) return
  nextTick(() => restoreScroll(pop ? positions.get(to.fullPath) || 0 : 0))
})

// --- Lyrics contribution modal (opened from several places) ---------------
const submitOpen = ref(false)
async function openSubmit() {
  // Never inside the mini player: the editor needs the room.
  await ensureFullWindow()
  submitOpen.value = true
}

onMounted(() => {
  startOnboarding()
  window.addEventListener('popstate', onPopState)
  window.addEventListener('dannify:open-lyrics-submit', openSubmit)
  // Bring back the track that was playing when the app was last closed,
  // cued to where it stopped and paused. Done after mount so the player bar
  // is already on screen when it fills in.
  player.restoreSession()
})
onUnmounted(() => {
  window.removeEventListener('popstate', onPopState)
  window.removeEventListener('dannify:open-lyrics-submit', openSubmit)
  removeBefore()
  removeAfter()
})
</script>

<style>
.shell {
  --side-w: var(--sidebar-w);
  display: grid;
  height: 100%;
  grid-template-rows: var(--titlebar-h) minmax(0, 1fr) var(--player-h);
  grid-template-columns: var(--side-w) minmax(0, 1fr) auto;
  grid-template-areas:
    'title title title'
    'side center panel'
    'player player player';
  column-gap: var(--gap);
  padding: 0 var(--gap);
}
.shell.is-rail {
  --side-w: var(--rail-w);
}
.shell-title {
  grid-area: title;
  margin: 0 calc(var(--gap) * -1);
}
.shell-side {
  grid-area: side;
}
.shell-center {
  grid-area: center;
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 0;
}
.shell-main {
  position: relative;
  flex: 1;
  min-width: 0;
  overflow-x: hidden;
  overflow-y: auto;
  border-radius: var(--radius-panel);
  background: rgb(var(--c-panel));
  outline: none;
  scroll-padding-top: 48px;
  /* Views restore their own scroll position; Chromium's anchoring would
     fight that (and jitter virtualized lists as rows are recycled). */
  overflow-anchor: none;
}
.shell-main.is-immersive {
  overflow: hidden;
  background: #0c0c0e;
}
.shell-panel {
  grid-area: panel;
}
.shell-player {
  grid-area: player;
  margin: 0 calc(var(--gap) * -1);
}

/* Phone-sized browsers: sidebar becomes a drawer. */
.shell.is-compact {
  grid-template-columns: minmax(0, 1fr);
  grid-template-areas:
    'title'
    'center'
    'player';
}
.shell.is-compact .shell-side {
  position: fixed;
  top: var(--titlebar-h);
  bottom: var(--player-h);
  left: 0;
  z-index: 70;
  width: min(300px, 86vw);
  border-radius: 0 var(--radius-panel) var(--radius-panel) 0;
  box-shadow: var(--shadow-pop);
  transform: translateX(-105%);
  transition: transform 0.24s var(--ease-out);
}
.shell.is-compact .shell-side.is-open {
  transform: none;
}
.shell-scrim {
  position: fixed;
  inset: var(--titlebar-h) 0 var(--player-h) 0;
  z-index: 69;
  background: rgb(0 0 0 / 0.5);
}
.scrim-enter-active,
.scrim-leave-active {
  transition: opacity 0.2s ease;
}
.scrim-enter-from,
.scrim-leave-to {
  opacity: 0;
}

html.is-col-resizing,
html.is-col-resizing * {
  cursor: ew-resize !important;
  user-select: none !important;
}
</style>
