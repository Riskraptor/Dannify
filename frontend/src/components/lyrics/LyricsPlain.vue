<template>
  <div class="plain-scroll" :class="{ 'is-large': large }" tabindex="0" :aria-label="t('lyrics.title')">
    <p class="plain-note">
      <Icon icon="ph:info" class="h-3.5 w-3.5 shrink-0" />
      <span class="min-w-0 flex-1">{{ t('lyrics.plainOnly') }}</span>
      <button class="plain-link press" @click="tools.contribute">{{ t('lyrics.addTiming') }}</button>
    </p>
    <!-- One paragraph per line, each finding its own direction: a song can
         go from Arabic to English and back. -->
    <div class="plain-text selectable">
      <p v-for="(line, i) in rows" :key="i" dir="auto" :class="{ 'is-gap': !line }">{{ line }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { useLyricsTools } from '/src/model/lyrics/useLyricsTools'

const props = defineProps({
  text: { type: String, required: true },
  large: { type: Boolean, default: false },
})

const { t } = useI18n()
const tools = useLyricsTools()

// Runs of blank lines are one gap between verses.
const rows = computed(() =>
  props.text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l, i, all) => l || (i > 0 && all[i - 1]))
)
</script>

<style scoped>
.plain-scroll {
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
  padding: 0.75rem 0.75rem 2rem 0.6rem;
  overflow-anchor: none;
  font-size: 15px;
  line-height: 1.65;
  color: rgb(var(--c-fg) / 0.8);
  -webkit-mask-image: linear-gradient(to bottom, #000 0, #000 86%, transparent 100%);
  mask-image: linear-gradient(to bottom, #000 0, #000 86%, transparent 100%);
}
.plain-scroll::-webkit-scrollbar {
  display: none;
}
.plain-scroll:focus-visible {
  outline-offset: -2px;
  border-radius: 10px;
}
.plain-note {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgb(var(--c-accent) / 0.22);
  background: rgb(var(--c-accent) / 0.07);
  font-size: 12.5px;
  line-height: 1.45;
  color: rgb(var(--c-fg) / 0.78);
  backdrop-filter: blur(8px);
}
/* The action is the point of the note, so it looks like one. */
.plain-link {
  flex: none;
  padding: 4px 11px;
  border-radius: 999px;
  font-weight: 700;
  font-size: 12px;
  color: rgb(var(--c-accent-fg));
  background: rgb(var(--c-accent));
  transition: filter 0.15s ease;
}
.plain-link:hover {
  filter: brightness(1.08);
}
.plain-text p {
  overflow-wrap: anywhere;
  text-align: start;
}
.plain-text p.is-gap {
  height: 0.9em;
}
.is-large {
  font-size: 1.25rem;
  line-height: 1.7;
}
</style>
