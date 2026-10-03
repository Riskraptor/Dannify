<template>
  <!-- A playlist's picture: its first four songs' covers in a square, or the
       first one alone while it has fewer, or a plain mark while it is empty. -->
  <span class="pa" :class="[`is-${radius}`, { 'is-grid': covers4.length === 4 }]">
    <template v-if="covers4.length === 4">
      <CoverImage
        v-for="(c, i) in covers4"
        :key="i"
        :src="c"
        kind="playlist"
        radius="none"
        :size="size ? Math.ceil(size / 2) : 0"
        class="pa-cell"
        :eager="eager"
      />
    </template>
    <CoverImage
      v-else-if="urls.length"
      :src="urls[0]"
      kind="playlist"
      radius="none"
      :size="size"
      class="pa-one"
      :eager="eager"
    />
    <span v-else class="pa-empty">
      <Icon icon="ph:playlist" class="pa-icon" />
    </span>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import CoverImage from './CoverImage.vue'
import { coverURL } from '/src/model/playlists'

const props = defineProps({
  covers: { type: Array, default: () => [] },
  size: { type: Number, default: 0 },
  radius: { type: String, default: 'md' }, // sm | md
  eager: { type: Boolean, default: false },
})

const urls = computed(() => props.covers.map(coverURL).filter(Boolean))
const covers4 = computed(() => (urls.value.length >= 4 ? urls.value.slice(0, 4) : []))
</script>

<style scoped>
.pa {
  position: relative;
  display: grid;
  overflow: hidden;
  background: rgb(var(--c-tint) / 0.08);
}
.pa.is-sm {
  border-radius: 4px;
}
.pa.is-md {
  border-radius: 6px;
}
.pa.is-grid {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}
.pa-cell,
.pa-one {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
}
.pa-empty {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, rgb(var(--c-accent) / 0.35), rgb(var(--c-accent) / 0.08));
  color: rgb(var(--c-fg) / 0.75);
}
.pa-icon {
  width: 45%;
  height: 45%;
}
</style>
