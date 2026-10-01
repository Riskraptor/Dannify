<template>
  <!-- Compact bar that sticks to the top once the hero scrolls away -->
  <div class="hero-sticky" :class="{ 'is-shown': compact }" aria-hidden="true">
    <div class="hero-sticky-bar">
      <div v-if="cover" class="hero-sticky-bg" :style="{ backgroundImage: `url('${cover}')` }" />
      <button
        v-if="playable"
        class="play-fab relative h-9 w-9"
        tabindex="-1"
        :title="t('actions.play')"
        @click="$emit('play')"
      >
        <Icon :icon="playing ? 'ph:pause-fill' : 'ph:play-fill'" class="h-4 w-4" />
      </button>
      <span class="relative truncate text-[17px] font-bold">{{ title }}</span>
    </div>
  </div>

  <section class="hero" :class="{ 'is-round': round }">
    <div v-if="cover" class="hero-bg" :style="{ backgroundImage: `url('${cover}')` }" aria-hidden="true" />
    <div class="hero-fade" aria-hidden="true" />
    <div class="hero-inner view-pad">
      <div class="hero-cover">
        <slot name="cover">
          <CoverImage :src="cover" :fallback="coverFallback" :kind="kind" :round="round" radius="md" class="h-full w-full" eager />
        </slot>
      </div>
      <div class="min-w-0 flex-1">
        <p class="hero-label">{{ label }}</p>
        <h1 class="hero-title" :class="titleSize" :title="title">{{ title }}</h1>
        <div class="hero-meta"><slot name="meta" /></div>
        <div v-if="$slots.sub" class="hero-sub"><slot name="sub" /></div>
      </div>
    </div>
  </section>

  <div ref="actions" class="hero-actions view-pad">
    <slot name="actions" />
  </div>
</template>

<script setup>
import { ref, computed, inject, onMounted, onBeforeUnmount, onActivated, onDeactivated } from 'vue'
import { Icon } from '@iconify/vue'
import CoverImage from './CoverImage.vue'
import { useI18n } from '/src/i18n'

const props = defineProps({
  title: { type: String, required: true },
  label: { type: String, default: '' },
  cover: { type: String, default: '' },
  // Drawn instead when `cover` cannot be loaded (an artist's web photo, offline).
  coverFallback: { type: String, default: '' },
  kind: { type: String, default: 'album' },
  round: { type: Boolean, default: false },
  playable: { type: Boolean, default: true },
  playing: { type: Boolean, default: false },
})
defineEmits(['play'])

const { t } = useI18n()
const scroller = inject('viewScroller', ref(null))
const actions = ref(null)
const compact = ref(false)

const titleSize = computed(() => {
  const n = props.title.length
  if (n > 42) return 'is-sm'
  if (n > 22) return 'is-md'
  return 'is-lg'
})

let io = null
function observe() {
  disconnect()
  if (!scroller.value || !actions.value) return
  io = new IntersectionObserver(
    ([entry]) => {
      compact.value = !entry.isIntersecting && entry.boundingClientRect.top < (entry.rootBounds ? entry.rootBounds.top + 60 : 60)
    },
    { root: scroller.value, rootMargin: '-56px 0px 0px 0px', threshold: 0 }
  )
  io.observe(actions.value)
}
function disconnect() {
  if (io) io.disconnect()
  io = null
}
onMounted(observe)
onActivated(observe)
onDeactivated(disconnect)
onBeforeUnmount(disconnect)
</script>

<style scoped>
.hero-sticky {
  position: sticky;
  top: 0;
  z-index: 20;
  height: 0;
}
.hero-sticky-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  height: 56px;
  padding: 0 24px;
  overflow: hidden;
  background: rgb(var(--c-raised));
  box-shadow: 0 6px 20px rgb(0 0 0 / 0.25);
  opacity: 0;
  transform: translateY(-8px);
  pointer-events: none;
  transition:
    opacity 0.18s ease,
    transform 0.2s var(--ease-out);
}
.hero-sticky-bg {
  position: absolute;
  inset: -60px;
  background-size: cover;
  background-position: center;
  filter: blur(40px) saturate(1.2) brightness(0.55);
  opacity: 0.9;
  /* A layer of its own: blurred once and then moved, instead of blurred
     again on every repaint while the page scrolls. */
  will-change: transform;
}
[data-mode='light'] .hero-sticky-bg {
  filter: blur(40px) saturate(1.1) brightness(1.1);
  opacity: 0.45;
}
.hero-sticky.is-shown .hero-sticky-bar {
  opacity: 1;
  transform: none;
  pointer-events: auto;
}
.hero {
  position: relative;
  overflow: hidden;
  padding-top: 40px;
}
.hero-bg {
  position: absolute;
  inset: -80px;
  background-size: cover;
  background-position: center;
  filter: blur(70px) saturate(1.35);
  opacity: 0.5;
  transform: scale(1.1);
  /* A layer of its own: blurred once and then moved, instead of blurred
     again on every repaint while the page scrolls. */
  will-change: transform;
}
[data-mode='light'] .hero-bg {
  opacity: 0.35;
}
.hero-fade {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to bottom,
    rgb(var(--c-panel) / 0.15) 0%,
    rgb(var(--c-panel) / 0.55) 55%,
    rgb(var(--c-panel)) 100%
  );
}
.hero-inner {
  position: relative;
  display: flex;
  align-items: flex-end;
  gap: 24px;
  padding-bottom: 24px;
}
.hero-cover {
  flex-shrink: 0;
  width: clamp(140px, 17vw, 220px);
  height: clamp(140px, 17vw, 220px);
  border-radius: 6px;
  box-shadow: 0 12px 40px rgb(0 0 0 / 0.45);
}
/* An artist's round photo: the shadow is round too, not a square behind it. */
.hero.is-round .hero-cover {
  border-radius: 50%;
}
.hero-label {
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.85);
}
.hero-title {
  font-weight: 800;
  line-height: 1.02;
  letter-spacing: -0.03em;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  padding-bottom: 0.08em;
}
.hero-title.is-lg {
  font-size: clamp(36px, 5.4vw, 72px);
}
.hero-title.is-md {
  font-size: clamp(30px, 3.8vw, 52px);
}
.hero-title.is-sm {
  font-size: clamp(24px, 2.6vw, 36px);
}
.hero-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  margin-top: 12px;
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.75);
}
.hero-sub {
  max-width: 720px;
  margin-top: 8px;
  font-size: 12.5px;
  line-height: 1.55;
  color: rgb(var(--c-fg) / 0.62);
}
.hero-actions {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding-top: 8px;
  padding-bottom: 20px;
}
@media (max-width: 700px) {
  .hero-inner {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
