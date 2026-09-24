<template>
  <div class="pb-12">
    <!-- Signed out: this view only exists because of the Google account -->
    <EmptyState
      v-if="!account.signedIn.value"
      icon="ph:heart"
      :title="t('account.likedSignedOutTitle')"
      :text="t('account.likedSignedOutText')"
    >
      <button class="btn-accent btn-pill" :disabled="account.busy.value" @click="account.signIn()">
        <Icon icon="ph:google-logo" class="h-4 w-4" />
        {{ t('account.connect') }}
      </button>
    </EmptyState>

    <template v-else>
      <CollectionHero
        :title="t('account.likedSongs')"
        :label="t('explore.playlist')"
        kind="playlist"
        :playing="playingHere"
        @play="playAll"
      >
        <template #cover>
          <div class="liked-cover">
            <Icon icon="ph:heart-fill" class="h-1/2 w-1/2" />
          </div>
        </template>
        <template #meta>
          <span v-if="account.displayName.value" class="font-semibold text-fg">
            {{ account.displayName.value }}
          </span>
          <span v-if="account.displayName.value" class="opacity-50">•</span>
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
          <button v-if="pendingCount > 0" class="btn btn-pill" @click="downloadRows(rows)">
            <Icon icon="ph:download-simple" class="h-4 w-4" />
            {{ pendingCount === rows.length ? t('explore.downloadAll') : t('explore.downloadRemaining', { count: pendingCount }) }}
          </button>
          <span v-else-if="rows.length" class="pill-accent h-7 px-3 text-xs">
            <Icon icon="ph:check-circle-fill" class="h-4 w-4" />
            {{ t('explore.allInLibrary') }}
          </span>
          <button
            class="icon-btn is-round h-10 w-10"
            :title="t('common.refresh')"
            :disabled="busy"
            @click="reload"
          >
            <Icon icon="ph:arrows-clockwise" class="h-6 w-6" :class="{ 'animate-spin': busy }" />
          </button>
        </template>
      </CollectionHero>

      <div v-if="busy && !rows.length" class="view-pad space-y-2">
        <div v-for="n in 10" :key="n" class="skeleton h-14" />
      </div>
      <EmptyState
        v-else-if="!rows.length"
        icon="ph:heart"
        :title="t('account.likedEmptyTitle')"
        :text="t('account.likedEmptyText')"
      />
      <div v-else class="view-pad">
        <TrackTable :rows="rows" :sticky-offset="56" :on-play="(i) => playRows(rows, i)" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Icon } from '@iconify/vue'
import { usePlayer } from '/src/model/player'
import { useAccount } from '/src/model/account'
import { useLibraryIndex } from '/src/model/libraryIndex'
import {
  songRow,
  playRows,
  shuffleRows,
  downloadRows,
  isRowCurrent,
  isRowDownloaded,
} from '/src/model/tracks'
import { onRefresh } from '/src/model/useRefresh'
import { useI18n } from '/src/i18n'
import CollectionHero from '/src/components/ui/CollectionHero.vue'
import TrackTable from '/src/components/ui/TrackTable.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'

const { t } = useI18n()
const player = usePlayer()
const account = useAccount()
const libIndex = useLibraryIndex()

const busy = ref(false)
const rows = computed(() => account.liked.value.map(songRow))

const pendingCount = computed(() => {
  void libIndex.byVideoId.value
  return rows.value.filter((r) => !isRowDownloaded(r)).length
})

const totalDuration = computed(() => {
  const secs = rows.value.reduce((s, r) => s + (r.duration || 0), 0)
  if (!secs) return ''
  const h = Math.floor(secs / 3600)
  const m = Math.round((secs % 3600) / 60)
  return h ? t('common.hoursMinutes', { h, m }) : t('common.minutes', { m })
})

// Playing from here, and playing at all, are different questions. Answering
// only the second meant pausing and pressing play again started from the top.
const currentHere = computed(() => rows.value.some((r) => isRowCurrent(r)))
const playingHere = computed(() => currentHere.value && player.isPlaying.value)

function playAll() {
  if (currentHere.value) return player.toggle()
  playRows(rows.value, 0)
}

async function reload() {
  busy.value = true
  try {
    await account.loadLiked(true)
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  if (account.signedIn.value && !account.likedLoaded.value) reload()
})
onRefresh(reload)
</script>

<style scoped>
.liked-cover {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  border-radius: 6px;
  color: #fff;
  background: linear-gradient(135deg, rgb(var(--c-accent)), rgb(var(--c-accent) / 0.45));
}
</style>
