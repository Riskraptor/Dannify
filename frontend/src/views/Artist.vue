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

    <EmptyState
      v-else-if="!artist"
      icon="ph:user"
      :title="t('artist.notFound')"
    >
      <button class="btn btn-pill" @click="router.push({ name: 'Artists' })">{{ t('artist.back') }}</button>
    </EmptyState>

    <template v-else>
      <CollectionHero
        :title="artist.name"
        :label="t('artist.label')"
        :cover="coverUrl"
        kind="artist"
        round
        :playing="playingHere"
        @play="playAll"
      >
        <template #meta>
          <span>{{ t('artists.trackCount', { count: artist.count }) }}</span>
          <span class="opacity-50">•</span>
          <span>{{ t('artist.albumCount', { count: artist.albums.length }) }}</span>
        </template>
        <template #actions>
          <button class="play-fab" :title="t('artists.playAll')" @click="playAll">
            <Icon :icon="playingHere ? 'ph:pause-fill' : 'ph:play-fill'" class="h-5 w-5" />
          </button>
          <button class="icon-btn is-round h-10 w-10" :title="t('artist.shuffle')" @click="shuffleRows(allRows)">
            <Icon icon="ph:shuffle" class="h-6 w-6" />
          </button>
          <button class="btn btn-pill" @click="router.push({ name: 'Search', params: { query: artist.name } })">
            <Icon icon="ph:globe" class="h-4 w-4" />
            {{ t('actions.searchOnline') }}
          </button>
        </template>
      </CollectionHero>

      <section v-for="album in albums" :key="album.name" class="view-pad mb-8">
        <div class="album-head">
          <CoverImage :src="API.coverFileURL(album.cover)" kind="album" radius="sm" class="h-12 w-12" />
          <div class="min-w-0">
            <h2 class="truncate text-[17px] font-bold">{{ album.name === 'Singles' ? t('artist.singles') : album.name }}</h2>
            <p class="text-xs text-fg/50">{{ t('artists.trackCount', { count: album.rows.length }) }}</p>
          </div>
        </div>
        <TrackTable
          :rows="album.rows"
          :header="false"
          :show-cover="false"
          :show-album="false"
          use-track-numbers
          deletable
          :on-play="(i) => playFromAlbum(album, i)"
        />
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { usePlayer } from '/src/model/player'
import { localRow, playRows, shuffleRows } from '/src/model/tracks'
import { onRefresh, onLibraryChanged } from '/src/model/useRefresh'
import { useI18n } from '/src/i18n'
import CollectionHero from '/src/components/ui/CollectionHero.vue'
import TrackTable from '/src/components/ui/TrackTable.vue'
import CoverImage from '/src/components/ui/CoverImage.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const player = usePlayer()

const artist = ref(null)
const loading = ref(false)

const coverUrl = computed(() =>
  artist.value && artist.value.cover ? API.coverFileURL(artist.value.cover) : ''
)

const albums = computed(() =>
  artist.value
    ? artist.value.albums.map((al) => ({ ...al, rows: al.tracks.map(localRow) }))
    : []
)
const allRows = computed(() => albums.value.flatMap((al) => al.rows))

const playingHere = computed(() => {
  const cur = player.currentTrack.value
  return (
    !!cur &&
    player.isPlaying.value &&
    allRows.value.some((r) => r.file && r.file === cur.file)
  )
})

function playAll() {
  if (playingHere.value) return player.toggle()
  player.setShuffle(false)
  playRows(allRows.value, 0)
}

function playFromAlbum(album, i) {
  const target = album.rows[i]
  playRows(allRows.value, Math.max(0, allRows.value.indexOf(target)))
}

async function load() {
  const name = route.params.name
  if (!name) return
  loading.value = true
  try {
    const res = await API.getArtist(name)
    artist.value = res.data
  } catch {
    artist.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)
onRefresh(load)
onLibraryChanged(() => setTimeout(load, 800))
</script>

<style scoped>
.album-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  padding: 0 12px;
}
</style>
