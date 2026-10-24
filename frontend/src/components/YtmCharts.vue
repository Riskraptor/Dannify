<template>
  <!-- What YouTube Music says is played now where the listener is: its
       charts, the artists climbing them, and what is new. Nothing at all
       when it cannot be had (offline, signed out of nothing: it needs no
       sign-in). -->
  <div v-if="artists.length || playlists.length || albums.length" class="ytm-charts">
    <Shelf v-if="playlists.length" :title="t('charts.title', { country: countryName })">
      <MediaCard
        v-for="p in playlists"
        :key="p.browse_id"
        :item="{ name: p.name, cover: p.cover_url }"
        kind="playlist"
        :subtitle-text="countryName"
        @open="router.push({ name: 'ExplorePlaylist', params: { id: p.browse_id } })"
      />
    </Shelf>
    <Shelf v-if="artists.length" :title="t('charts.topArtists', { country: countryName })">
      <MediaCard
        v-for="a in artists"
        :key="a.browse_id"
        :item="{ name: a.name, cover: a.cover_url }"
        kind="artist"
        :subtitle-text="`#${a.rank} ${TREND[a.trend] || ''}${a.subscribers ? ` · ${t('charts.subscribers', { count: a.subscribers })}` : ''}`"
        @open="router.push({ name: 'ExploreArtist', params: { id: a.browse_id } })"
      />
    </Shelf>
    <Shelf v-if="releases && albums.length" :title="t('charts.newReleases')">
      <MediaCard
        v-for="al in albums"
        :key="al.browse_id"
        :item="{ name: al.name, cover: al.cover_url }"
        kind="album"
        :subtitle-text="[al.kind, al.artist].filter(Boolean).join(' · ')"
        @open="router.push({ name: 'ExploreAlbum', params: { id: al.browse_id } })"
      />
    </Shelf>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from '/src/i18n'
import { useCharts } from '/src/model/charts'
import Shelf from '/src/components/ui/Shelf.vue'
import MediaCard from '/src/components/MediaCard.vue'

// New releases are left out where YouTube Music's own feed already has them
// (Home).
defineProps({ releases: { type: Boolean, default: true } })

// Rising, falling, or where it was.
const TREND = { up: '▲', down: '▼', neutral: '' }

const { t } = useI18n()
const router = useRouter()
const charts = useCharts()
charts.load()

const playlists = computed(() => charts.data.value.playlists || [])
const artists = computed(() => charts.data.value.artists || [])
const albums = computed(() => charts.albums.value || [])
// "Kenya", or the world's charts called that, in the listener's language.
const countryName = computed(() => {
  const code = charts.data.value.code
  if (!code || code === 'ZZ') return t('charts.world')
  try {
    return new Intl.DisplayNames([document.documentElement.lang || 'en'], { type: 'region' }).of(code) || charts.data.value.country
  } catch {
    return charts.data.value.country || code
  }
})
</script>
