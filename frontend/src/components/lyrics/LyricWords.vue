<template>
  <!-- The line playing, word by word: what has been sung is lit, the word
       being sung fills in as it goes, and what is still to come waits a
       shade dimmer. Only this one line is drawn this way. -->
  <span class="lyric-words" :class="{ 'is-estimate': !exact, 'is-paused': !player.isPlaying.value }"
    ><span
      v-for="(w, i) in words"
      :key="i"
      class="w"
      :class="i < at ? 'w-sung' : i === at ? 'w-singing' : 'w-ahead'"
      :style="i === at ? { '--wd': `${w.dur}s`, '--wdelay': `${delay}s` } : null"
      >{{ w.text }}</span
    ></span
  >
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { usePlayer } from '/src/model/player'
import { lineWords, wordAt } from '/src/model/lyrics/words'

const props = defineProps({
  line: { type: Object, required: true },
  // When the next line starts, or null for the last one.
  next: { type: Number, default: null },
})

const player = usePlayer()

const timing = computed(() => lineWords(props.line, props.next))
const words = computed(() => timing.value.words)
const exact = computed(() => timing.value.exact)

// A touch early, as the lines are: a word lights as the voice reaches it.
// The frame clock is the finer one; the song's own clock keeps the words
// going when frames stall (a covered window).
const LEAD = 0.08
const now = () =>
  Math.max(player.frameTime.value, player.currentTime.value) - player.lyricsOffset.value + LEAD
// Read every frame, but it only changes when a new word starts.
const at = computed(() => wordAt(words.value, now()))

// Where the word's sweep starts: part way in when the song was joined (or
// sought to) in the middle of it.
const delay = ref(0)
watch(
  at,
  (i) => {
    const w = words.value[i]
    const into = w ? Math.min(w.dur, Math.max(0, now() - w.time)) : 0
    delay.value = -Math.round(into * 1000) / 1000
  },
  { immediate: true }
)
</script>

<style scoped>
.w-ahead {
  color: rgb(var(--c-fg) / 0.42);
}
.w-sung {
  color: rgb(var(--c-fg));
  text-shadow: 0 0 30px rgb(var(--c-accent) / 0.22);
}
/* The sweep: a gradient behind the letters, slid across in the word's own
   time by the compositor, so nothing is redrawn frame by frame. */
.w-singing {
  color: transparent;
  background-image: linear-gradient(90deg, rgb(var(--c-fg)) 45%, rgb(var(--c-fg) / 0.42) 55%);
  background-size: 225% 100%;
  background-position: 100% 0;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-box-decoration-break: clone;
  box-decoration-break: clone;
  animation: word-fill var(--wd, 0.3s) linear var(--wdelay, 0s) both;
}
/* Guessed timings get a softer edge, so being a little off does not show. */
.is-estimate .w-singing {
  background-image: linear-gradient(90deg, rgb(var(--c-fg)) 30%, rgb(var(--c-fg) / 0.42) 70%);
}
.is-paused .w-singing {
  animation-play-state: paused;
}
@keyframes word-fill {
  to {
    background-position: 0 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .w-singing {
    animation: none;
    background: none;
    color: rgb(var(--c-fg));
  }
}
</style>
