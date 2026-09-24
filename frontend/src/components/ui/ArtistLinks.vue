<template>
  <span class="artist-links">
    <template v-for="(a, i) in artists" :key="i">
      <button
        v-if="a.id || a.local"
        type="button"
        class="link"
        @click.stop="openArtist(a)"
        @dblclick.stop
      >{{ a.name }}</button>
      <span v-else>{{ a.name }}</span>
      <span v-if="i < artists.length - 1">, </span>
    </template>
  </span>
</template>

<script setup>
import { openArtist } from '/src/model/tracks'

defineProps({
  artists: { type: Array, default: () => [] },
})
</script>
