<template>
  <div class="lyrics-view" :class="{ 'is-large': large, 'is-compact': compact }">
    <LyricsSkeleton v-if="tools.loading.value" :large="large" />
    <LyricsLines v-else-if="tools.hasLines.value" :large="large" />
    <LyricsPlain v-else-if="tools.plain.value" :text="tools.plain.value" :large="large" />
    <LyricsEmpty v-else :compact="compact" />

    <LyricsOffsetBar v-if="tools.hasLines.value" />
  </div>
</template>

<script setup>
import { useLyricsTools } from '/src/model/lyrics/useLyricsTools'
import LyricsSkeleton from './LyricsSkeleton.vue'
import LyricsLines from './LyricsLines.vue'
import LyricsPlain from './LyricsPlain.vue'
import LyricsEmpty from './LyricsEmpty.vue'
import LyricsOffsetBar from './LyricsOffsetBar.vue'

// The lyrics of the song playing, in whichever state they are: on their way,
// in time, words only, missing, or out of reach while offline.
defineProps({
  // Big, left-aligned typography for the full Now Playing view.
  large: { type: Boolean, default: false },
  // The mini player: no big buttons; editing happens in the full window.
  compact: { type: Boolean, default: false },
})

const tools = useLyricsTools()
</script>

<style scoped>
.lyrics-view {
  position: relative;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
</style>
