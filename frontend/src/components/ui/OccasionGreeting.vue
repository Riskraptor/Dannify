<template>
  <Teleport to="body">
    <transition name="og">
      <div v-if="open" class="og-layer" role="dialog" :aria-label="words.title" @mousedown.self="close">
        <Particles :look="occasion.look" :count="occasion.look.motion === 'burst' ? 90 : 80" />
        <div
          ref="card"
          class="og-card"
          :style="{ '--c1': tone[0], '--c2': tone[1] }"
          tabindex="-1"
          @keydown.esc.prevent="close"
        >
          <span class="og-mark"><Icon :icon="occasion.icon" class="h-8 w-8" /></span>
          <h2 class="og-title">{{ words.title }}</h2>
          <p class="og-text">{{ words.text }}</p>
          <div class="og-actions">
            <button v-if="words.music" class="og-music press" @click="listen">
              <Icon icon="ph:music-notes-fill" class="h-4 w-4" />
              {{ t('occasion.listen') }}
            </button>
            <button class="btn-accent btn-pill press og-go px-6" @click="close">{{ t('occasion.go') }}</button>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { dayRoute, markGreeted, shouldGreet, toneList, wordsFor } from '/src/model/occasions'
import { rememberFocus } from '/src/model/focusTrap'
import { useI18n } from '/src/i18n'
import Particles from './Particles.vue'

// A greeting on a special day (model/occasions.js), the first time Dannify
// opens on it: a card in the day's colours, its weather across the window,
// and a way to the day's music. It goes on its own after a few seconds,
// waits its turn behind anything else being shown (the first-run tour,
// What's new), and does not come again for the same day.

const props = defineProps({
  occasion: { type: Object, required: true },
})

const { t, locale } = useI18n()
const router = useRouter()
const open = ref(false)
const card = ref(null)
const words = computed(() => wordsFor(props.occasion, t, locale.value))
// The card's colours: the day's own, darkened behind white words.
const tone = computed(() => {
  const strong = toneList((props.occasion.look && props.occasion.look.palette) || [])
  return [strong[0] || '#1ed760', strong[1] || strong[0] || '#3fa9f5']
})
let timers = []
let giveBack = null

function busy() {
  return !!document.querySelector('[role="dialog"][aria-modal="true"], .ob')
}

function show(tries = 0) {
  if (!shouldGreet(props.occasion)) return
  if (busy()) {
    if (tries < 8) timers.push(setTimeout(() => show(tries + 1), 4000))
    return
  }
  markGreeted(props.occasion)
  giveBack = rememberFocus()
  open.value = true
  nextTick(() => card.value && card.value.focus())
  timers.push(setTimeout(close, 11000))
}

function close() {
  if (!open.value) return
  open.value = false
  const back = giveBack
  giveBack = null
  back && back()
}

function listen() {
  close()
  router.push(dayRoute(props.occasion))
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
  width: min(440px, 100%);
  padding: 34px 28px 26px;
  border-radius: 22px;
  text-align: center;
  outline: none;
  color: #fff;
  background:
    radial-gradient(120% 80% at 50% 0%, color-mix(in srgb, var(--c1) 55%, transparent), transparent 70%),
    linear-gradient(160deg, color-mix(in srgb, var(--c1) 45%, #0b0b10), #101016 55%, color-mix(in srgb, var(--c2) 40%, #0b0b10));
  box-shadow:
    0 30px 80px rgb(0 0 0 / 0.5),
    inset 0 0 0 1px rgb(255 255 255 / 0.08);
}
.og-mark {
  display: grid;
  place-items: center;
  width: 68px;
  height: 68px;
  border-radius: 20px;
  background: rgb(255 255 255 / 0.14);
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 0.12);
  animation: og-pop 0.6s cubic-bezier(0.2, 0.9, 0.2, 1.25) both;
}
.og-title {
  margin-top: 6px;
  font-size: 28px;
  font-weight: 900;
  line-height: 1.15;
  letter-spacing: -0.02em;
  text-wrap: balance;
}
.og-text {
  max-width: 34ch;
  font-size: 14.5px;
  line-height: 1.5;
  color: rgb(255 255 255 / 0.84);
  text-wrap: pretty;
}
.og-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin-top: 12px;
}
.og-music {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 18px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 700;
  color: #fff;
  background: rgb(255 255 255 / 0.14);
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 0.18);
  transition: background 0.15s ease;
}
.og-music:hover {
  background: rgb(255 255 255 / 0.22);
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
  .og-enter-from .og-card {
    transform: none;
  }
}
</style>
