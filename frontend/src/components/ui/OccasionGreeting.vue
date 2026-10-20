<template>
  <Teleport to="body">
    <transition name="og">
      <div v-if="open" class="og-layer" role="dialog" :aria-label="title" @mousedown.self="close">
        <Particles v-if="!still" :kind="occasion.effect" :count="occasion.effect === 'snow' ? 70 : 90" />
        <div ref="card" class="og-card" :class="`is-${occasion.id}`" tabindex="-1" @keydown.esc.prevent="close">
          <span class="og-mark"><Icon :icon="occasion.icon" class="h-8 w-8" /></span>
          <h2 class="og-title">{{ title }}</h2>
          <p class="og-text">{{ t(`occasion.${occasion.id}.text`) }}</p>
          <button class="btn-accent btn-pill press og-go px-6" @click="close">{{ t('occasion.go') }}</button>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { markGreeted, occasionOn, occasionYear, prefersStill, shouldGreet } from '/src/model/occasions'
import { rememberFocus } from '/src/model/focusTrap'
import { useI18n } from '/src/i18n'
import Particles from './Particles.vue'

// A greeting on a special day (model/occasions.js), the first time Dannify
// opens on it: a card, with snow or confetti across the window, that goes on
// its own after a few seconds. It waits its turn behind anything else being
// shown (the first-run tour, What's new), and does not come again that year.

const { t } = useI18n()
const occasion = occasionOn() || { id: '', effect: 'snow', icon: '' }
const still = prefersStill()
const open = ref(false)
const card = ref(null)
const title = computed(() => t(`occasion.${occasion.id}.title`, { year: occasionYear(occasion) }))
let timers = []
let giveBack = null

function busy() {
  return !!document.querySelector('[role="dialog"][aria-modal="true"], .ob')
}

function show(tries = 0) {
  if (!shouldGreet(occasion)) return
  if (busy()) {
    if (tries < 8) timers.push(setTimeout(() => show(tries + 1), 4000))
    return
  }
  markGreeted(occasion)
  giveBack = rememberFocus()
  open.value = true
  nextTick(() => card.value && card.value.focus())
  timers.push(setTimeout(close, 9000))
}

function close() {
  if (!open.value) return
  open.value = false
  const back = giveBack
  giveBack = null
  back && back()
}

onMounted(() => timers.push(setTimeout(show, 1600)))
onBeforeUnmount(() => timers.forEach(clearTimeout))
</script>

<style scoped>
.og-layer {
  position: fixed;
  inset: 0;
  z-index: 1150;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(0 0 0 / 0.42);
}
.og-card {
  position: relative;
  z-index: 1;
  display: grid;
  justify-items: center;
  gap: 10px;
  width: min(420px, 100%);
  padding: 34px 28px 26px;
  border-radius: 22px;
  text-align: center;
  outline: none;
  color: #fff;
  background: linear-gradient(160deg, #0f5132, #0b3d2e 55%, #7a1c1c);
  box-shadow: 0 30px 80px rgb(0 0 0 / 0.5);
}
.og-card.is-newyear {
  background: linear-gradient(160deg, #2b1a5e, #12123a 55%, #6b2a00);
}
.og-mark {
  display: grid;
  place-items: center;
  width: 68px;
  height: 68px;
  border-radius: 20px;
  background: rgb(255 255 255 / 0.14);
  animation: og-pop 0.6s cubic-bezier(0.2, 0.9, 0.2, 1.25) both;
}
.og-title {
  margin-top: 6px;
  font-size: 28px;
  font-weight: 900;
  letter-spacing: -0.02em;
}
.og-text {
  max-width: 32ch;
  font-size: 14.5px;
  line-height: 1.5;
  color: rgb(255 255 255 / 0.82);
}
.og-go {
  margin-top: 10px;
}
@keyframes og-pop {
  from {
    opacity: 0;
    transform: scale(0.6);
  }
}
.og-enter-active,
.og-leave-active {
  transition: opacity 0.35s ease;
}
.og-enter-active .og-card,
.og-leave-active .og-card {
  transition: transform 0.35s var(--ease-out);
}
.og-enter-from,
.og-leave-to {
  opacity: 0;
}
.og-enter-from .og-card {
  transform: translateY(16px) scale(0.96);
}
@media (prefers-reduced-motion: reduce) {
  .og-mark {
    animation: none;
  }
}
</style>
