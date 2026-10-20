<template>
  <div class="pb-12">
    <!-- Not signed in: what signing in brings, and the way to do it. -->
    <EmptyState
      v-if="!spotify.connected.value"
      icon="ph:spotify-logo-fill"
      :title="t('spotify.bringTitle')"
      :text="spotify.configured.value ? t('spotify.bringText') : t('spotify.notConfiguredHint')"
    >
      <button
        v-if="spotify.configured.value"
        class="btn-accent btn-pill press px-5"
        :disabled="spotify.status.value.signing_in"
        @click="spotify.connect()"
      >
        <span v-if="spotify.status.value.signing_in" class="spinner h-4 w-4" />
        <Icon v-else icon="ph:spotify-logo-fill" class="h-4 w-4" />
        {{ spotify.status.value.signing_in ? t('spotify.waiting') : t('spotify.connect') }}
      </button>
      <router-link v-else :to="{ name: 'Settings', query: { pane: 'accounts' } }" class="btn btn-pill">
        {{ t('spotify.openSettings') }}
      </router-link>
    </EmptyState>

    <template v-else>
      <header class="spx-hero view-pad">
        <span class="spx-avatar">
          <img v-if="me.image && !photoFailed" :src="me.image" alt="" referrerpolicy="no-referrer" @error="photoFailed = true" />
          <Icon v-else icon="ph:spotify-logo-fill" class="h-14 w-14" />
        </span>
        <div class="min-w-0">
          <p class="spx-label"><Icon icon="ph:spotify-logo-fill" class="h-4 w-4" /> {{ t('spotify.title') }}</p>
          <h1 class="spx-name">{{ me.name || t('spotify.yours') }}</h1>
          <p class="spx-text">{{ t('spotify.heroText') }}</p>
        </div>
      </header>

      <!-- The three lists everyone has. -->
      <div class="spx-tiles view-pad">
        <button v-for="tile in TILES" :key="tile.kind" class="spx-tile press" @click="openList(tile.kind)">
          <span class="spx-tile-art" :class="`is-${tile.kind}`"><Icon :icon="tile.icon" class="h-6 w-6" /></span>
          <span class="min-w-0 text-left">
            <span class="spx-tile-title">{{ t(tile.label) }}</span>
            <span class="spx-tile-sub">{{ tileSub(tile.kind) }}</span>
          </span>
        </button>
      </div>

      <div class="shelves">
        <p v-if="problem" class="spx-problem view-pad">{{ t(errorKey(problem)) }}</p>

        <Shelf v-if="playlists.length" :title="t('spotify.playlists')">
          <MediaCard
            v-for="p in playlists"
            :key="p.id"
            :item="{ name: p.name, cover: p.image }"
            kind="playlist"
            :subtitle-text="playlistSub(p)"
            playable
            @open="router.push({ name: 'SpotifyList', params: { kind: 'playlist', id: p.id } })"
            @play="playList('playlist', p.id)"
          />
        </Shelf>

        <Shelf v-if="topArtists.length" :title="t('spotify.topArtists')">
          <MediaCard
            v-for="a in topArtists"
            :key="a.id"
            :item="{ name: a.name, cover: a.image }"
            kind="artist"
            :subtitle-text="a.genres && a.genres.length ? a.genres.join(', ') : t('explore.artist')"
            @open="findArtist(a.name)"
          />
        </Shelf>

        <Shelf v-if="albums.length" :title="t('spotify.albums')">
          <MediaCard
            v-for="a in albums"
            :key="a.id"
            :item="{ name: a.name, cover: a.image }"
            kind="album"
            :subtitle-text="[a.artist, a.year].filter(Boolean).join(' • ')"
            playable
            @open="router.push({ name: 'SpotifyList', params: { kind: 'album', id: a.id } })"
            @play="playList('album', a.id)"
          />
        </Shelf>

        <Shelf v-if="following.length" :title="t('spotify.following')">
          <MediaCard
            v-for="a in following"
            :key="a.id"
            :item="{ name: a.name, cover: a.image }"
            kind="artist"
            :subtitle-text="t('explore.artist')"
            @open="findArtist(a.name)"
          />
        </Shelf>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { errorKey, loadSpotifyPlaylists, reasonOf, spotifyPlaylists, useSpotify } from '/src/model/spotify'
import { playRows, songRow } from '/src/model/tracks'
import { onRefresh } from '/src/model/useRefresh'
import { useI18n } from '/src/i18n'
import Shelf from '/src/components/ui/Shelf.vue'
import MediaCard from '/src/components/MediaCard.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'

// Your Spotify: what signing in to Spotify brings into Dannify. Every song
// plays through YouTube Music; any list can be copied or saved for offline
// from its own page (SpotifyList.vue).

const { t } = useI18n()
const router = useRouter()
const spotify = useSpotify()
const me = computed(() => spotify.user.value)
const photoFailed = ref(false)

const TILES = [
  { kind: 'liked', label: 'spotify.liked', icon: 'ph:heart-fill' },
  { kind: 'top', label: 'spotify.topSongs', icon: 'ph:trophy-fill' },
  { kind: 'recent', label: 'spotify.recent', icon: 'ph:clock-counter-clockwise-bold' },
]

const playlists = spotifyPlaylists
const topArtists = shallowRef([])
const albums = shallowRef([])
const following = shallowRef([])
const likedCount = ref(null)
const problem = ref('')

// Each part on its own: one that fails, or is slow, holds up none of the rest.
async function load() {
  if (!spotify.connected.value) return
  problem.value = ''
  const parts = [
    loadSpotifyPlaylists(true),
    API.spotifyTop('artists', 'medium_term').then((r) => (topArtists.value = r.data.items || [])),
    API.spotifyAlbums().then((r) => (albums.value = r.data.albums || [])),
    API.spotifyArtists().then((r) => (following.value = r.data.artists || [])),
    API.spotifyLiked().then((r) => (likedCount.value = (r.data.songs || []).length)),
  ]
  const results = await Promise.allSettled(parts)
  const failed = results.find((r) => r.status === 'rejected')
  if (failed && results.every((r) => r.status === 'rejected')) problem.value = reasonOf(failed.reason)
  else if (failed && ['expired', 'not_allowed'].includes(reasonOf(failed.reason))) problem.value = reasonOf(failed.reason)
}
watch(() => spotify.connected.value, (on) => on && load(), { immediate: true })
// F5: from Spotify itself, not from what was read a few minutes ago.
onRefresh(() => API.spotifyRefresh().catch(() => {}).then(load))
const onChanged = () => load()
onMounted(() => window.addEventListener('dannify:spotify-changed', onChanged))
onBeforeUnmount(() => window.removeEventListener('dannify:spotify-changed', onChanged))

function tileSub(kind) {
  if (kind === 'liked') return likedCount.value == null ? t('spotify.liked') : t('explore.songCount', { count: likedCount.value })
  if (kind === 'top') return t('spotify.topSongsSub')
  return t('spotify.recentSub')
}
function playlistSub(p) {
  const by = p.mine ? t('spotify.byYou') : p.owner
  return [by, p.count ? t('explore.songCount', { count: p.count }) : ''].filter(Boolean).join(' • ')
}
function openList(kind) {
  router.push({ name: 'SpotifyList', params: { kind } })
}
async function playList(kind, id) {
  try {
    const res = kind === 'album' ? await API.spotifyAlbum(id) : await API.spotifyPlaylist(id)
    playRows((res.data.songs || []).map(songRow), 0)
  } catch (err) {
    problem.value = reasonOf(err)
  }
}
// Spotify's artist pages are closed to an app like this: the artist is
// looked for in Dannify instead, where their songs play.
function findArtist(name) {
  router.push({ name: 'Search', params: { query: name } })
}
</script>

<style scoped>
.spx-hero {
  display: flex;
  align-items: flex-end;
  gap: 22px;
  padding-top: 40px;
  padding-bottom: 26px;
  background: linear-gradient(180deg, rgb(30 215 96 / 0.32), transparent);
}
.spx-avatar {
  display: grid;
  flex: none;
  place-items: center;
  width: 132px;
  height: 132px;
  overflow: hidden;
  border-radius: 999px;
  background: #1ed760;
  color: #000;
  box-shadow: 0 18px 40px rgb(0 0 0 / 0.35);
}
.spx-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.spx-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 700;
  color: rgb(var(--c-fg) / 0.85);
}
.spx-name {
  margin-top: 4px;
  font-size: clamp(2rem, 5vw, 3.4rem);
  font-weight: 900;
  line-height: 1.05;
  letter-spacing: -0.03em;
}
.spx-text {
  margin-top: 6px;
  font-size: 13.5px;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.spx-tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
  margin-bottom: 28px;
}
.spx-tile {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 14px 0 0;
  overflow: hidden;
  border-radius: 8px;
  background: rgb(var(--c-tint) / 0.06);
  transition: background-color 0.15s ease;
}
.spx-tile:hover {
  background: rgb(var(--c-tint) / 0.1);
}
.spx-tile-art {
  display: grid;
  flex: none;
  place-items: center;
  width: 64px;
  height: 64px;
  color: #fff;
}
.spx-tile-art.is-liked {
  background: linear-gradient(135deg, #4b2bd9, #8fd0c4);
}
.spx-tile-art.is-top {
  background: linear-gradient(135deg, #f59e0b, #b91c1c);
}
.spx-tile-art.is-recent {
  background: linear-gradient(135deg, #0ea5e9, #1e3a8a);
}
.spx-tile-title,
.spx-tile-sub {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.spx-tile-title {
  font-size: 14.5px;
  font-weight: 700;
}
.spx-tile-sub {
  font-size: 12.5px;
  color: rgb(var(--c-fg) / var(--fg-55));
}
.spx-problem {
  margin-bottom: 18px;
  font-size: 13.5px;
  color: rgb(var(--c-warn));
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
