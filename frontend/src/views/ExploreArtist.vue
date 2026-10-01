<template>
  <div class="pb-12">
    <div v-if="showSkeleton && !artist" class="view-pad pt-10">
      <div class="flex items-end gap-6">
        <div class="skeleton h-48 w-48 rounded-full" />
        <div class="flex-1 space-y-3">
          <div class="skeleton h-4 w-24 rounded" />
          <div class="skeleton h-12 w-1/2 rounded" />
          <div class="skeleton h-4 w-1/3 rounded" />
        </div>
      </div>
      <div class="mt-10">
        <div v-for="n in 6" :key="n" class="row-ghost">
          <span class="skeleton row-ghost-cover" />
          <span class="row-ghost-lines">
            <span class="skeleton h-[11px] rounded" :style="ghostWidth(n)" />
            <span class="skeleton h-[9px] w-[34%] rounded" />
          </span>
        </div>
      </div>
    </div>

    <EmptyState
      v-else-if="!artist && !loading"
      :icon="failure === 'offline' ? 'ph:wifi-slash' : failure === 'error' ? 'ph:warning-circle' : 'ph:user'"
      :title="failure === 'offline' ? t('net.offlineTitle') : failure === 'error' ? t('net.loadFailed') : t('explore.notFound')"
      :text="failure === 'offline' ? t('net.offlinePage') : ''"
    >
      <div class="flex gap-2">
        <button v-if="failure" class="btn btn-pill" @click="load">{{ t('common.retry') }}</button>
        <button class="btn btn-pill" @click="router.back()">{{ t('explore.back') }}</button>
      </div>
    </EmptyState>

    <!-- Loading, but not for long enough to have earned a skeleton yet.
         Without this the v-else below matched while the data was still null
         and the render threw reading a name off nothing. -->
    <div v-else-if="!artist" class="view-pad pt-10" aria-busy="true" />

    <template v-else>
      <CollectionHero
        :title="artist.name"
        :label="t('explore.artist')"
        :cover="artist.cover_url"
        kind="artist"
        round
        :playing="playingHere"
        @play="playTop"
      >
        <template #meta>
          <span v-if="artist.subscribers">{{ artist.subscribers }} {{ t('explore.subscribers') }}</span>
        </template>
        <template v-if="artist.description" #sub>
          <!-- Artist bios run long; clamp with a real expander so the whole
               text is reachable instead of hiding behind a tooltip. -->
          <p class="selectable bio" :class="{ 'is-open': bioOpen }">
            {{ artist.description }}
          </p>
          <button v-if="bioIsLong" class="bio-more" @click="bioOpen = !bioOpen">
            {{ bioOpen ? t('explore.showLess') : t('explore.readMore') }}
            <Icon :icon="bioOpen ? 'ph:caret-up-bold' : 'ph:caret-down-bold'" class="h-3 w-3" />
          </button>
        </template>
        <template #actions>
          <button class="play-fab" :disabled="!songRows.length" :title="t('explore.play')" @click="playTop">
            <Icon :icon="playingHere ? 'ph:pause-fill' : 'ph:play-fill'" class="h-5 w-5" />
          </button>
          <button
            class="icon-btn is-round h-10 w-10"
            :disabled="!songRows.length"
            :title="t('actions.shuffle')"
            @click="shuffleRows(songRows)"
          >
            <Icon icon="ph:shuffle" class="h-6 w-6" />
          </button>
          <button
            v-if="chosen.length"
            class="btn-accent btn-pill press"
            @click="downloadChosen"
          >
            <Icon icon="ph:download-simple" class="h-4 w-4" />
            {{ t('explore.downloadChosen', { count: chosen.length }) }}
          </button>
        </template>
      </CollectionHero>

      <section v-if="songRows.length" class="view-pad mb-10">
        <h2 class="section-title">{{ t('explore.topSongs') }}</h2>
        <TrackTable
          :rows="visibleRows"
          :sticky-offset="56"
          selectable
          :on-play="(i) => playRows(songRows, i)"
          @selection-change="chosen = $event"
        />
        <button
          v-if="songRows.length > songLimit"
          class="more-btn"
          @click="songLimit += 25"
        >
          {{ t('explore.showMore') }}
        </button>
        <button v-else-if="songRows.length > 10" class="more-btn" @click="songLimit = 10">
          {{ t('explore.showLess') }}
        </button>
      </section>

      <div class="shelves">
        <Shelf v-if="artist.albums.length" :title="t('explore.albums')" wrap>
          <MediaCard
            v-for="al in artist.albums"
            :key="al.browse_id"
            :item="al"
            kind="album"
            @open="ex.openAlbum(al.browse_id)"
          />
        </Shelf>
        <Shelf v-if="artist.singles.length" :title="t('explore.singles')" wrap>
          <MediaCard
            v-for="al in artist.singles"
            :key="al.browse_id"
            :item="al"
            kind="album"
            @open="ex.openAlbum(al.browse_id)"
          />
        </Shelf>
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
import { useExplore } from '/src/model/explore'
import { usePlayer } from '/src/model/player'
import { songRow, playRows, shuffleRows, downloadRows, isRowCurrent } from '/src/model/tracks'
import { onRefresh } from '/src/model/useRefresh'
import { useI18n } from '/src/i18n'
import CollectionHero from '/src/components/ui/CollectionHero.vue'
import TrackTable from '/src/components/ui/TrackTable.vue'
import Shelf from '/src/components/ui/Shelf.vue'
import MediaCard from '/src/components/MediaCard.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'
import { failedForNetwork, whenOnline } from '/src/model/connectivity'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const ex = useExplore()
const player = usePlayer()

const artist = ref(null)
const loading = ref(false)
// Whatever is ticked in the list. There used to be one button that grabbed a
// fixed bundle of "popular" tracks, which is rarely the set anybody wanted.
const chosen = ref([])

function downloadChosen() {
  if (chosen.value.length) downloadRows(chosen.value)
}
// Fast pages should not flash a skeleton on their way in.
const showSkeleton = useDeferred(loading)

// A column of identical bars is what makes a skeleton look fake. Fixed
// widths, so nothing reflows while it waits.
const GHOST_WIDTHS = ['72%', '54%', '83%', '61%', '77%', '48%']
function ghostWidth(n) {
  return { width: GHOST_WIDTHS[(n - 1) % GHOST_WIDTHS.length] }
}

const songLimit = ref(10)
const bioOpen = ref(false)
// Two clamped lines is roughly 180 characters at the hero's width.
const bioIsLong = computed(() => (artist.value?.description || '').length > 180)

const songRows = computed(() => (artist.value ? artist.value.songs.map(songRow) : []))
const visibleRows = computed(() => songRows.value.slice(0, songLimit.value))

const currentHere = computed(() => songRows.value.some((r) => isRowCurrent(r)))
const playingHere = computed(() => currentHere.value && player.isPlaying.value)

function playTop() {
  // Resume where it was, rather than starting from the first track again.
  if (currentHere.value) return player.toggle()
  playRows(songRows.value, 0)
}

// '' (none), 'missing', 'offline' or 'error': "Nothing found" was said for
// all of them, offline included.
const failure = ref('')

async function load() {
  const id = route.params.id
  if (!id) return
  loading.value = true
  try {
    const res = await API.exploreArtist(id)
    artist.value = res.data
    failure.value = ''
  } catch (e) {
    artist.value = null
    const status = e && e.response && e.response.status
    if (status === 404) failure.value = 'missing'
    else if (await failedForNetwork(e)) {
      failure.value = 'offline'
      whenOnline(() => {
        if (!artist.value) load()
      })
    } else failure.value = 'error'
  } finally {
    loading.value = false
  }
}

onMounted(load)
onRefresh(load)
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
  text-decoration: underline;
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
