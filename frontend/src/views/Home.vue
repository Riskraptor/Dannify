<template>
  <div class="pb-12">
    <header class="view-pad flex items-end justify-between gap-4 pb-5 pt-7">
      <h1 class="text-[30px] font-bold tracking-tight">{{ greeting }}</h1>
      <button
        v-if="!account.signedIn.value && desktop.isDesktop"
        class="btn btn-pill shrink-0"
        :disabled="account.busy.value"
        @click="account.signIn()"
      >
        <Icon icon="ph:google-logo" class="h-4 w-4" />
        {{ t('account.connect') }}
      </button>
    </header>

    <!-- First run: nothing downloaded, nothing played, no feed yet -->
    <section v-if="isFresh" class="view-pad">
      <div class="welcome">
        <div class="welcome-glow" aria-hidden="true" />
        <img src="../assets/dannify.svg" alt="" class="relative h-14 w-14 drag-none" />
        <h2 class="relative mt-5 text-2xl font-bold tracking-tight">{{ t('home.welcomeTitle') }}</h2>
        <p class="relative mt-2 max-w-lg text-[14px] leading-relaxed text-fg/65">
          {{ t('home.welcomeText') }}
        </p>
        <form class="welcome-search relative" @submit.prevent="submitWelcome">
          <Icon icon="ph:magnifying-glass" class="welcome-search-icon" />
          <input
            v-model="welcomeQuery"
            type="text"
            class="field h-11 rounded-full pl-11 text-sm"
            :placeholder="t('search.placeholder')"
            spellcheck="false"
          />
        </form>
        <div class="relative mt-4 flex flex-wrap items-center justify-center gap-2 text-xs text-fg/55">
          <span class="pill-muted"><Icon icon="ph:magnifying-glass" class="h-3 w-3" /> {{ t('home.tipSearch') }}</span>
          <span class="pill-muted"><Icon icon="ph:download-simple" class="h-3 w-3" /> {{ t('home.tipDownload') }}</span>
          <span class="pill-muted"><Icon icon="ph:microphone-stage" class="h-3 w-3" /> {{ t('home.tipLyrics') }}</span>
        </div>
      </div>
    </section>

    <!-- Jump back in: the last things you played -->
    <section v-if="quick.length" class="shelf-block view-pad">
      <header class="shelf-head is-flush">
        <h2 class="shelf-title">{{ t('home.jumpBackIn') }}</h2>
      </header>
      <div class="tile-grid">
        <SongTile
          v-for="(row, i) in quick"
          :key="row.key + i"
          :row="row"
          :source="quick"
          :menu="() => recentMenu(i)"
          @play="playRecent(i)"
        />
      </div>
    </section>

    <div class="shelves">
      <!-- Your YouTube Music picks (personalized once signed in) -->
      <template v-for="(section, si) in feedSections" :key="section.title + si">
        <section v-if="section.songs" class="shelf-block">
          <header class="shelf-head">
            <h2 class="shelf-title">{{ section.title }}</h2>
            <button class="shelf-more" @click="playRows(section.rows, 0)">
              {{ t('home.playAll') }}
            </button>
          </header>
          <div class="tile-grid is-flush">
            <SongTile
              v-for="(row, i) in section.rows"
              :key="row.key"
              :row="row"
              :source="section.rows"
              @play="playRows(section.rows, i)"
            />
          </div>
        </section>
        <Shelf v-else :title="section.title">
          <MediaCard
            v-for="it in section.items"
            :key="it.type + it.browse_id"
            :item="it"
            :kind="it.type"
            @open="openCard(it)"
          />
        </Shelf>
      </template>

      <!-- No feed and no connection: said, rather than an empty page. -->
      <p v-if="feedOffline" class="feed-note">
        <Icon icon="ph:wifi-slash" class="h-4 w-4 shrink-0" />
        {{ t('net.offlineHome') }}
      </p>

      <!-- Loading. Shaped like the shelves it stands in for: bare grey slabs
           read as a broken page, not a loading one. -->
      <div v-if="showFeedSkeleton && !feedSections.length" class="feed-skeleton">
        <div v-for="band in 2" :key="band" class="shelf-block">
          <header class="shelf-head">
            <span class="skeleton h-[18px] w-[150px] rounded" />
          </header>
          <div class="tile-grid is-flush">
            <div v-for="n in 6" :key="n" class="row-ghost">
              <span class="skeleton row-ghost-cover" />
              <span class="row-ghost-lines">
                <span class="skeleton h-[11px] rounded" :style="ghostWidth(n)" />
                <span class="skeleton h-[9px] w-[38%] rounded" />
              </span>
            </div>
          </div>
        </div>
      </div>

      <Shelf
        v-if="account.signedIn.value && likedRows.length"
        :title="t('account.likedSongs')"
        :more-label="t('home.showAll')"
        @more="router.push({ name: 'Liked' })"
      >
        <MediaCard
          v-for="(row, i) in likedRows.slice(0, 12)"
          :key="row.key"
          :item="{ name: row.title, cover: row.cover }"
          kind="track"
          :subtitle-text="row.artistText"
          playable
          :menu="() => trackMenu([row], { source: likedRows })"
          @open="playRows(likedRows, i)"
          @play="playRows(likedRows, i)"
        />
      </Shelf>

      <Shelf
        v-if="account.playlists.value.length"
        :title="t('account.yourPlaylists')"
      >
        <MediaCard
          v-for="p in account.playlists.value"
          :key="p.browse_id"
          :item="p"
          kind="playlist"
          @open="ex.openPlaylist(p.browse_id)"
        />
      </Shelf>

      <Shelf
        v-if="recentlyAdded.length"
        :title="t('home.recentlyAdded')"
        :more-label="t('home.showAll')"
        @more="router.push({ name: 'Library', query: { sort: 'added' } })"
      >
        <MediaCard
          v-for="(row, i) in recentlyAdded"
          :key="row.key"
          :item="{ name: row.title, cover: row.cover }"
          kind="track"
          :subtitle-text="row.artistText"
          playable
          :menu="() => trackMenu([row])"
          @open="playRows(recentlyAdded, i)"
          @play="playRows(recentlyAdded, i)"
        />
      </Shelf>

      <Shelf
        v-if="topArtists.length"
        :title="t('home.yourArtists')"
        :more-label="t('home.showAll')"
        @more="router.push({ name: 'Artists' })"
      >
        <MediaCard
          v-for="a in topArtists"
          :key="a.name"
          :item="{ name: a.name, cover: a.cover ? API.coverFileURL(a.cover, a.cover_v) : '' }"
          kind="artist"
          :subtitle-text="t('nav.artistSongs', { count: a.count })"
          playable
          @open="router.push({ name: 'Artist', params: { name: a.name } })"
          @play="playArtist(a.name)"
        />
      </Shelf>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { useDeferred } from '/src/model/deferred'
import { desktop } from '/src/desktop/bridge'
import { usePlayer } from '/src/model/player'
import { useLibrary } from '/src/model/library'
import { useRecent, trackKey } from '/src/model/recent'
import { useHomeFeed } from '/src/model/home'
import { useConnectivity, whenOnline } from '/src/model/connectivity'
import { useAccount } from '/src/model/account'
import { localRow, songRow, queueRow, playRows, trackMenu, onArtistPage } from '/src/model/tracks'
import { useExplore } from '/src/model/explore'
import { warmAll } from '/src/model/prefetch'
import { onRefresh } from '/src/model/useRefresh'
import { useI18n } from '/src/i18n'
import Shelf from '/src/components/ui/Shelf.vue'
import SongTile from '/src/components/ui/SongTile.vue'
import MediaCard from '/src/components/MediaCard.vue'

const { t } = useI18n()
const router = useRouter()
const player = usePlayer()
const lib = useLibrary()
const recent = useRecent()
const account = useAccount()
const feed = useHomeFeed()
const ex = useExplore()

lib.ensureLoaded()
feed.load().then(warmFirstShelf)
onActivated(() => {
  lib.ensureLoaded()
  feed.load()
})

// Home is where most sessions start, so the songs at the top of it get
// resolved before anyone reaches for the mouse.
function warmFirstShelf() {
  const first = feedSections.value.find((section) => section.songs)
  if (first) warmAll(first.rows.map((row) => row.raw), 4)
}
onRefresh(() => feed.load(true))

const feedLoading = feed.loading
// The feed is usually already warm, so a skeleton would flash. Only show
// one for a load slow enough that the user would otherwise see nothing.
const showFeedSkeleton = useDeferred(feedLoading)

// No feed because there is no connection: said on the page, and the feed
// fetched again by itself when the connection is back. Asked quietly (a
// probe, not the "no internet" notice): the page already says it.
const connectivity = useConnectivity()
const feedOffline = computed(
  () =>
    feed.loaded.value &&
    !feed.loading.value &&
    !!feed.error.value &&
    !feed.sections.value.length &&
    connectivity.isOffline.value
)
watch(
  () => feed.error.value,
  async (err) => {
    if (!err || feed.sections.value.length) return
    if (!(await connectivity.probe())) whenOnline(() => feed.load(true))
  }
)

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 5) return t('home.goodEvening')
  if (h < 12) return t('home.goodMorning')
  if (h < 18) return t('home.goodAfternoon')
  return t('home.goodEvening')
})

// The welcome panel is for a genuinely empty app, not for the two seconds
// before the feed lands. Showing it during the load meant every launch
// flashed "Welcome to Dannify" and then replaced it with shelves.
const isFresh = computed(
  () =>
    lib.loaded.value &&
    feed.loaded.value &&
    !feed.loading.value &&
    lib.tracks.value.length === 0 &&
    recent.played.value.length === 0 &&
    !feed.sections.value.length
)

// Titles are not all one length, and a column of identical bars is the thing
// that makes a skeleton look fake. Deterministic so it does not reflow.
const GHOST_WIDTHS = ['72%', '54%', '83%', '61%', '77%', '48%']
function ghostWidth(n) {
  return { width: GHOST_WIDTHS[(n - 1) % GHOST_WIDTHS.length] }
}

// Recently played, as rows so the tiles share the track context menu.
const quick = computed(() =>
  recent.played.value.slice(0, 8).map((tr, i) => queueRow(tr, i))
)

// Sections whose items are all songs get the wide-tile grid; everything else
// (albums, playlists, artists) keeps the card shelf.
//
// YouTube's feed happily repeats a track across "Quick picks", "Trending"
// and "Listen again", and the tiles above already show what you just
// played. Anything seen once is dropped from every later shelf, so the page
// never shows you the same song twice.
const feedSections = computed(() => {
  const seen = new Set(
    quick.value.map((row) => row.raw && (row.raw.video_id || row.raw.song_id)).filter(Boolean)
  )
  const out = []
  for (const section of feed.sections.value) {
    const fresh = []
    for (const item of section.items || []) {
      if (!item) continue
      const id = item.song_id || item.video_id || item.browse_id
      if (id && seen.has(id)) continue
      if (id) seen.add(id)
      fresh.push(item)
    }
    if (!fresh.length) continue
    const songs = fresh.every((it) => it.type === 'song')
    const entry = {
      title: section.title || t('home.forYou'),
      items: songs ? fresh : fresh.filter((it) => it.type !== 'song'),
      songs,
      rows: songs ? fresh.slice(0, 12).map(songRow) : [],
    }
    // A shelf of three leftovers looks broken; fold it away instead.
    if (entry.songs ? entry.rows.length >= 2 : entry.items.length >= 3) out.push(entry)
  }
  return out
})

const likedRows = computed(() => account.liked.value.map(songRow))

const recentlyAdded = computed(() =>
  [...lib.tracks.value]
    .sort((a, b) => (b.added || 0) - (a.added || 0))
    .slice(0, 16)
    .map(localRow)
)

const topArtists = computed(() =>
  [...lib.artists.value].sort((a, b) => b.count - a.count).slice(0, 16)
)

function playRecent(i) {
  const list = recent.played.value
  const tr = list[i]
  if (!tr) return
  if (player.currentTrack.value && trackKey(player.currentTrack.value) === trackKey(tr)) {
    player.toggle()
    return
  }
  // Queue the history from the clicked track onward.
  player.setPlaylist(list.slice(i).map((x) => ({ ...x })), { startIndex: 0 })
}

function recentMenu(i) {
  const tr = recent.played.value[i]
  return [
    { label: t('actions.play'), icon: 'ph:play', action: () => playRecent(i) },
    { label: t('actions.playNext'), icon: 'ph:queue', action: () => player.enqueue([{ ...tr }], { next: true }) },
    { label: t('actions.addToQueue'), icon: 'ph:list-plus', action: () => player.enqueue([{ ...tr }]) },
    { divider: true },
    {
      label: t('home.removeFromHistory'),
      icon: 'ph:clock-counter-clockwise',
      action: () => recent.forgetPlayed(tr),
    },
  ]
}

function openCard(item) {
  if (item.type === 'artist') ex.openArtist(item.browse_id)
  else if (item.type === 'playlist') ex.openPlaylist(item.browse_id)
  else ex.openAlbum(item.browse_id)
}

function playArtist(name) {
  const rows = lib.tracks.value
    .filter((tr) => onArtistPage(tr, name))
    .map(localRow)
  playRows(rows, 0)
}

const welcomeQuery = ref('')
function submitWelcome() {
  const q = welcomeQuery.value.trim()
  if (!q) return
  recent.rememberSearch(q)
  router.push({ name: 'Search', params: { query: q } })
}
</script>

<style scoped>
.welcome {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  overflow: hidden;
  padding: 48px 24px 40px;
  border-radius: 14px;
  text-align: center;
  background: rgb(var(--c-raised));
  border: 1px solid rgb(var(--c-tint) / 0.06);
}
.welcome-glow {
  position: absolute;
  top: -120px;
  left: 50%;
  width: 520px;
  height: 320px;
  transform: translateX(-50%);
  border-radius: 999px;
  background: rgb(var(--c-accent) / 0.22);
  filter: blur(80px);
  /* A layer of its own: blurred once and then moved, instead of blurred
     again on every repaint while the page scrolls. */
  will-change: transform;
}
.welcome-search {
  width: min(520px, 100%);
  margin-top: 24px;
}
.welcome-search-icon {
  position: absolute;
  left: 16px;
  top: 50%;
  width: 18px;
  height: 18px;
  transform: translateY(-50%);
  color: rgb(var(--c-fg) / 0.5);
  pointer-events: none;
}
.tile-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 8px;
  margin-bottom: 32px;
}
.tile-grid.is-flush {
  margin-bottom: 0;
  padding: 0 10px;
}
.shelves {
  padding: 0 14px;
}
@media (min-width: 1024px) {
  .shelves {
    padding: 0 22px;
  }
}
.shelf-block {
  margin-bottom: 28px;
}
.shelf-head.is-flush {
  padding-left: 0;
  padding-right: 0;
}
.shelf-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 10px;
  padding: 0 10px;
}
.shelf-title {
  font-size: 21px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.shelf-more {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.55);
}
.shelf-more:hover {
  color: rgb(var(--c-fg));
  text-decoration: underline;
}
.feed-note {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 8px 0 28px;
  padding: 12px 16px;
  border-radius: 10px;
  background: rgb(var(--c-tint) / 0.05);
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.7);
}
.feed-skeleton {
  padding-bottom: 28px;
}

</style>
