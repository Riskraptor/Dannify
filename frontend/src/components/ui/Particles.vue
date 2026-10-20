<template>
  <!-- Snow or confetti, drawn by the compositor alone: each piece is moved,
       never repainted. Nothing at all for reduced motion. -->
  <div class="ptl" :class="[`is-${kind}`, { 'is-contained': contain }]" :style="{ '--fall': fall }" aria-hidden="true">
    <i v-for="p in pieces" :key="p.id" class="ptl-p" :style="p.style" />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // snow | confetti
  kind: { type: String, default: 'snow' },
  count: { type: Number, default: 40 },
  // Within the nearest positioned parent instead of over the whole window.
  contain: { type: Boolean, default: false },
  // How far a piece falls: the window's height, or the parent's.
  fall: { type: String, default: '110vh' },
})

const CONFETTI = ['#1ed760', '#ffd166', '#ef476f', '#3fa9f5', '#c77dff', '#ff9f1c']

const pieces = computed(() =>
  Array.from({ length: props.count }, (_, id) => {
    const snow = props.kind === 'snow'
    const size = snow ? 3 + Math.random() * 5 : 0
    const style = {
      '--x': `${(Math.random() * 100).toFixed(1)}%`,
      '--drift': `${(Math.random() * 80 - 40).toFixed(0)}px`,
      '--d': `${(snow ? 7 + Math.random() * 7 : 4 + Math.random() * 4).toFixed(1)}s`,
      '--delay': `${(-Math.random() * 12).toFixed(1)}s`,
      '--o': (snow ? 0.45 + Math.random() * 0.45 : 0.95).toFixed(2),
    }
    if (snow) {
      style['--s'] = `${size.toFixed(1)}px`
    } else {
      style['--c'] = CONFETTI[id % CONFETTI.length]
      style['--r'] = `${Math.round(360 + Math.random() * 720)}deg`
    }
    return { id, style }
  })
)
</script>

<style scoped>
.ptl {
  position: fixed;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: 0;
}
.ptl.is-contained {
  position: absolute;
}
.ptl-p {
  position: absolute;
  top: -16px;
  left: var(--x);
  width: var(--s, 5px);
  height: var(--s, 5px);
  border-radius: 50%;
  background: #fff;
  opacity: var(--o);
  will-change: transform;
  animation: ptl-fall var(--d) linear var(--delay) infinite;
}
[data-mode='light'] .is-snow .ptl-p {
  background: rgb(150 180 215);
}
.is-confetti .ptl-p {
  width: 7px;
  height: 11px;
  border-radius: 2px;
  background: var(--c);
  animation-name: ptl-tumble;
}
@keyframes ptl-fall {
  to {
    transform: translate3d(var(--drift), var(--fall), 0);
  }
}
@keyframes ptl-tumble {
  to {
    transform: translate3d(var(--drift), var(--fall), 0) rotate(var(--r));
  }
}
@media (prefers-reduced-motion: reduce) {
  .ptl {
    display: none;
  }
}
</style>
