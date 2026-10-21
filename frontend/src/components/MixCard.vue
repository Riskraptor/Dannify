<template>
  <div
    class="mcard"
    role="button"
    tabindex="0"
    :title="title"
    @click="$emit('open')"
    @keydown.enter.prevent="$emit('open')"
    @keydown.space.self.prevent="$emit('open')"
  >
    <div class="mcard-art">
      <MixArt :covers="covers" :icon="icon" :tone="tone" :title="title" />
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
    <p class="mcard-title">{{ title }}</p>
    <p class="mcard-sub">{{ subtitle }}</p>
  </div>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import MixArt from './ui/MixArt.vue'
import { useI18n } from '/src/i18n'

// A mix on a shelf (model/mixes.js), or "Your Soundtrack": the same card
// as an album's, with a picture made from what is in it.

defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  covers: { type: Array, default: () => [] },
  icon: { type: String, default: 'ph:sparkle' },
  tone: { type: String, default: 'mix-recent' },
  playable: { type: Boolean, default: true },
})
defineEmits(['open', 'play'])

const { t } = useI18n()
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
  overflow: hidden;
  border-radius: 6px;
  box-shadow: 0 6px 20px rgb(0 0 0 / 0.25);
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
