<template>
  <!-- The song that is playing, large, and who made it: their picture, a few
       lines about them, and what comes on next. A music app's "now playing"
       view, beside lyrics and the queue. -->
  <div v-overlay-scroll class="npa">
    <div v-if="!cur" class="npa-empty">
      <Icon icon="ph:vinyl-record" class="mb-2 h-9 w-9 text-fg/25" />
      <p>{{ t('panel.aboutIdle') }}</p>
    </div>
    <template v-else>
      <CoverImage :src="cur.cover" radius="md" :size="320" class="npa-cover" eager />
      <div class="npa-head">
        <div class="min-w-0 flex-1">
          <p class="npa-title" :title="cur.title">{{ cur.title }}</p>
          <p class="npa-artist">
            <template v-for="(a, i) in row.artists" :key="a.name + i">
              <span v-if="i" class="opacity-60">, </span>
              <button class="npa-link" @click="openArtist(a)">{{ a.name }}</button>
            </template>
            <span v-if="!row.artists.length">{{ t('common.unknownArtist') }}</span>
          </p>
        </div>
        <button
          v-if="videoId"
          class="icon-btn is-round press shrink-0"
          :class="{ 'is-liked': liked }"
          :title="liked ? t('account.removeFromLiked') : t('account.addToLiked')"
          :aria-label="liked ? t('account.removeFromLiked') : t('account.addToLiked')"
          @click="account.toggleLike(row.raw)"
        >
          <Icon :icon="liked ? 'ph:heart-fill' : 'ph:heart'" class="h-5 w-5" />
        </button>
        <button class="icon-btn is-round press shrink-0" :title="t('actions.more')" :aria-label="t('actions.more')" @click="onMore">
          <Icon icon="ph:dots-three-bold" class="h-5 w-5" />
        </button>
      </div>

      <!-- About the artist -->
      <section v-if="artist" class="npa-card npa-about">
        <div
          class="npa-photo"
          :style="artist.cover_url ? { backgroundImage: `url('${artist.cover_url}')` } : null"
        >
          <span class="npa-photo-label">{{ t('panel.aboutArtist') }}</span>
        </div>
        <div class="npa-about-body">
          <p class="npa-about-name">{{ artist.name }}</p>
          <p v-if="artist.monthly_listeners || artist.subscribers" class="npa-about-meta">
            {{ artist.monthly_listeners || artist.subscribers }}
          </p>
          <p v-if="artist.description" class="npa-bio" :class="{ 'is-open': bioOpen }">
            {{ artist.description }}
          </p>
          <div class="mt-3 flex flex-wrap gap-2">
            <button v-if="artist.description && artist.description.length > 220" class="btn-ghost btn-pill h-8 px-3 text-xs" @click="bioOpen = !bioOpen">
              {{ bioOpen ? t('explore.showLess') : t('explore.readMore') }}
            </button>
            <button class="btn btn-pill h-8 px-3 text-xs" @click="openArtist(row.artists[0])">
              {{ t('actions.openArtist') }}
            </button>
          </div>
        </div>
      </section>
      <div v-else-if="artistLoading" class="npa-card npa-skeleton">
        <div class="skeleton h-40 w-full" />
        <div class="skeleton mt-3 h-4 w-1/2" />
        <div class="skeleton mt-2 h-3 w-3/4" />
      </div>

      <!-- Next in queue -->
      <section v-if="next" class="npa-card">
        <div class="npa-card-head">
          <p class="npa-card-title">{{ t('panel.nextInQueue') }}</p>
          <button class="npa-link text-xs font-semibold" @click="ui.openPanel('queue')">
            {{ t('panel.openQueue') }}
          </button>
        </div>
        <button class="npa-next" @click="player.playAt(next.queueIndex)">
          <CoverImage :src="next.cover" radius="sm" :size="44" class="npa-next-art" />
          <span class="min-w-0 flex-1 text-left">
            <span class="block truncate text-[14px] font-medium">{{ next.title }}</span>
            <span class="block truncate text-[12.5px] text-fg/55">{{ next.artistText }}</span>
          </span>
          <Icon icon="ph:play-fill" class="npa-next-play" />
        </button>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { useUi } from '/src/model/ui'
import { usePlayer } from '/src/model/player'
import { useAccount } from '/src/model/account'
import { queueRow, songVideoId, trackMenu } from '/src/model/tracks'
import { openContextMenu } from '/src/model/contextMenu'
import { useI18n } from '/src/i18n'
import CoverImage from '../ui/CoverImage.vue'

const { t } = useI18n()
const router = useRouter()
const ui = useUi()
const player = usePlayer()
const account = useAccount()

const cur = computed(() => player.currentTrack.value)
const row = computed(() => (cur.value ? queueRow(cur.value, player.currentIndex.value) : null))
const videoId = computed(() => (row.value ? songVideoId(row.value) : ''))
const liked = computed(() => account.isLiked(videoId.value))
const next = computed(() => {
  const i = player.upcoming.value[0]
  const list = player.playlist.value
  return i != null && list[i] ? queueRow(list[i], i) : null
})

// The artist's page online, once per artist while the app runs.
const pages = new Map()
const artist = ref(null)
const artistLoading = ref(false)
const bioOpen = ref(false)

async function loadArtist(a) {
  bioOpen.value = false
  if (!a || !a.name) {
    artist.value = null
    return
  }
  const key = a.id || `n:${a.name}`
  if (pages.has(key)) {
    artist.value = pages.get(key)
    return
  }
  artist.value = null
  artistLoading.value = true
  try {
    const res = a.id ? await API.exploreArtist(a.id) : await API.getArtistOnline(a.name)
    const page = res.data || null
    pages.set(key, page)
    if (row.value && row.value.artists[0] && (row.value.artists[0].id || `n:${row.value.artists[0].name}`) === key) {
      artist.value = page
    }
  } catch {
    pages.set(key, null)
  } finally {
    artistLoading.value = false
  }
}

watch(
  () => (row.value && row.value.artists[0] ? `${row.value.artists[0].id}|${row.value.artists[0].name}` : ''),
  () => loadArtist(row.value && row.value.artists[0]),
  { immediate: true }
)

function openArtist(a) {
  if (!a) return
  if (a.id) router.push({ name: 'ExploreArtist', params: { id: a.id } })
  else router.push({ name: 'Artist', params: { name: a.name } })
}

function onMore(e) {
  if (!row.value) return
  openContextMenu(e, trackMenu([row.value], { queue: true }), { anchor: true })
}
</script>

<style scoped>
.npa {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 16px 20px;
}
.npa-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 16px;
  text-align: center;
  font-size: 13px;
  color: rgb(var(--c-fg) / var(--fg-45));
}
.npa-cover {
  width: 100%;
  aspect-ratio: 1;
  height: auto;
  box-shadow: 0 10px 30px rgb(0 0 0 / 0.35);
}
.npa-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 16px 0 18px;
}
.npa-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-display, inherit);
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.015em;
}
.npa-artist {
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  color: rgb(var(--c-fg) / var(--fg-62));
}
.npa-link:hover {
  color: rgb(var(--c-fg));
  text-decoration: underline;
}
.npa-card {
  margin-bottom: 14px;
  overflow: hidden;
  border-radius: 10px;
  background: rgb(var(--c-tint) / 0.06);
}
.npa-skeleton {
  padding: 12px;
}
.npa-photo {
  position: relative;
  height: 200px;
  background-color: rgb(var(--c-tint) / 0.08);
  background-size: cover;
  background-position: center 25%;
}
.npa-photo::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgb(0 0 0 / 0.45), transparent 45%);
}
.npa-photo-label {
  position: absolute;
  top: 12px;
  left: 14px;
  z-index: 1;
  font-size: 14px;
  font-weight: 700;
  color: #fff;
}
.npa-about-body {
  padding: 14px 16px 16px;
}
.npa-about-name {
  font-size: 16px;
  font-weight: 700;
}
.npa-about-meta {
  margin-top: 2px;
  font-size: 13px;
  color: rgb(var(--c-fg) / var(--fg-55));
}
.npa-bio {
  display: -webkit-box;
  margin-top: 10px;
  overflow: hidden;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-line;
  color: rgb(var(--c-fg) / 0.7);
}
.npa-bio.is-open {
  display: block;
  -webkit-line-clamp: unset;
}
.npa-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 6px;
}
.npa-card-title {
  font-size: 14px;
  font-weight: 700;
}
.npa-next {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 8px 16px 14px;
}
.npa-next:hover {
  background: rgb(var(--c-tint) / 0.05);
}
.npa-next-art {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
}
.npa-next-play {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  color: rgb(var(--c-fg) / var(--fg-50));
}
.npa-next:hover .npa-next-play {
  color: rgb(var(--c-accent));
}
</style>
