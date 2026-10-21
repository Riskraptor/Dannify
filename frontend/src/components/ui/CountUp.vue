<template>
  <span class="count-up">{{ shown }}</span>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

// A number that counts up to itself when it appears: the big moments of
// "Your year in music". Straight to the number for less motion.
const props = defineProps({
  value: { type: Number, default: 0 },
  // How it is written: Intl.NumberFormat in the app's language.
  format: { type: Function, default: (n) => String(n) },
  ms: { type: Number, default: 1300 },
})

const now = ref(0)
let raf = 0

function still() {
  try {
    return matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

function run() {
  cancelAnimationFrame(raf)
  const target = props.value || 0
  if (still() || target <= 0) {
    now.value = target
    return
  }
  const start = performance.now()
  now.value = 0
  const step = (t) => {
    const p = Math.min(1, (t - start) / props.ms)
    // Fast, then easing into the number.
    now.value = Math.round(target * (1 - Math.pow(1 - p, 3)))
    if (p < 1) raf = requestAnimationFrame(step)
  }
  raf = requestAnimationFrame(step)
}

const shown = computed(() => props.format(now.value))
onMounted(run)
watch(() => props.value, run)
onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<style scoped>
.count-up {
  font-variant-numeric: tabular-nums;
}
</style>
