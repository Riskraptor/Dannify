<template>
  <div class="pb-12">
    <div v-if="state === 'loading'" class="grid place-items-center pt-24">
      <span class="spinner h-8 w-8" />
    </div>

    <EmptyState v-else-if="state === 'error'" icon="ph:spotify-logo" :title="t('spotify.loadFailed')" :text="t(errorKey(reason))">
      <button class="btn btn-pill" @click="load">{{ t('common.retry') }}</button>
      <router-link
        v-if="['expired', 'not_configured', 'not_allowed'].includes(reason)"
        :to="{ name: 'Settings', query: { pane: 'accounts' } }"
        class="btn btn-pill"
      >
        {{ t('spotify.openSettings') }}
      </router-link>
    </EmptyState>

    <template v-else>
      <CollectionHero :title="title" :label="label" :cover="cover" :playing="playingHere" @play="playAll">
        <template v-if="!cover" #cover>
          <div class="spl-art" :class="`is-${kind}`">
            <Icon :icon="ART_ICON[kind] || 'ph:spotify-logo-fill'" class="h-20 w-20" />
          </div>
        </template>
        <template #meta>
          <span v-if="byline" class="font-semibold text-fg/90">{{ byline }}</span>
          <template v-if="rows.length">
            <span v-if="byline" class="opacity-50">•</span>
            <span>{{ t('explore.songCount', { count: rows.length }) }}</span>
          </template>
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
          <button class="btn btn-pill" :disabled="!rows.length || copying" @click="copyToDannify">
            <span v-if="copying" class="spinner h-4 w-4" />
            <Icon v-else icon="ph:playlist" class="h-4 w-4" />
            {{ copying ? t('spotify.copying', { done: progress.done, total: progress.total }) : t('spotify.copy') }}
          </button>
          <button class="btn btn-pill" :disabled="!rows.length" @click="downloadRows(rows)">
            <Icon icon="ph:download-simple" class="h-4 w-4" />
            {{ t('spotify.saveOffline') }}
          </button>
          <!-- Top songs: over the last month, half a year, or all time. -->
          <div v-if="kind === 'top'" class="seg ml-auto" role="radiogroup" :aria-label="t('spotify.span')">
            <button
              v-for="sp in SPANS"
              :key="sp.id"
              class="seg-item"
              role="radio"
              :aria-checked="span === sp.id"
              :class="{ 'is-active': span === sp.id }"
              @click="router.replace({ name: 'SpotifyList', params: { kind: 'top', id: sp.id } })"
            >
              {{ t(sp.label) }}
            </button>
          </div>
        </template>
      </CollectionHero>

      <EmptyState v-if="!rows.length" compact icon="ph:music-notes" :title="t('spotify.emptyList')" />
      <div v-else class="view-pad">
        <TrackTable :rows="rows" :sticky-offset="56" :on-play="(i) => playRows(rows, i)" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { usePlayer } from '/src/model/player'
import { errorKey, importSpotify, reasonOf } from '/src/model/spotify'
import { downloadRows, isRowCurrent, playRows, shuffleRows, songRow } from '/src/model/tracks'
import { onRefresh } from '/src/model/useRefresh'
import { useI18n } from '/src/i18n'
import CollectionHero from '/src/components/ui/CollectionHero.vue'
import TrackTable from '/src/components/ui/TrackTable.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'

// One of the person's Spotify lists: a playlist, an album, Liked Songs, top
// songs or what they played lately. Its songs play through YouTube Music,
// and the list can be copied into Dannify or saved for offline.

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const player = usePlayer()

const ART_ICON = { liked: 'ph:heart-fill', top: 'ph:trophy-fill', recent: 'ph:clock-counter-clockwise-bold' }
const SPANS = [
  { id: 'short_term', label: 'spotify.spanMonth' },
  { id: 'medium_term', label: 'spotify.spanHalfYear' },
  { id: 'long_term', label: 'spotify.spanAllTime' },
]

const kind = computed(() => String(route.params.kind || 'liked'))
const ident = computed(() => String(route.params.id || ''))
const span = computed(() => (SPANS.some((s) => s.id === ident.value) ? ident.value : 'medium_term'))

const data = shallowRef(null)
const state = ref('loading')
const reason = ref('')
let asked = 0

async function load() {
  const mine = ++asked
  state.value = 'loading'
  try {
    let res
    if (kind.value === 'playlist') res = (await API.spotifyPlaylist(ident.value)).data
    else if (kind.value === 'album') res = (await API.spotifyAlbum(ident.value)).data
    else if (kind.value === 'liked') res = { songs: (await API.spotifyLiked()).data.songs }
    else if (kind.value === 'recent') res = { songs: (await API.spotifyRecent()).data.songs }
    else res = { songs: (await API.spotifyTop('tracks', span.value)).data.items }
    if (mine !== asked) return
    data.value = res
    state.value = 'ready'
  } catch (err) {
    if (mine !== asked) return
    reason.value = reasonOf(err)
    state.value = 'error'
  }
}
watch([kind, ident], load, { immediate: true })
onRefresh(load)
// Signed in or out elsewhere (Settings): asked again.
const onChanged = () => load()
onMounted(() => window.addEventListener('dannify:spotify-changed', onChanged))
onBeforeUnmount(() => window.removeEventListener('dannify:spotify-changed', onChanged))

const rows = computed(() => ((data.value && data.value.songs) || []).map(songRow))
const cover = computed(() => (data.value && data.value.image) || '')
const title = computed(() => {
  if (kind.value === 'liked') return t('spotify.liked')
  if (kind.value === 'top') return t('spotify.topSongs')
  if (kind.value === 'recent') return t('spotify.recent')
  return (data.value && data.value.name) || ''
})
const label = computed(() => {
  if (kind.value === 'album') return t('spotify.labelAlbum')
  if (kind.value === 'playlist') return t('spotify.labelPlaylist')
  return t('spotify.title')
})
const byline = computed(() => {
  const d = data.value || {}
  if (kind.value === 'album') return [d.artist, d.year].filter(Boolean).join(' • ')
  if (kind.value === 'playlist') return d.owner || ''
  return ''
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
  if (currentHere.value) return player.toggle()
  playRows(rows.value, 0)
}

// Copied into a Dannify playlist: each song matched on YouTube Music.
const copying = ref(false)
const progress = reactive({ done: 0, total: 0 })
async function copyToDannify() {
  copying.value = true
  progress.done = 0
  progress.total = rows.value.length
  try {
    const id = await importSpotify(kind.value, kind.value === 'top' ? span.value : ident.value, title.value, (now) => {
      progress.done = now.done
      progress.total = now.total
    })
    if (id) router.push({ name: 'Playlist', params: { id } })
  } finally {
    copying.value = false
  }
}
</script>

<style scoped>
.spl-art {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  border-radius: 8px;
  color: #fff;
  background: linear-gradient(135deg, #1ed760, #0b6b33);
  box-shadow: 0 18px 40px rgb(0 0 0 / 0.35);
}
.spl-art.is-liked {
  background: linear-gradient(135deg, #4b2bd9, #8fd0c4);
}
.spl-art.is-top {
  background: linear-gradient(135deg, #f59e0b, #b91c1c);
}
.spl-art.is-recent {
  background: linear-gradient(135deg, #0ea5e9, #1e3a8a);
}
</style>
