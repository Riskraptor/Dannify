<template>
  <span class="cover" :class="[round ? 'rounded-full' : radiusClass]">
    <img
      v-if="src && !failed"
      :key="src"
      :src="src1x"
      :srcset="srcset"
      alt=""
      :loading="eager ? 'eager' : 'lazy'"
      decoding="async"
      referrerpolicy="no-referrer"
      class="drag-none"
      :class="{ 'is-loaded': loaded }"
      @load="loaded = true"
      @error="failed = true"
    />
    <Icon v-if="!src || failed || !loaded" :icon="fallbackIcon" class="cover-fallback" />
    <slot />
  </span>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { Icon } from '@iconify/vue'
import { libraryEpoch } from '/src/model/library'

const props = defineProps({
  src: { type: String, default: '' },
  kind: { type: String, default: 'track' }, // track | album | artist | playlist
  round: { type: Boolean, default: false },
  radius: { type: String, default: 'md' }, // sm | md | lg
  eager: { type: Boolean, default: false },
  // CSS px this cover renders at. Google's CDN resizes on demand, so asking
  // for the size we actually draw turns a 544px JPEG into a 40px one: the
  // single biggest win on a list of a few hundred rows.
  size: { type: Number, default: 0 },
})

// Only Google's image hosts understand these suffixes; everything else
// (local /cover URLs, other CDNs) is passed through untouched.
const RESIZABLE = /(googleusercontent\.com|ggpht\.com|ytimg\.com)/

function atSize(url, px) {
  if (!url || !px || !RESIZABLE.test(url)) return url
  if (/=w\d+-h\d+/.test(url)) return url.replace(/=w\d+-h\d+[^&]*$/, `=w${px}-h${px}-l90-rj`)
  if (/=s\d+/.test(url)) return url.replace(/=s\d+[^&]*$/, `=s${px}`)
  return url
}

const failed = ref(false)
const loaded = ref(false)
const retry = ref(0)
watch(
  () => props.src,
  () => {
    failed.value = false
    loaded.value = false
    retry.value = 0
  }
)

// A saved song's picture that failed is tried again whenever the library is
// read again. It failed because the song would not open, and the usual reason
// the library changes is that it has just been repaired. Pictures from the
// web are left alone: those fail for reasons a reload does not change.
const isLocal = computed(() => String(props.src || '').startsWith('/cover'))
watch(libraryEpoch, () => {
  if (failed.value && isLocal.value) {
    failed.value = false
    loaded.value = false
    retry.value++
  }
})

const src1x = computed(() => {
  const url = atSize(props.src, props.size)
  return retry.value && isLocal.value ? `${url}&r=${retry.value}` : url
})
const srcset = computed(() => {
  if (!props.size || src1x.value === props.src || isLocal.value) return undefined
  return `${src1x.value} 1x, ${atSize(props.src, props.size * 2)} 2x`
})

const radiusClass = computed(
  () => ({ sm: 'rounded', md: 'rounded-md', lg: 'rounded-lg' })[props.radius] || 'rounded-md'
)
const fallbackIcon = computed(
  () =>
    ({
      artist: 'ph:user',
      album: 'ph:vinyl-record',
      playlist: 'ph:playlist',
    })[props.kind] || 'ph:music-note'
)
</script>

<style scoped>
.cover {
  position: relative;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  overflow: hidden;
  background: rgb(var(--c-tint) / 0.08);
  isolation: isolate;
}
.cover img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  transition: opacity 0.2s ease;
}
.cover img.is-loaded {
  opacity: 1;
}
.cover-fallback {
  width: 40%;
  height: 40%;
  max-width: 48px;
  max-height: 48px;
  color: rgb(var(--c-fg) / 0.35);
}
</style>
