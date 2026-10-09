<template>
  <div class="lyrics-lines" :class="{ 'is-large': large }">
    <div
      ref="scroll"
      class="synced-scroll"
      @scroll.passive="follow.hold"
      @wheel.passive="follow.hold"
    >
      <div class="spacer-top" aria-hidden="true" />
      <!-- One tab stop for the whole song: the arrow keys walk the lines,
           Enter plays from the one with the focus. A tab stop per line made
           the rest of the window a few hundred presses away. -->
      <ol
        class="lines"
        :aria-label="t('lyrics.linesLabel')"
        @keydown="onKey"
        @focusout="onFocusOut"
      >
        <li
          v-for="(line, idx) in lines"
          :key="idx"
          :ref="(el) => follow.setLineEl(el, idx)"
          class="lyric-line"
          :class="{ active: idx === active, past: idx < active }"
          :style="{ '--d': Math.min(4, Math.abs(idx - active)) }"
          :tabindex="idx === tabStop ? 0 : -1"
          :aria-current="idx === active ? 'true' : undefined"
          dir="auto"
          @click="player.seekToLyric(idx)"
          @focus="focused = idx"
        >
          <span class="lyric-stamp" aria-hidden="true">{{ formatShort(line.time) }}</span>
          <span class="lyric-text">{{ line.text || '♪' }}</span>
        </li>
      </ol>
      <div class="spacer-bottom" aria-hidden="true" />
    </div>

    <!-- Back to the line playing, while the user reads elsewhere. It goes on
         its own once following resumes; the hairline shows when. -->
    <transition name="jump">
      <button v-if="follow.suspended.value" class="lyrics-jump press" @click="follow.jumpToCurrent">
        <Icon icon="ph:crosshair-simple" class="h-3.5 w-3.5" />
        {{ t('lyrics.jump') }}
        <span :key="follow.suspendTick.value" class="jump-countdown" />
      </button>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { Icon } from '@iconify/vue'
import { usePlayer } from '/src/model/player'
import { useI18n } from '/src/i18n'
import { formatShort } from '/src/model/lyrics/lrc'
import { useLyricsFollow } from '/src/model/lyrics/useLyricsFollow'

defineProps({ large: { type: Boolean, default: false } })

const { t } = useI18n()
const player = usePlayer()

const scroll = ref(null)
const lines = computed(() => player.lyricsLines.value)
const active = computed(() => player.activeLyricIndex.value)
// The line keyboard focus is on, or -1: then Tab lands on the line playing.
const focused = ref(-1)
const tabStop = computed(() => (focused.value >= 0 ? focused.value : Math.max(0, active.value)))

const follow = useLyricsFollow({ container: scroll, active, lines })

function focusLine(idx) {
  const to = Math.max(0, Math.min(lines.value.length - 1, idx))
  focused.value = to
  follow.hold()
  nextTick(() => {
    const box = scroll.value
    const el = box?.querySelectorAll('.lyric-line')[to]
    if (!el) return
    el.focus({ preventScroll: true })
    // Into view inside the lyrics only, clear of the faded edges. The
    // browser's own scrollIntoView also moves every clipped pane around it.
    const pad = box.clientHeight * 0.2
    const top = el.offsetTop
    const bottom = top + el.offsetHeight
    if (top < box.scrollTop + pad) box.scrollTo({ top: top - pad })
    else if (bottom > box.scrollTop + box.clientHeight - pad) box.scrollTo({ top: bottom - box.clientHeight + pad })
  })
}

function onKey(e) {
  if (e.altKey || e.ctrlKey || e.metaKey) return
  const at = focused.value >= 0 ? focused.value : Math.max(0, active.value)
  const moves = { ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: lines.value.length - 1, PageDown: at + 5, PageUp: at - 5 }
  if (e.key in moves) {
    e.preventDefault()
    focusLine(moves[e.key])
  } else if (e.key === 'Enter') {
    e.preventDefault()
    player.seekToLyric(at)
  }
}

function onFocusOut(e) {
  if (!e.currentTarget.contains(e.relatedTarget)) focused.value = -1
}
</script>

<style scoped>
.lyrics-lines {
  position: relative;
  height: 100%;
}
.synced-scroll {
  position: relative;
  height: 100%;
  overflow-y: auto;
  /* Never sideways: the line being sung is drawn a touch larger, and each
     line's hover reaches past the text, and together they let the pane be
     dragged left and right. The padding keeps both inside it. */
  overflow-x: hidden;
  scrollbar-width: none;
  padding: 0 0.75rem 0 0.6rem;
  /* WebView2 keeps the scroll anchored to a growing element otherwise, which
     fights our own scrollTo during playback. */
  overflow-anchor: none;
  -webkit-mask-image: linear-gradient(to bottom, transparent 0, #000 14%, #000 86%, transparent 100%);
  mask-image: linear-gradient(to bottom, transparent 0, #000 14%, #000 86%, transparent 100%);
}
.synced-scroll::-webkit-scrollbar {
  display: none;
}
.spacer-top {
  height: 38%;
}
.spacer-bottom {
  height: 48%;
}
.lines {
  margin: 0;
  padding: 0;
  list-style: none;
}

/* Depth of field. Every line carries how far it is from the one playing
   (--d), and that turns into blur, dimming and scale, so attention falls on
   the current line the way it does on a stage. Four steps is as far as it
   goes; past that the lines are only a texture. */
.lyric-line {
  --d: 4;
  position: relative;
  font-family: var(--font-display, theme('fontFamily.display'));
  font-size: 1.4rem;
  line-height: 1.34;
  font-weight: 700;
  letter-spacing: -0.01em;
  text-align: start;
  padding: 0.3rem 0.55rem;
  margin: 0 -0.55rem;
  border-radius: 10px;
  color: rgb(var(--c-fg) / 0.55);
  cursor: pointer;
  transform-origin: left center;
  overflow-wrap: anywhere;
  opacity: calc(1 - var(--d) * 0.17);
  filter: blur(calc(var(--d) * 0.5px));
  transform: scale(calc(1 - var(--d) * 0.008));
  transition:
    color 0.32s ease,
    opacity 0.32s var(--ease-out),
    filter 0.32s var(--ease-out),
    font-size 0.32s var(--ease-out),
    transform 0.32s var(--ease-out);
}
.lyric-line:dir(rtl) {
  transform-origin: right center;
}
/* Lines already sung recede further than lines still to come. */
.lyric-line.past {
  color: rgb(var(--c-fg) / 0.4);
  opacity: calc(0.82 - var(--d) * 0.17);
}
.lyric-line:hover,
.lyric-line:focus-visible {
  color: rgb(var(--c-fg) / 0.85);
  background: rgb(var(--c-tint) / 0.06);
  filter: none;
  opacity: 1;
}
.lyric-line:focus-visible {
  outline-offset: -2px;
}
/* A time gutter on hover, so a line can be used as a cue point. Only where
   there is room for it: the side panel is narrow. */
.is-large .synced-scroll {
  padding-left: 3.4rem;
}
.lyric-stamp {
  display: none;
}
.is-large .lyric-stamp {
  display: block;
  position: absolute;
  left: -2.6rem;
  top: 50%;
  transform: translateY(-50%);
  font-family: var(--font-body, theme('fontFamily.sans'));
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-fg) / 0.4);
  opacity: 0;
  transition: opacity 0.15s ease;
}
.is-large .lyric-line:hover .lyric-stamp,
.is-large .lyric-line:focus-visible .lyric-stamp {
  opacity: 1;
}

/* The whole line lights up when it starts, rather than colouring in word by
   word: word timings are often a little off, and a sweep that runs ahead of
   the voice is worse than none. */
.lyric-line.active {
  color: rgb(var(--c-fg));
  font-size: 1.62rem;
  opacity: 1;
  filter: none;
  transform: scale(1.01);
  text-shadow: 0 0 30px rgb(var(--c-accent) / 0.22);
}
/* A soft pool of light behind the line playing: barely there, but it is
   what makes it findable at a glance in a wall of text. */
.lyric-line.active::before {
  content: '';
  position: absolute;
  inset: -0.35rem -1.1rem;
  z-index: -1;
  border-radius: 16px;
  background: radial-gradient(120% 100% at 0% 50%, rgb(var(--c-accent) / 0.13), transparent 72%);
  animation: lyric-glow 0.5s var(--ease-out) both;
  pointer-events: none;
}
.lyric-line.active:dir(rtl)::before {
  background: radial-gradient(120% 100% at 100% 50%, rgb(var(--c-accent) / 0.13), transparent 72%);
}
.lyric-line.active .lyric-text {
  animation: lyric-land 0.42s var(--ease-out) both;
}
@keyframes lyric-glow {
  from {
    opacity: 0;
  }
}
@keyframes lyric-land {
  from {
    opacity: 0.45;
    transform: translateY(2px);
  }
}

.is-large .lyric-line {
  font-size: clamp(1.6rem, 2.4vw, 2.3rem);
  line-height: 1.26;
  padding: 0.45rem 0.7rem;
  margin: 0 -0.7rem;
}
.is-large .lyric-line.active {
  font-size: clamp(1.9rem, 2.9vw, 2.75rem);
  text-shadow: 0 0 44px rgb(var(--c-accent) / 0.28);
}
@media (max-width: 640px) {
  .lyric-line {
    font-size: 1.2rem;
  }
}
@media (prefers-reduced-motion: reduce) {
  .lyric-line {
    transition: none;
    filter: none;
    transform: none;
  }
  .lyric-line.active {
    transform: none;
  }
  .lyric-line.active::before,
  .lyric-line.active .lyric-text {
    animation: none;
  }
}

.lyrics-jump {
  position: absolute;
  bottom: 0.75rem;
  left: 50%;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.85rem;
  border-radius: 9999px;
  /* Dark in every theme, like the toasts: it floats over cover art too. */
  border: 1px solid rgb(255 255 255 / 0.1);
  background: rgb(36 37 42 / 0.94);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  box-shadow: var(--shadow-pop);
  overflow: hidden;
  z-index: 6;
}
/* A hairline that drains as the countdown runs, so the pill explains
   itself instead of vanishing without warning. */
.jump-countdown {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 2px;
  width: 100%;
  background: rgb(var(--c-accent));
  transform-origin: left center;
  animation: jump-drain 3s linear forwards;
}
@keyframes jump-drain {
  to {
    transform: scaleX(0);
  }
}
.jump-enter-active,
.jump-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.jump-enter-from,
.jump-leave-to {
  opacity: 0;
  transform: translate(-50%, 10px);
}
</style>
