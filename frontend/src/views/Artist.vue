<template>
  <div class="pb-12">
    <div v-if="loading && !artist" class="view-pad pt-10">
      <div class="flex items-end gap-6">
        <div class="skeleton h-48 w-48 rounded-full" />
        <div class="flex-1 space-y-3">
          <div class="skeleton h-4 w-24" />
          <div class="skeleton h-12 w-1/2" />
        </div>
      </div>
    </div>

    <EmptyState v-else-if="!artist" icon="ph:warning-circle" :title="t('net.loadFailed')">
      <div class="flex gap-2">
        <button class="btn btn-pill" @click="load">{{ t('common.retry') }}</button>
        <button class="btn btn-pill" @click="router.push({ name: 'Artists' })">{{ t('artist.back') }}</button>
      </div>
    </EmptyState>

    <!-- Nothing of theirs saved, and nothing found online either. -->
    <EmptyState
      v-else-if="artist.gone && onlineState === 'missing'"
      icon="ph:user"
      :title="t('artist.goneTitle', { name: artist.name })"
      :text="t('artist.goneHint')"
    >
      <div class="flex gap-2">
        <button class="btn btn-pill" @click="router.push({ name: 'Search', params: { query: artist.name } })">
          {{ t('artist.searchFor', { name: artist.name }) }}
        </button>
        <button class="btn btn-pill" @click="router.push({ name: 'Artists' })">{{ t('artist.back') }}</button>
      </div>
    </EmptyState>

    <template v-else>
      <CollectionHero
        :title="artist.name"
        :label="t('artist.label')"
        :cover="heroCover"
        :cover-fallback="localCover"
        kind="artist"
        round
        :playing="playingHere"
        @play="playAll"
      >
        <template #meta>
          <span v-if="artist.gone">{{ t('artist.noneSaved') }}</span>
          <template v-else>
            <span>{{ t('artists.trackCount', { count: artist.count }) }}</span>
            <span class="opacity-50">•</span>
            <span>{{ t('artist.albumCount', { count: artist.albums.length }) }}</span>
          </template>
          <template v-if="online && online.subscribers">
            <span class="opacity-50">•</span>
            <span>{{ online.subscribers }} {{ t('explore.subscribers') }}</span>
          </template>
        </template>
        <template v-if="online && online.description" #sub>
          <p class="selectable bio" :class="{ 'is-open': bioOpen }">{{ online.description }}</p>
          <button v-if="online.description.length > 180" class="bio-more" @click="bioOpen = !bioOpen">
            {{ bioOpen ? t('explore.showLess') : t('explore.readMore') }}
            <Icon :icon="bioOpen ? 'ph:caret-up-bold' : 'ph:caret-down-bold'" class="h-3 w-3" />
          </button>
        </template>
        <template #actions>
          <button class="play-fab" :title="t('artists.playAll')" :disabled="!playableRows.length" @click="playAll">
            <Icon :icon="playingHere ? 'ph:pause-fill' : 'ph:play-fill'" class="h-5 w-5" />
          </button>
          <button
            class="icon-btn is-round h-10 w-10"
            :title="t('artist.shuffle')"
            :disabled="!playableRows.length"
            @click="shuffleRows(playableRows)"
          >
            <Icon icon="ph:shuffle" class="h-6 w-6" />
          </button>
          <button
            v-if="!artist.gone"
            class="btn btn-pill"
            :title="t('details.artistHint')"
            :disabled="detailsRunning"
            @click="refreshThisArtist"
          >
            <Icon icon="ph:arrows-clockwise" class="h-4 w-4" :class="{ 'animate-spin': detailsRunning }" />
            {{
              detailsRunning
                ? t('details.progress', { done: detailsDone, total: detailsTotal })
                : t('details.refresh')
            }}
          </button>
          <button
            v-if="online && online.browse_id"
            class="btn btn-pill"
            :title="t('artist.fullPageHint')"
            @click="openFullPage"
          >
            <Icon icon="ph:arrow-square-out" class="h-4 w-4" />
            {{ t('artist.fullPage') }}
          </button>
          <FollowButton
            v-if="online"
            :channel-id="online.channel_id || (String(online.browse_id || '').startsWith('UC') ? online.browse_id : '')"
            :browse-id="online.browse_id || ''"
            :name="online.name || artist.name"
            :cover="online.cover_url || ''"
          />
        </template>
      </CollectionHero>

      <!-- One list, with the album on the row. It used to be a heading per
           album, which meant a library that is mostly singles turned into a
           column of headings with one track under each. The online artist
           page has always been a plain list; this is the same thing. -->
      <!-- Every song of theirs deleted: the page stays, says so, and their
           music carries on below. It used to turn into "Artist not found",
           for an artist who was right there a moment before. -->
      <p v-if="artist.gone" class="view-pad gone-note">
        <Icon icon="ph:info" class="h-4 w-4 shrink-0" />
        {{ t('artist.noneSavedNote', { name: artist.name }) }}
      </p>
      <section v-else class="view-pad mb-10">
        <h2 class="section-title">{{ t('artist.inLibrary') }}</h2>
        <TrackTable
          :rows="allRows"
          :sticky-offset="56"
          show-album
          deletable
          selectable
          selection-bar
          :on-play="(i) => playRows(allRows, i)"
        />
      </section>

      <!-- The rest of their music, below what is already saved. This used to
           be a "Search online" button that left the page; now the page just
           carries on, and nothing already in the library appears twice. -->
      <section class="more" aria-live="polite">
        <div class="view-pad more-head">
          <h2 class="section-title">{{ t('artist.moreFrom', { name: artist.name }) }}</h2>
          <button v-if="online && online.browse_id" class="more-link" @click="openFullPage">
            {{ t('artist.fullPage') }}
            <Icon icon="ph:arrow-right" class="h-3.5 w-3.5" />
          </button>
        </div>

        <div v-if="onlineState === 'loading'" class="view-pad" aria-busy="true">
          <div v-for="n in 5" :key="n" class="row-ghost">
            <span class="skeleton row-ghost-cover" />
            <span class="row-ghost-lines">
              <span class="skeleton h-[11px] rounded" :style="ghostWidth(n)" />
              <span class="skeleton h-[9px] w-[34%] rounded" />
            </span>
          </div>
          <div class="mt-6 flex gap-3">
            <div v-for="n in 4" :key="n" class="skeleton aspect-square w-40 rounded-md" />
          </div>
        </div>

        <div v-else-if="onlineState === 'failed' || onlineState === 'offline'" class="view-pad more-note">
          <Icon :icon="onlineState === 'offline' ? 'ph:wifi-slash' : 'ph:cloud-slash'" class="h-4 w-4" />
          <span>{{ onlineState === 'offline' ? t('artist.moreOffline') : t('artist.moreUnavailable') }}</span>
          <button class="btn btn-pill h-7 text-xs" @click="loadOnline(true)">{{ t('common.retry') }}</button>
        </div>

        <p v-else-if="onlineState === 'missing'" class="view-pad more-note">
          <Icon icon="ph:magnifying-glass" class="h-4 w-4" />
          {{ t('artist.notOnline') }}
        </p>

        <template v-else-if="online">
          <div class="view-pad mb-8">
            <div class="more-subhead">
              <h3>{{ t('artist.popularNotSaved') }}</h3>
              <button
                v-if="unsavedRows.length"
                class="btn btn-pill h-8 text-xs"
                @click="downloadRows(unsavedRows)"
              >
                <Icon icon="ph:download-simple" class="h-4 w-4" />
                {{ t('artist.saveAll', { count: unsavedRows.length }) }}
              </button>
            </div>
            <template v-if="unsavedRows.length">
              <TrackTable
                :rows="shownUnsaved"
                :sticky-offset="56"
                selectable
                :on-play="(i) => playRows(unsavedRows, i)"
              />
              <button v-if="unsavedRows.length > moreLimit" class="more-btn" @click="moreLimit += 15">
                {{ t('explore.showMore') }}
              </button>
              <button v-else-if="unsavedRows.length > 8" class="more-btn" @click="moreLimit = 8">
                {{ t('explore.showLess') }}
              </button>
            </template>
            <p v-else class="more-note">
              <Icon icon="ph:check-circle" class="h-4 w-4 text-accent" />
              {{ t('artist.everythingSaved') }}
            </p>
          </div>

          <div class="shelves">
            <Shelf v-if="online.albums && online.albums.length" :title="t('explore.albums')">
              <MediaCard
                v-for="al in online.albums"
                :key="al.browse_id"
                :item="al"
                kind="album"
                :subtitle-text="albumNote(al)"
                @open="router.push({ name: 'ExploreAlbum', params: { id: al.browse_id } })"
              />
            </Shelf>
            <Shelf v-if="online.singles && online.singles.length" :title="t('explore.singles')">
              <MediaCard
                v-for="al in online.singles"
                :key="al.browse_id"
                :item="al"
                kind="album"
                :subtitle-text="albumNote(al)"
                @open="router.push({ name: 'ExploreAlbum', params: { id: al.browse_id } })"
              />
            </Shelf>
          </div>
        </template>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import FollowButton from '/src/components/ui/FollowButton.vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { usePlayer } from '/src/model/player'
import {
  localRow,
  songRow,
  playRows,
  shuffleRows,
  downloadRows,
  isRowDownloaded,
} from '/src/model/tracks'
import { useLibraryIndex } from '/src/model/libraryIndex'
import { useArtistLinks } from '/src/model/artistLinks'
import { refreshArtists, detailsRunning, detailsDone, detailsTotal } from '/src/model/details'
import { onRefresh, onLibraryChanged } from '/src/model/useRefresh'
import { useI18n } from '/src/i18n'
import { songKey } from '/src/model/songKey'
import { failedForNetwork, whenOnline } from '/src/model/connectivity'
import CollectionHero from '/src/components/ui/CollectionHero.vue'
import TrackTable from '/src/components/ui/TrackTable.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'
import Shelf from '/src/components/ui/Shelf.vue'
import MediaCard from '/src/components/MediaCard.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const player = usePlayer()
const libIndex = useLibraryIndex()
const artistLinks = useArtistLinks()

const artist = ref(null)
const loading = ref(false)

// The artist's own picture when it is known, the cover of one of their songs
// until then (and offline).
const localCover = computed(() =>
  artist.value && artist.value.cover ? API.coverFileURL(artist.value.cover, artist.value.cover_v) : ''
)
const heroCover = computed(() => {
  if (!artist.value) return ''
  const photo =
    (online.value && online.value.cover_url) || artistLinks.artistPhoto(artist.value.name, 544)
  return photo || localCover.value
})

const albums = computed(() =>
  artist.value
    ? artist.value.albums.map((al) => ({ ...al, rows: al.tracks.map(localRow) }))
    : []
)
const allRows = computed(() => albums.value.flatMap((al) => al.rows))
// What Play plays: their saved songs, or with none saved, their popular ones.
const playableRows = computed(() => (allRows.value.length ? allRows.value : unsavedRows.value))

// Whether what is playing belongs to this page, and separately whether it is
// actually running. Both used to be one flag, so a paused collection looked
// unplayed and the same button that paused it started it again from the top.
const currentHere = computed(() => {
  const cur = player.currentTrack.value
  if (!cur) return false
  if (allRows.value.length) return allRows.value.some((r) => r.file && r.file === cur.file)
  const id = cur.video_id || ''
  return !!id && unsavedRows.value.some((r) => r.raw && (r.raw.video_id || r.raw.song_id) === id)
})
const playingHere = computed(() => currentHere.value && player.isPlaying.value)

function playAll() {
  if (currentHere.value) return player.toggle()
  if (!playableRows.value.length) return
  player.setShuffle(false)
  playRows(playableRows.value, 0)
}

// Each artist gets a page of its own (see viewKey in App.vue), so the name is
// fixed for the life of this one. Reading it from the route when a delayed
// reload fired picked up whichever artist was on screen by then, and this
// page quietly turned into theirs.
const name = String(route.params.name || '')
let seq = 0
let reloadTimer = null

async function load() {
  if (!name) return
  const mine = ++seq
  loading.value = true
  try {
    const res = await API.getArtist(name)
    if (mine !== seq) return // a newer read is on its way
    const data = res.data
    artist.value = data && typeof data === 'object' && Array.isArray(data.albums) ? data : null
  } catch (err) {
    if (mine !== seq) return
    if (err && err.response && err.response.status === 404) {
      // None of their songs in the library (any more): still them. The page
      // keeps their name, picture and music; only what was saved is gone.
      const shown = (artist.value && artist.value.name) || name
      artist.value = { name: shown, count: 0, albums: [], cover: '', cover_v: 0, gone: true }
    } else if (!artist.value) {
      // A hiccup on the first read: nothing to show, and a retry offered.
      artist.value = null
    }
  } finally {
    if (mine === seq) loading.value = false
  }
}

// ----- The rest of their music ------------------------------------------------
const online = ref(null)
// idle | loading | ready | missing | failed
const onlineState = ref('idle')
const moreLimit = ref(8)

async function loadOnline(force = false) {
  if (!name || (!force && (onlineState.value === 'loading' || onlineState.value === 'ready'))) return
  onlineState.value = 'loading'
  try {
    const res = await API.getArtistOnline(name)
    online.value = res.data && typeof res.data === 'object' ? res.data : null
    onlineState.value = online.value ? 'ready' : 'missing'
  } catch (err) {
    if (err && err.response && err.response.status === 404) onlineState.value = 'missing'
    else if (await failedForNetwork(err)) {
      onlineState.value = 'offline'
      whenOnline(() => {
        if (onlineState.value === 'offline') loadOnline(true)
      })
    } else onlineState.value = 'failed'
  }
}

// Their songs that are not saved yet, each once. Anything already in the
// library is on the list above and is left out here; so is a song YouTube
// lists twice. "Twice" means the same song, not only the same video: the
// album track and its music video ("Commando" and "Commando (Official Video)")
// are one song, and one of them saved is that song saved. A remix, a live or
// an acoustic version is a song of its own and stays.
const savedSongKeys = computed(() => new Set(allRows.value.map((r) => songKey(r.title))))
const unsavedRows = computed(() => {
  void libIndex.byVideoId.value
  if (!online.value || !Array.isArray(online.value.songs)) return []
  const seen = new Set()
  const out = []
  for (const song of online.value.songs) {
    const row = songRow(song)
    const id = song.video_id || song.song_id || row.key
    const key = songKey(row.title)
    if (seen.has(id) || (key && seen.has(key))) continue
    seen.add(id)
    if (key) seen.add(key)
    if (isRowDownloaded(row) || (key && savedSongKeys.value.has(key))) continue
    out.push(row)
  }
  return out
})

// Of an album of theirs online, how many songs are saved, by the album's name.
const savedPerAlbum = computed(() => {
  // By each song's own album: the list above files a single under "Singles".
  const counts = new Map()
  for (const row of allRows.value) {
    const key = songKey(row.album || '')
    if (key) counts.set(key, (counts.get(key) || 0) + 1)
  }
  return counts
})
function albumNote(al) {
  const saved = savedPerAlbum.value.get(songKey(al.name)) || 0
  const parts = []
  if (al.year) parts.push(al.year)
  if (saved) parts.push(t('artist.savedCount', { count: saved }))
  else parts.push(al.album_type || t('explore.album'))
  return parts.join(' · ')
}

const bioOpen = ref(false)

function openFullPage() {
  if (online.value && online.value.browse_id) {
    router.push({ name: 'ExploreArtist', params: { id: online.value.browse_id } })
  }
}
const shownUnsaved = computed(() => unsavedRows.value.slice(0, moreLimit.value))

const GHOST_WIDTHS = ['72%', '54%', '83%', '61%', '77%', '48%']
function ghostWidth(n) {
  return { width: GHOST_WIDTHS[(n - 1) % GHOST_WIDTHS.length] }
}

// Their picture and online page looked up again, and every saved song of
// theirs brought up to date: one button for "this artist looks wrong".
async function refreshThisArtist() {
  if (!artist.value) return
  const playing = player.currentTrack.value && player.currentTrack.value.file
  const files = allRows.value.map((r) => r.file).filter((f) => f && f !== playing)
  await refreshArtists([artist.value.name], files)
  await artistLinks.load()
  loadOnline(true)
}

onMounted(async () => {
  libIndex.load()
  await load()
  loadOnline()
})
onRefresh(() => {
  load()
  loadOnline(true)
})
onLibraryChanged(() => {
  clearTimeout(reloadTimer)
  reloadTimer = setTimeout(load, 800)
})
onBeforeUnmount(() => clearTimeout(reloadTimer))
</script>

<style scoped>
.section-title {
  margin-bottom: 8px;
  font-size: 21px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.bio {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-line;
}
.bio.is-open {
  display: block;
  max-height: 40vh;
  overflow-y: auto;
  -webkit-line-clamp: unset;
}
.bio-more {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 12px;
  font-weight: 700;
  color: rgb(var(--c-fg) / 0.7);
}
.bio-more:hover {
  color: rgb(var(--c-fg));
}
.gone-note {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 18px;
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.65);
}
.more {
  padding-top: 6px;
  border-top: 1px solid rgb(var(--c-tint) / 0.06);
}
.more-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  padding-top: 18px;
}
.more-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.6);
}
.more-link:hover {
  color: rgb(var(--c-fg));
  text-decoration: underline;
}
.more-subhead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 4px 0 6px;
}
.more-subhead h3 {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: rgb(var(--c-fg) / 0.6);
}
.more-note {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 0 20px;
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.6);
}
.more-btn {
  margin: 8px 0 0 12px;
  font-size: 13px;
  font-weight: 700;
  color: rgb(var(--c-fg) / 0.6);
}
.more-btn:hover {
  color: rgb(var(--c-fg));
}
.shelves {
  padding: 0 14px;
}
@media (min-width: 1024px) {
  .shelves {
    padding: 0 22px;
  }
}
</style>
