<template>
  <div
    class="mcard"
    role="button"
    tabindex="0"
    :title="item.name"
    @click="$emit('open')"
    @keydown.enter.prevent="$emit('open')"
    @keydown.space.self.prevent="$emit('open')"
    @contextmenu="onMenu"
    @mouseenter="warmPageOnHover(kind, item.browse_id)"
    @mouseleave="cancelPageWarm()"
    @focus="warmPageOnHover(kind, item.browse_id)"
  >
    <div class="mcard-art" :class="{ 'is-round': round }">
      <CoverImage
        :src="item.cover_url || item.cover || ''"
        :fallback="item.fallback || ''"
        :kind="kind"
        :round="round"
        radius="md"
        :size="220"
        class="h-full w-full"
      />
      <button
        v-if="playable"
        class="mcard-play"
        tabindex="-1"
        :title="t('actions.play')"
        :aria-label="t('actions.play')"
        @click.stop="$emit('play')"
      >
        <Icon icon="ph:play-fill" class="h-5 w-5" />
      </button>
    </div>
    <p class="mcard-title">{{ item.name }}</p>
    <p class="mcard-sub">{{ subtitle }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import CoverImage from './ui/CoverImage.vue'
import { openContextMenu } from '/src/model/contextMenu'
import { warmPageOnHover, cancelPageWarm } from '/src/model/prefetch'
import { useI18n } from '/src/i18n'
import { useArtistLinks } from '/src/model/artistLinks'

const props = defineProps({
  item: { type: Object, required: true },
  kind: { type: String, default: 'album' }, // artist | album | playlist
  playable: { type: Boolean, default: false },
  subtitleText: { type: String, default: '' },
  menu: { type: Function, default: null }, // () => context menu items
})
const emit = defineEmits(['open', 'play'])

const { t } = useI18n()
const round = computed(() => props.kind === 'artist')
const { links } = useArtistLinks()
const libraryArtistIds = computed(() => new Set(Object.values(links.value).map((l) => l && l.id).filter(Boolean)))

const subtitle = computed(() => {
  if (props.subtitleText) return props.subtitleText
  const it = props.item
  if (props.kind === 'artist') {
    // Two artists can share a name (two "Mavokali" in a search): which one
    // the library's songs are by, their followers, and whether they have any
    // songs at all are what tell them apart.
    const parts = []
    if (it.browse_id && libraryArtistIds.value.has(it.browse_id)) parts.push(t('explore.yourArtist'))
    if (it.subscribers) parts.push(`${it.subscribers} ${t('explore.subscribers')}`)
    if (it.namesake && it.has_songs === false) parts.push(t('explore.videosOnly'))
    return parts.join(' · ') || t('explore.artist')
  }
  if (props.kind === 'playlist') {
    return it.item_count
      ? `${it.author ? it.author + ' · ' : ''}${it.item_count} ${t('explore.tracks')}`
      : it.author || t('explore.playlist')
  }
  const parts = []
  if (it.year) parts.push(it.year)
  if (it.artists && it.artists.length) parts.push(it.artists.join(', '))
  return parts.join(' · ') || it.album_type || t('explore.album')
})

function onMenu(e) {
  const custom = props.menu ? props.menu() : null
  const items = custom || [
    props.playable && { label: t('actions.play'), icon: 'ph:play', action: () => emit('play') },
    { label: t('actions.open'), icon: 'ph:arrow-square-out', action: () => emit('open') },
  ]
  openContextMenu(e, items)
}
</script>

<style scoped>
.mcard {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 10px;
  border-radius: 8px;
  outline: none;
  transition: background-color 0.15s ease;
}
.mcard:hover,
.mcard:focus-visible {
  background: rgb(var(--c-tint) / 0.06);
}
.mcard:focus-visible {
  box-shadow: inset 0 0 0 2px rgb(var(--c-accent) / 0.7);
}
.mcard-art {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  margin-bottom: 10px;
  border-radius: 6px;
  box-shadow: 0 6px 20px rgb(0 0 0 / 0.25);
}
.mcard-art.is-round {
  border-radius: 999px;
}
.mcard-play {
  position: absolute;
  right: 8px;
  bottom: 8px;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 999px;
  background: rgb(var(--c-accent));
  color: rgb(var(--c-accent-fg));
  box-shadow: 0 8px 18px rgb(0 0 0 / 0.35);
  opacity: 0;
  transform: translateY(8px);
  transition:
    opacity 0.18s ease,
    transform 0.22s var(--ease-out);
}
.mcard:hover .mcard-play {
  opacity: 1;
  transform: none;
}
.mcard-play:hover {
  transform: scale(1.05) !important;
}
.mcard-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
  font-weight: 600;
}
.mcard-sub {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-top: 2px;
  font-size: 13.5px;
  line-height: 1.35;
  color: rgb(var(--c-fg) / var(--fg-58));
}
</style>
