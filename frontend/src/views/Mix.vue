<template>
  <div class="pb-12">
    <EmptyState v-if="!meta" icon="ph:sparkle" :title="t('mixes.notFound')">
      <router-link :to="{ name: 'Home' }" class="btn btn-pill">{{ t('nav.home') }}</router-link>
    </EmptyState>

    <template v-else>
      <CollectionHero :title="t(meta.title)" :label="t('mixes.label')" :playing="playingHere" @play="playAll">
        <template #cover>
          <MixArt :covers="covers" :icon="meta.icon" :tone="meta.tone" :size="232" class="mix-hero-art" />
        </template>
        <template #meta>
          <span class="text-fg/80">{{ t(meta.text) }}</span>
          <template v-if="rows.length">
            <span class="opacity-50">•</span>
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
          <button class="btn btn-pill" :disabled="!rows.length || saving" @click="saveAsPlaylist">
            <Icon icon="ph:playlist" class="h-4 w-4" />
            {{ t('mixes.save') }}
          </button>
        </template>
      </CollectionHero>

      <EmptyState v-if="!rows.length" compact icon="ph:music-notes" :title="t('mixes.empty')" :text="t('mixes.emptyText')" />
      <div v-else class="view-pad">
        <TrackTable :rows="rows" :sticky-offset="56" :on-play="(i) => playRows(rows, i)" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import { usePlayer } from '/src/model/player'
import { usePlaylists } from '/src/model/playlists'
import { mixCovers, MIXES, useMixes } from '/src/model/mixes'
import { isRowCurrent, playRows, shuffleRows } from '/src/model/tracks'
import { onRefresh } from '/src/model/useRefresh'
import { useI18n } from '/src/i18n'
import CollectionHero from '/src/components/ui/CollectionHero.vue'
import MixArt from '/src/components/ui/MixArt.vue'
import TrackTable from '/src/components/ui/TrackTable.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'

// One mix (model/mixes.js): its songs, played or saved like a playlist's.

const { t } = useI18n()
const route = useRoute()
const player = usePlayer()
const playlists = usePlaylists()
const { mixes, refresh } = useMixes()
onRefresh(refresh)

const id = computed(() => String(route.params.id || ''))
const meta = computed(() => MIXES[id.value] || null)
const rows = computed(() => (mixes.value.find((m) => m.id === id.value) || { rows: [] }).rows)
const covers = computed(() => mixCovers(rows.value))

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

// A copy, as a playlist of its own: the mix goes on changing, the copy not.
const saving = ref(false)
async function saveAsPlaylist() {
  if (!rows.value.length || !meta.value) return
  saving.value = true
  try {
    // Asks for a name (the mix's, to start with) and says where it went.
    await playlists.createPlaylist(rows.value, { name: t(meta.value.title), open: false })
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.mix-hero-art {
  border-radius: 8px;
}
</style>
