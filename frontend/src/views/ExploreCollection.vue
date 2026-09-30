<template>
  <div class="pb-12">
    <div v-if="showSkeleton && !album" class="view-pad pt-10">
      <div class="flex items-end gap-6">
        <div class="skeleton h-48 w-48 rounded-lg" />
        <div class="flex-1 space-y-3">
          <div class="skeleton h-4 w-24 rounded" />
          <div class="skeleton h-12 w-1/2 rounded" />
          <div class="skeleton h-4 w-1/3 rounded" />
        </div>
      </div>
      <div class="mt-10">
        <div v-for="n in 8" :key="n" class="row-ghost">
          <span class="skeleton row-ghost-cover" />
          <span class="row-ghost-lines">
            <span class="skeleton h-[11px] rounded" :style="ghostWidth(n)" />
            <span class="skeleton h-[9px] w-[34%] rounded" />
          </span>
        </div>
      </div>
    </div>

    <EmptyState
      v-else-if="!album && !loading"
      :icon="isPlaylist ? 'ph:playlist' : 'ph:vinyl-record'"
      :title="t('explore.notFound')"
    >
      <button class="btn btn-pill" @click="router.back()">{{ t('explore.back') }}</button>
    </EmptyState>

    <!-- Loading, but not for long enough to have earned a skeleton yet.
         Without this the v-else below matched while the data was still null
         and the render threw reading a name off nothing. -->
    <div v-else-if="!album" class="view-pad pt-10" aria-busy="true" />

    <template v-else>
      <CollectionHero
        :title="album.name"
        :label="label"
        :cover="album.cover_url"
        :kind="isPlaylist ? 'playlist' : 'album'"
        :playing="playingHere"
        @play="playAll"
      >
        <template #meta>
          <template v-if="isPlaylist">
            <span v-if="album.author" class="font-semibold text-fg">{{ album.author }}</span>
          </template>
          <template v-else>
            <ArtistLinks :artists="artistLinks" class="font-semibold text-fg" />
            <template v-if="album.year">
              <span class="opacity-50">•</span>
              <span>{{ album.year }}</span>
            </template>
          </template>
          <span class="opacity-50">•</span>
          <span>{{ t('explore.songCount', { count: rows.length }) }}</span>
          <template v-if="totalDuration">
            <span class="opacity-50">•</span>
            <span class="text-fg/60">{{ totalDuration }}</span>
          </template>
        </template>
        <template #actions>
          <button class="play-fab" :disabled="!rows.length" :title="t('explore.play')" @click="playAll">
            <Icon :icon="playingHere ? 'ph:pause-fill' : 'ph:play-fill'" class="h-5 w-5" />
          </button>
          <button
            class="icon-btn is-round h-10 w-10"
            :disabled="!rows.length"
            :title="t('actions.shuffle')"
            @click="shuffleRows(rows)"
          >
            <Icon icon="ph:shuffle" class="h-6 w-6" />
          </button>
          <button
            v-if="pendingCount > 0"
            class="btn btn-pill"
            @click="downloadRows(rows)"
          >
            <Icon icon="ph:download-simple" class="h-4 w-4" />
            {{ pendingCount === rows.length ? t('explore.downloadAll') : t('explore.downloadRemaining', { count: pendingCount }) }}
          </button>
          <span v-else-if="rows.length" class="pill-accent h-7 px-3 text-xs">
            <Icon icon="ph:check-circle-fill" class="h-4 w-4" />
            {{ t('explore.allInLibrary') }}
          </span>
          <button class="icon-btn is-round h-10 w-10" :title="t('actions.more')" @click="openMore">
            <Icon icon="ph:dots-three-bold" class="h-6 w-6" />
          </button>
        </template>
      </CollectionHero>

      <div class="view-pad">
        <TrackTable
          :rows="rows"
          :show-cover="isPlaylist"
          :show-album="isPlaylist"
          :sticky-offset="56"
          :on-play="(i) => playRows(rows, i)"
        />
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { useDeferred } from '/src/model/deferred'
import { usePlayer } from '/src/model/player'
import { useLibraryIndex } from '/src/model/libraryIndex'
import {
  songRow,
  playRows,
  shuffleRows,
  downloadRows,
  playNext,
  addToQueue,
  isRowCurrent,
  isRowDownloaded,
  isRowDownloading,
} from '/src/model/tracks'
import { openContextMenu } from '/src/model/contextMenu'
import { copyText } from '/src/model/clipboard'
import { toast } from '/src/model/toast'
import { onRefresh } from '/src/model/useRefresh'
import { useI18n } from '/src/i18n'
import CollectionHero from '/src/components/ui/CollectionHero.vue'
import TrackTable from '/src/components/ui/TrackTable.vue'
import ArtistLinks from '/src/components/ui/ArtistLinks.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'

const props = defineProps({ mode: { type: String, default: 'album' } })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const player = usePlayer()
const libIndex = useLibraryIndex()

const album = ref(null)
const loading = ref(false)
// Fast pages should not flash a skeleton on their way in.
const showSkeleton = useDeferred(loading)

// A column of identical bars is what makes a skeleton look fake. Fixed
// widths, so nothing reflows while it waits.
const GHOST_WIDTHS = ['72%', '54%', '83%', '61%', '77%', '48%']
function ghostWidth(n) {
  return { width: GHOST_WIDTHS[(n - 1) % GHOST_WIDTHS.length] }
}


const isPlaylist = computed(() => props.mode === 'playlist')
const label = computed(() => {
  if (isPlaylist.value) return t('explore.playlist')
  const type = album.value && album.value.album_type
  return type && typeof type === 'string' ? type : t('explore.album')
})

const artistLinks = computed(() => {
  if (!album.value) return []
  const ids = album.value.artist_ids
  if (Array.isArray(ids) && ids.length) return ids.map((a) => ({ name: a.name, id: a.id }))
  return (album.value.artists || []).map((n) => ({ name: n, id: '' }))
})

const rows = computed(() => {
  if (!album.value) return []
  const base = album.value
  return base.tracks.map((s) => {
    // Album tracks often lack their own cover/album fields: inherit them.
    const song = isPlaylist.value
      ? s
      : {
          ...s,
          cover_url: s.cover_url || base.cover_url,
          album_name: s.album_name || base.name,
          album_id: s.album_id || route.params.id,
        }
    return songRow(song)
  })
})

// Songs neither saved nor already on their way. Counting the ones on their
// way kept "Download all" up during the batch, and pressing it again sent
// every one of them a second time.
const pendingCount = computed(() => {
  void libIndex.byVideoId.value
  return rows.value.filter((r) => !isRowDownloaded(r) && !isRowDownloading(r)).length
})

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
  // Resume where it was, rather than starting the collection again.
  if (currentHere.value) return player.toggle()
  playRows(rows.value, 0)
}

function openMore(e) {
  const link = isPlaylist.value
    ? `https://music.youtube.com/playlist?list=${String(route.params.id).replace(/^VL/, '')}`
    : `https://music.youtube.com/browse/${route.params.id}`
  openContextMenu(
    e,
    [
      { label: t('actions.playNext'), icon: 'ph:queue', action: () => playNext(rows.value) },
      { label: t('actions.addToQueue'), icon: 'ph:list-plus', action: () => addToQueue(rows.value) },
      { divider: true },
      pendingCount.value > 0 && {
        label: t('explore.downloadAll'),
        icon: 'ph:download-simple',
        action: () => downloadRows(rows.value),
      },
      {
        label: t('actions.copyLink'),
        icon: 'ph:link',
        action: async () => {
          if (await copyText(link)) toast(t('actions.linkCopied'), { icon: 'ph:link' })
        },
      },
    ],
    { anchor: true }
  )
}

async function load() {
  const id = route.params.id
  if (!id) return
  loading.value = true
  try {
    const res = isPlaylist.value ? await API.explorePlaylist(id) : await API.exploreAlbum(id)
    album.value = res.data
  } catch {
    album.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)
onRefresh(load)
</script>
