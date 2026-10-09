<template>
  <!-- The shape of lyrics, where lyrics will be: the lines arrive in the
       same place, at the same size, instead of after a spinner. -->
  <div class="lyrics-skeleton" :class="{ 'is-large': large }" role="status">
    <span class="sr-only">{{ t('lyrics.loading') }}</span>
    <span
      v-for="(w, i) in WIDTHS"
      :key="i"
      class="skeleton bar"
      :class="{ 'is-lead': i === 2 }"
      :style="{ width: w + '%', animationDelay: i * 40 + 'ms' }"
      aria-hidden="true"
    />
  </div>
</template>

<script setup>
import { useI18n } from '/src/i18n'

defineProps({ large: { type: Boolean, default: false } })

const { t } = useI18n()
const WIDTHS = [62, 78, 86, 54, 70, 46, 66]
</script>

<style scoped>
.lyrics-skeleton {
  display: flex;
  height: 100%;
  flex-direction: column;
  justify-content: center;
  gap: 14px;
  padding: 0 0.6rem;
  overflow: hidden;
  -webkit-mask-image: linear-gradient(to bottom, transparent 0, #000 22%, #000 78%, transparent 100%);
  mask-image: linear-gradient(to bottom, transparent 0, #000 22%, #000 78%, transparent 100%);
}
.bar {
  height: 1.15rem;
  max-width: 100%;
  border-radius: 8px;
}
.bar.is-lead {
  height: 1.45rem;
  background: rgb(var(--c-tint) / 0.11);
}
.is-large {
  gap: 20px;
  padding-left: 3.4rem;
}
.is-large .bar {
  height: 1.8rem;
}
.is-large .bar.is-lead {
  height: 2.3rem;
}
</style>
