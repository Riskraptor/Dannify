<template>
  <div class="pb-12">
    <div v-if="state === 'loading'" class="view-pad space-y-2 pt-10">
      <div class="skeleton mb-8 h-48 w-48" />
      <div v-for="n in 6" :key="n" class="skeleton h-11" />
    </div>

    <!-- Every song of it deleted, or a link to an album that was never here. -->
    <EmptyState
      v-else-if="state === 'missing'"
      icon="ph:vinyl-record"
      :title="t('albums.notFound')"
      :text="t('albums.notFoundHint')"
    >
      <div class="flex flex-wrap justify-center gap-2">
        <router-link :to="{ name: 'Albums' }" class="btn btn-pill">{{ t('albums.title') }}</router-link>
        <button class="btn btn-pill" @click="searchOnline">
          <Icon icon="ph:globe" class="h-4 w-4" />
          {{ t('actions.searchOnline') }}
        </button>
      </div>
    </EmptyState>

    <EmptyState v-else-if="state === 'error'" icon="ph:warning" :title="t('library.failedLoad')">
      <button class="btn btn-pill" @click="load">{{ t('common.retry') }}</button>
    </EmptyState>

    <template v-else>
      <CollectionHero
        :title="album.name"
        :label="t('albums.label')"
        :cover="album.cover ? API.coverFileURL(album.cover, album.cover_v) : ''"
        kind="album"
        :playing="playingHere"
        @play="playAll"
      >
        <template #meta>
          <router-link :to="{ name: 'Artist', params: { name: album.artist } }" class="link font-semibold text-fg">
            {{ album.artist }}
          </router-link>
          <span class="opacity-50">•</span>
          <span>{{ t('explore.songCount', { count: rows.length }) }}</span>
          <template v-if="totalDuration">
            <span class="opacity-50">•</span>
            <span class="text-fg/60">{{ totalDuration }}</span>
          </template>
        </template>
        <template #actions>
          <button class="play-fab" :disabled="!rows.length" :title="t('explore.play')" :aria-label="t('explore.play')" @click="playAll">
            <Icon :icon="playingHere ? 'ph:pause-fill' : 'ph:play-fill'" class="h-5 w-5" />
          </button>
          <button
            class="icon-btn is-round h-10 w-10"
            :disabled="!rows.length"
            :title="t('actions.shuffle')"
            :aria-label="t('actions.shuffle')"
            @click="shuffleRows(rows)"
          >
            <Icon icon="ph:shuffle" class="h-6 w-6" />
          </button>
          <!-- What is saved of it may be a few songs: the rest is a click
               away, on YouTube Music. -->
          <button class="btn btn-pill" :title="t('albums.fullAlbumHint')" @click="openFull">
            <Icon icon="ph:vinyl-record" class="h-4 w-4" />
            {{ t('albums.fullAlbum') }}
          </button>
          <button class="icon-btn is-round h-10 w-10" :title="t('actions.more')" :aria-label="t('actions.more')" @click="onMore">
            <Icon icon="ph:dots-three-bold" class="h-6 w-6" />
          </button>
        </template>
      </CollectionHero>

      <div class="view-pad">
        <TrackTable
          :rows="rows"
          :sticky-offset="56"
          :show-cover="false"
          :show-album="false"
          use-track-numbers
          selectable
          selection-bar
          deletable
          :on-play="(i) => playRows(rows, i)"
        />
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, shallowRef, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { usePlayer } from '/src/model/player'
import { usePlaylists } from '/src/model/playlists'
import {
  localRow,
  playRows,
  shuffleRows,
  playNext,
  addToQueue,
  isRowCurrent,
  refreshRowDetails,
} from '/src/model/tracks'
import { openContextMenu } from '/src/model/contextMenu'
import { onLibraryChanged, onRefresh } from '/src/model/useRefresh'
import { useI18n } from '/src/i18n'
import CollectionHero from '/src/components/ui/CollectionHero.vue'
import TrackTable from '/src/components/ui/TrackTable.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'

// One album in the library: the songs of it that are saved, in the order
// the album has them, and the rest of it online.

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const player = usePlayer()
const playlists = usePlaylists()

const album = shallowRef(null)
const state = ref('loading') // loading | ready | missing | error
let asked = 0

async function load() {
  const artist = String(route.params.artist || '')
  const name = String(route.params.name || '')
  if (!artist || !name) return
  const mine = ++asked
  try {
    const res = await API.getAlbum(artist, name)
    if (mine !== asked) return
    album.value = res.data
    state.value = 'ready'
  } catch (err) {
    if (mine !== asked) return
    if (err && err.response && err.response.status === 404) {
      album.value = null
      state.value = 'missing'
    } else if (!album.value) {
      state.value = 'error'
    }
  }
}
// Each album keeps a page of its own (App.vue keys them by address), so these
// change only when one page is reused for another.
watch(() => [route.params.artist, route.params.name], load, { immediate: true })
// A song saved, repaired or deleted: the album as it is now.
onLibraryChanged(load)
onRefresh(load)

const rows = computed(() => (album.value ? (album.value.tracks || []).map(localRow) : []))

const totalDuration = computed(() => {
  const secs = rows.value.reduce((s, r) => s + (r.duration || 0), 0)
  if (!secs) return ''
  const h = Math.floor(secs / 3600)
  const m = Math.round((secs % 3600) / 60)
  return h ? t('common.hoursMinutes', { h, m }) : t('common.minutes', { m })
})

const currentHere = computed(() => rows.value.some((r) => isRowCurrent(r)))
const playingHere = computed(() => currentHere.value && player.isPlaying.value)
function playAll() {
  if (currentHere.value) return player.toggle()
  playRows(rows.value, 0)
}

function searchOnline() {
  const who = album.value ? album.value.artist : String(route.params.artist || '')
  const name = album.value ? album.value.name : String(route.params.name || '')
  router.push({ name: 'Search', params: { query: `${who} ${name}`.trim() } })
}
// Straight to it when a song of it knows which album it is on YouTube Music;
// a search for it when none does yet.
function openFull() {
  if (album.value && album.value.album_id) {
    router.push({ name: 'ExploreAlbum', params: { id: album.value.album_id } })
  } else {
    searchOnline()
  }
}

function onMore(e) {
  const list = rows.value
  openContextMenu(
    e,
    [
      { label: t('actions.playNext'), icon: 'ph:queue', action: () => playNext(list) },
      { label: t('actions.addToQueue'), icon: 'ph:list-plus', action: () => addToQueue(list) },
      { label: t('playlists.addTo'), icon: 'ph:playlist', action: () => playlists.pickPlaylist(list) },
      { divider: true },
      {
        label: t('actions.goToArtist'),
        icon: 'ph:user',
        action: () => router.push({ name: 'Artist', params: { name: album.value.artist } }),
      },
      { label: t('albums.fullAlbum'), icon: 'ph:vinyl-record', action: openFull },
      {
        label: t('details.refreshMany', { count: list.length }),
        icon: 'ph:arrows-clockwise',
        action: () => refreshRowDetails(list),
      },
    ],
    { anchor: true }
  )
}
</script>
