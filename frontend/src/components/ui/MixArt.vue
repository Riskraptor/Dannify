<template>
  <div class="mix-art" :class="tone" aria-hidden="true">
    <div class="mix-grid" :class="{ 'is-single': shown.length < 4 }">
      <CoverImage v-for="(cover, i) in shown" :key="cover + i" :src="cover" radius="none" :size="size / 2" class="mix-tile" />
    </div>
    <div class="mix-wash" />
    <div class="mix-label">
      <Icon :icon="icon" class="mix-icon" />
      <span v-if="title" class="mix-name">{{ title }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import CoverImage from './CoverImage.vue'

// A mix's picture: the covers of the songs it opens with, under a wash of its
// own colour, with its name across the bottom. Made from what is in it, so it
// changes when the mix does.

const props = defineProps({
  covers: { type: Array, default: () => [] },
  icon: { type: String, default: 'ph:sparkle' },
  // mix-repeat | mix-top | mix-forgotten | mix-recent | mix-now | mix-year
  tone: { type: String, default: 'mix-recent' },
  title: { type: String, default: '' },
  // The size it is drawn at, for the covers' small copies.
  size: { type: Number, default: 220 },
})

// Four different pictures when there are four; one when there are not.
const unique = computed(() => [...new Set(props.covers.filter(Boolean))])
const shown = computed(() => (unique.value.length >= 4 ? unique.value.slice(0, 4) : unique.value.slice(0, 1)))
</script>

<style scoped>
.mix-art {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: inherit;
  background: var(--mix-a);
  isolation: isolate;
}
.mix-grid {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}
.mix-grid.is-single {
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}
.mix-tile {
  width: 100%;
  height: 100%;
}
.mix-wash {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(to top, var(--mix-b) 0%, transparent 62%),
    linear-gradient(135deg, var(--mix-a) 0%, transparent 70%);
  mix-blend-mode: normal;
  opacity: 0.92;
}
.mix-label {
  position: absolute;
  left: 12%;
  right: 10%;
  bottom: 10%;
  display: grid;
  gap: 4%;
  color: #fff;
  text-shadow: 0 1px 12px rgb(0 0 0 / 0.35);
}
.mix-icon {
  width: 22%;
  height: auto;
  max-width: 40px;
  min-width: 16px;
}
.mix-name {
  font-size: clamp(0.85rem, 9cqw, 1.6rem);
  font-weight: 800;
  line-height: 1.05;
  letter-spacing: -0.02em;
}
.mix-art {
  container-type: inline-size;
}

.mix-repeat {
  --mix-a: rgb(30 215 96 / 0.85);
  --mix-b: rgb(6 66 46 / 0.95);
}
.mix-top {
  --mix-a: rgb(255 176 32 / 0.85);
  --mix-b: rgb(120 46 8 / 0.95);
}
.mix-forgotten {
  --mix-a: rgb(244 88 140 / 0.85);
  --mix-b: rgb(78 24 96 / 0.95);
}
.mix-recent {
  --mix-a: rgb(64 156 255 / 0.85);
  --mix-b: rgb(14 40 110 / 0.95);
}
.mix-now {
  --mix-a: rgb(255 122 69 / 0.88);
  --mix-b: rgb(52 34 120 / 0.95);
}
.mix-year {
  --mix-a: rgb(168 85 247 / 0.9);
  --mix-b: rgb(236 72 153 / 0.95);
}
</style>
