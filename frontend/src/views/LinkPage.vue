<template>
  <div class="pb-12">
    <div v-if="showSkeleton && !page" class="view-pad pt-10">
      <div class="flex items-end gap-6">
        <div class="skeleton h-48 w-48 rounded-lg" />
        <div class="flex-1 space-y-3">
          <div class="skeleton h-4 w-24 rounded" />
          <div class="skeleton h-12 w-1/2 rounded" />
          <div class="skeleton h-4 w-1/3 rounded" />
        </div>
      </div>
    </div>

    <div v-else-if="failure === 'offline'" class="view-pad pt-8">
      <OfflineCard />
    </div>
    <EmptyState
      v-else-if="failure"
      :icon="failure === 'notMusic' ? 'ph:microphone' : 'ph:link-break'"
      :title="failure === 'notMusic' ? t('links.notMusic') : t('links.loadFailed')"
      :text="failure === 'notMusic' ? '' : t('links.loadFailedText')"
    >
      <div class="flex gap-2">
        <button v-if="failure === 'error'" class="btn btn-pill" @click="load">{{ t('common.retry') }}</button>
        <button class="btn btn-pill" @click="router.back()">{{ t('explore.back') }}</button>
      </div>
    </EmptyState>

    <div v-else-if="!page" class="view-pad pt-10" aria-busy="true" />

    <template v-else>
      <CollectionHero
        :title="page.title || t('links.untitled')"
        :label="t(`links.label.${page.kind}`)"
        :cover="page.cover"
        :kind="page.kind === 'artist' ? 'artist' : page.kind === 'playlist' ? 'playlist' : 'album'"
        :round="page.kind === 'artist'"
        :playing="playingHere"
        @play="playAll"
      >
        <template #meta>
          <span class="spotify-mark" :title="t('links.fromSpotify')">
            <Icon icon="ph:spotify-logo-fill" class="h-4 w-4" />
          </span>
          <span v-if="page.subtitle" class="font-semibold text-fg">{{ page.subtitle }}</span>
          <template v-if="page.year">
            <span class="opacity-50">•</span>
            <span>{{ page.year }}</span>
          </template>
          <span v-if="page.subtitle || page.year" class="opacity-50">•</span>
          <span>{{ t('explore.songCount', { count: page.total }) }}</span>
          <template v-if="totalDuration">
            <span class="opacity-50">•</span>
            <span class="text-fg/60">{{ totalDuration }}</span>
          </template>
        </template>
        <template #sub>
          <!-- Each song is paired with the same one on YouTube Music, which is
               what plays and what is saved: a few at a time, shown as it goes. -->
          <p class="match-line" :class="{ 'is-done': !matching }" aria-live="polite">
            <span v-if="matching" class="spinner h-3.5 w-3.5" />
            <Icon v-else icon="ph:check-circle-fill" class="h-4 w-4" />
            <template v-if="matching">{{ t('links.finding', { done: tried, total: page.total }) }}</template>
            <template v-else-if="missing.length">{{ t('links.foundSome', { found: page.total - missing.length, total: page.total }) }}</template>
            <template v-else>{{ t('links.allFound') }}</template>
          </p>
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
          <button v-if="page.total > 1" class="btn btn-pill" :disabled="busy !== ''" @click="saveAsPlaylist">
            <span v-if="busy === 'playlist'" class="spinner h-4 w-4" />
            <Icon v-else icon="ph:playlist" class="h-4 w-4" />
            {{ t('links.saveAsPlaylist') }}
          </button>
          <button v-if="pendingCount > 0" class="btn btn-pill" :disabled="busy !== ''" @click="saveAll">
            <span v-if="busy === 'download'" class="spinner h-4 w-4" />
            <Icon v-else icon="ph:download-simple" class="h-4 w-4" />
            {{ page.total === 1 ? t('links.saveSong') : t('explore.downloadAll') }}
          </button>
          <span v-else-if="rows.length && !matching" class="pill-accent h-7 px-3 text-xs">
            <Icon icon="ph:arrow-circle-down-fill" class="h-4 w-4" />
            {{ t('explore.allInLibrary') }}
          </span>
          <button class="icon-btn is-round h-10 w-10" :title="t('actions.more')" :aria-label="t('actions.more')" @click="openMore">
            <Icon icon="ph:dots-three-bold" class="h-6 w-6" />
          </button>
        </template>
      </CollectionHero>

      <div class="view-pad">
        <TrackTable
          :rows="rows"
          show-cover
          :show-album="page.kind !== 'album'"
          :sticky-offset="56"
          selectable
          selection-bar
          :on-play="(i) => playRows(rows, i)"
        />

        <section v-if="missing.length" class="missing">
          <h2 class="missing-title">{{ t('links.notFoundTitle') }}</h2>
          <p class="missing-text">{{ t('links.notFoundText') }}</p>
          <ul class="missing-list">
            <li v-for="m in missing" :key="m.song_id" dir="auto">
              <b>{{ m.name }}</b>
              <span>{{ m.artist }}</span>
            </li>
          </ul>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
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
import { usePlaylists } from '/src/model/playlists'
import { openContextMenu } from '/src/model/contextMenu'
import { copyText } from '/src/model/clipboard'
import { toast } from '/src/model/toast'
import { desktop } from '/src/desktop/bridge'
import { failedForNetwork, whenOnline } from '/src/model/connectivity'
import { useI18n } from '/src/i18n'
import CollectionHero from '/src/components/ui/CollectionHero.vue'
import TrackTable from '/src/components/ui/TrackTable.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'
import OfflineCard from '/src/components/ui/OfflineCard.vue'

// The songs a pasted Spotify link holds (a song, an album, a playlist, an
// artist's top songs), each paired with the same song on YouTube Music: to
// play, save, or keep as a playlist of one's own.

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const player = usePlayer()
const libIndex = useLibraryIndex()
const playlists = usePlaylists()

const BATCH = 25

const page = ref(null)
const loading = ref(false)
const showSkeleton = useDeferred(loading)
// '' | 'offline' | 'notMusic' | 'error'
const failure = ref('')
// Per song, in order: undefined not tried yet, null not found, else the
// YouTube Music song.
const matches = ref([])
const matching = ref(false)
const busy = ref('')
let token = 0
let matchingDone = Promise.resolve()

const tried = computed(() => matches.value.filter((m) => m !== undefined).length)
const missing = computed(() =>
  page.value ? page.value.tracks.filter((_, i) => matches.value[i] === null) : []
)

const rows = computed(() => {
  const p = page.value
  if (!p) return []
  const out = []
  p.tracks.forEach((track, i) => {
    const found = matches.value[i]
    if (found === null) return
    // Found: the YouTube Music song, with Spotify's picture where it has none.
    // Not tried yet: the Spotify song, which still plays (the server finds it).
    out.push(songRow(found ? { ...found, cover_url: found.cover_url || track.cover_url } : track))
  })
  return out
})

const pendingCount = computed(() => {
  void libIndex.byVideoId.value
  return rows.value.filter((r) => !isRowDownloaded(r) && !isRowDownloading(r)).length
})

const totalDuration = computed(() => {
  const secs = page.value ? page.value.duration : 0
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

async function matchAll(mine) {
  const tracks = page.value.tracks
  matching.value = true
  try {
    for (let start = 0; start < tracks.length; start += BATCH) {
      const slice = tracks.slice(start, start + BATCH)
      let found
      try {
        found = ((await API.matchLinkSongs(slice)).data || {}).matches || []
      } catch {
        // YouTube Music did not answer: these stay as Spotify songs, which
        // still play.
        if (mine !== token) return
        continue
      }
      if (mine !== token) return
      const next = matches.value.slice()
      slice.forEach((_, j) => {
        next[start + j] = found[j] || null
      })
      matches.value = next
    }
  } finally {
    if (mine === token) matching.value = false
  }
}

async function load() {
  const url = String(route.query.url || '')
  if (!url) return
  const mine = ++token
  loading.value = true
  failure.value = ''
  page.value = null
  matches.value = []
  try {
    const res = await API.spotifyLink(url)
    if (mine !== token) return
    page.value = res.data
    matches.value = new Array(res.data.tracks.length)
    matchingDone = matchAll(mine)
  } catch (err) {
    if (mine !== token) return
    const status = err && err.response && err.response.status
    if (status === 422) failure.value = 'notMusic'
    else if (await failedForNetwork(err)) {
      failure.value = 'offline'
      whenOnline(() => {
        if (mine === token && failure.value) load()
      })
    } else failure.value = 'error'
  } finally {
    if (mine === token) loading.value = false
  }
}

// Saved as a playlist, or downloaded, with every song paired first: what
// goes in is what YouTube Music has.
async function whenMatched(kind, run) {
  busy.value = kind
  try {
    await matchingDone
    await run(rows.value.filter((r) => r.raw && r.raw.video_id))
  } finally {
    busy.value = ''
  }
}
function saveAsPlaylist() {
  return whenMatched('playlist', (list) => playlists.createPlaylist(list, { name: page.value.title || '' }))
}
function saveAll() {
  return whenMatched('download', (list) => downloadRows(list.filter((r) => !isRowDownloaded(r) && !isRowDownloading(r))))
}

function openMore(e) {
  const url = page.value.url
  openContextMenu(
    e,
    [
      rows.value.length && { label: t('actions.playNext'), icon: 'ph:queue', action: () => playNext(rows.value) },
      rows.value.length && { label: t('actions.addToQueue'), icon: 'ph:list-plus', action: () => addToQueue(rows.value) },
      rows.value.length && {
        label: t('playlists.addTo'),
        icon: 'ph:list-plus',
        action: () => whenMatched('playlist', (list) => playlists.pickPlaylist(list)),
      },
      { divider: true },
      { label: t('links.openInSpotify'), icon: 'ph:spotify-logo', action: () => desktop.openExternal(url) },
      {
        label: t('actions.copyLink'),
        icon: 'ph:link',
        action: async () => {
          if (await copyText(url)) toast(t('actions.linkCopied'), { icon: 'ph:link' })
        },
      },
    ],
    { anchor: true }
  )
}

watch(
  () => route.query.url,
  () => {
    if (route.name === 'Link') load()
  },
  { immediate: true }
)
onBeforeUnmount(() => {
  token++
})
</script>

<style scoped>
.spotify-mark {
  display: inline-grid;
  place-items: center;
  color: #1ed760;
}
.match-line {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-top: 4px;
  font-size: 12.5px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.7);
}
.match-line.is-done svg {
  color: rgb(var(--c-accent));
}
.missing {
  margin-top: 28px;
  padding: 16px 18px;
  border-radius: 14px;
  background: rgb(var(--c-tint) / 0.04);
}
.missing-title {
  font-size: 15px;
  font-weight: 750;
}
.missing-text {
  margin-top: 2px;
  font-size: 12.5px;
  color: rgb(var(--c-fg) / var(--fg-60, 0.62));
}
.missing-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 6px 18px;
  margin-top: 10px;
  font-size: 12.5px;
}
.missing-list li {
  display: flex;
  min-width: 0;
  flex-direction: column;
}
.missing-list b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 650;
}
.missing-list span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgb(var(--c-fg) / var(--fg-55, 0.55));
}
</style>
