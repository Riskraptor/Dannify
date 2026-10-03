<template>
  <div class="mood pb-12" :style="{ '--mood': colour }">
    <div class="mood-band" aria-hidden="true" />
    <header class="view-pad mood-head">
      <div class="mood-tile">
        <Icon :icon="glyph" class="h-14 w-14" />
      </div>
      <div class="min-w-0">
        <p class="eyebrow mb-1">{{ t('browse.eyebrow') }}</p>
        <h1 class="mood-title">{{ title }}</h1>
        <p v-if="playlists.length" class="mt-2 text-sm text-fg/60">
          {{ t('browse.playlistCount', { count: playlists.length }) }}
        </p>
      </div>
    </header>

    <div v-if="loading" class="view-pad grid grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-4 pt-2">
      <div v-for="n in 12" :key="n" class="skeleton aspect-square" />
    </div>
    <EmptyState
      v-else-if="failed"
      icon="ph:wifi-slash"
      :title="t('browse.failedTitle')"
      :text="t('browse.failedText')"
    >
      <button class="btn btn-pill" @click="load">{{ t('common.retry') }}</button>
    </EmptyState>
    <div v-else class="view-pad mood-grid">
      <MediaCard
        v-for="p in playlists"
        :key="p.browse_id"
        :item="{ name: p.name, cover: p.cover_url }"
        kind="playlist"
        :subtitle-text="p.description"
        @open="router.push({ name: 'ExplorePlaylist', params: { id: p.browse_id } })"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { moodColour, moodGlyph } from '/src/model/moods'
import { useI18n } from '/src/i18n'
import MediaCard from '/src/components/MediaCard.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const params = computed(() => String(route.params.params || ''))
const title = computed(() => String(route.query.title || ''))
const colour = computed(() => moodColour(title.value))
const glyph = computed(() => moodGlyph(title.value))
const playlists = ref([])
const loading = ref(true)
const failed = ref(false)

async function load() {
  const p = params.value
  if (!p) return
  loading.value = true
  failed.value = false
  try {
    const res = await API.getMoodPlaylists(p)
    if (p !== params.value) return
    playlists.value = (res.data && res.data.playlists) || []
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}
watch(params, load, { immediate: true })
</script>

<style scoped>
.mood {
  position: relative;
  isolation: isolate;
}
.mood-band {
  position: absolute;
  inset: 0 0 auto 0;
  z-index: -1;
  height: 340px;
  background: linear-gradient(180deg, color-mix(in srgb, var(--mood) 55%, transparent), transparent);
  pointer-events: none;
}
.mood-head {
  display: flex;
  align-items: flex-end;
  gap: 22px;
  padding-top: 34px;
  padding-bottom: 26px;
}
.mood-tile {
  display: grid;
  place-items: center;
  width: 132px;
  height: 132px;
  flex-shrink: 0;
  border-radius: 8px;
  color: #fff;
  background: var(--mood);
  box-shadow: 0 10px 28px rgb(0 0 0 / 0.35);
}
.mood-title {
  font-size: 44px;
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.025em;
}
.mood-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 8px 4px;
}
</style>
