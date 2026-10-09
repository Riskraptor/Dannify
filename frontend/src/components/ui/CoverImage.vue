<template>
  <span class="cover" :class="[round ? 'rounded-full' : radiusClass]">
    <img
      v-if="shown && !failed"
      :key="shown"
      :src="src1x"
      :srcset="srcset"
      alt=""
      :loading="eager ? 'eager' : 'lazy'"
      decoding="async"
      referrerpolicy="no-referrer"
      class="drag-none"
      :class="{ 'is-loaded': loaded }"
      @load="loaded = true"
      @error="onError"
    />
    <Icon v-if="!shown || failed || !loaded" :icon="fallbackIcon" class="cover-fallback" />
    <slot />
  </span>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { Icon } from '@iconify/vue'
import { libraryEpoch } from '/src/model/library'

const props = defineProps({
  src: { type: String, default: '' },
  // Tried when `src` fails: an artist's photo comes from the web, and offline
  // the cover of one of their saved songs is still there.
  fallback: { type: String, default: '' },
  kind: { type: String, default: 'track' }, // track | album | artist | playlist
  round: { type: Boolean, default: false },
  radius: { type: String, default: 'md' }, // none | sm | md | lg
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
const usingFallback = ref(false)
// What is drawn: the picture asked for, or the fallback once that failed.
const shown = computed(() => (usingFallback.value ? props.fallback : props.src || props.fallback))
// A new picture asked for: start again from it, not from the fallback.
watch(
  () => [props.src, props.fallback],
  () => {
    usingFallback.value = false
  }
)
// Start over only when what is drawn actually changes. This used to reset on
// any change at all: an artist's photo stayed the same while the album cover
// behind it moved (its song had just had its details refreshed), the photo
// was marked as not loaded, and since the browser had nothing new to load it
// never said otherwise. The picture sat hidden behind the placeholder icon.
watch(shown, () => {
  failed.value = false
  loaded.value = false
  retry.value = 0
})

function onError() {
  if (!usingFallback.value && props.fallback && props.src && props.fallback !== props.src) {
    usingFallback.value = true
    loaded.value = false
    return
  }
  failed.value = true
}

// A saved song's picture that failed is tried again whenever the library is
// read again. It failed because the song would not open, and the usual reason
// the library changes is that it has just been repaired. Pictures from the
// web are left alone: those fail for reasons a reload does not change.
const isLocal = computed(() => String(shown.value || '').startsWith('/cover'))
watch(libraryEpoch, () => {
  if (failed.value && isLocal.value) {
    failed.value = false
    loaded.value = false
    retry.value++
  }
})

const src1x = computed(() => {
  const url = atSize(shown.value, props.size)
  return retry.value && isLocal.value ? `${url}&r=${retry.value}` : url
})
const srcset = computed(() => {
  if (!props.size || src1x.value === shown.value || isLocal.value) return undefined
  return `${src1x.value} 1x, ${atSize(shown.value, props.size * 2)} 2x`
})

const radiusClass = computed(
  () => ({ none: 'rounded-none', sm: 'rounded', md: 'rounded-md', lg: 'rounded-lg' })[props.radius] || 'rounded-md'
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
  color: rgb(var(--c-fg) / var(--fg-35));
}
</style>
