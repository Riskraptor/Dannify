<template>
  <!-- A name said with a little ceremony: each letter rises into place, then
       a light runs across them. Still, for less motion. -->
  <span class="an" :aria-label="text">
    <span
      v-for="(ch, i) in letters"
      :key="i + ch"
      class="an-ch"
      :class="{ 'is-space': ch === ' ' }"
      :style="{ '--i': i }"
      aria-hidden="true"
      >{{ ch }}</span
    >
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ text: { type: String, default: '' } })
// By character, not by UTF-16 unit: a name in any script stays whole.
const letters = computed(() => Array.from(props.text))
</script>

<style scoped>
.an {
  display: inline-block;
  white-space: pre;
}
.an-ch {
  display: inline-block;
  color: transparent;
  background-image: linear-gradient(
    100deg,
    var(--an-ink, rgb(var(--c-fg))) 0 40%,
    var(--an-shine, rgb(var(--c-accent))) 50%,
    var(--an-ink, rgb(var(--c-fg))) 60% 100%
  );
  background-size: 300% 100%;
  background-position: 100% 0;
  -webkit-background-clip: text;
  background-clip: text;
  opacity: 0;
  transform: translateY(0.5em) rotate(8deg) scale(0.85);
  filter: blur(6px);
  animation:
    an-in 0.7s cubic-bezier(0.2, 0.9, 0.25, 1.25) forwards,
    an-shine 1.4s ease-in-out forwards;
  animation-delay:
    calc(var(--i) * 55ms + 150ms),
    calc(var(--i) * 55ms + 900ms);
}
.an-ch.is-space {
  width: 0.28em;
}
@keyframes an-in {
  to {
    opacity: 1;
    transform: none;
    filter: none;
  }
}
@keyframes an-shine {
  to {
    background-position: 0 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .an-ch {
    opacity: 1;
    transform: none;
    filter: none;
    animation: none;
    color: var(--an-ink, rgb(var(--c-fg)));
    background: none;
  }
}
</style>
