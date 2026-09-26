<template>
  <div ref="panel" class="lyrics-panel" :class="{ 'is-large': large }">
    <!-- Loading -->
    <div
      v-if="(player.lyricsLoading.value || refreshing) && !hasLines && !player.lyricsPlain.value"
      class="lp-center"
    >
      <span class="spinner h-6 w-6 text-fg/40" />
      <p class="text-[13px]">{{ t('lyrics.loading') }}</p>
    </div>

    <!-- Synced lyrics -->
    <div
      v-else-if="hasLines"
      ref="scroll"
      class="synced-scroll"
      @scroll.passive="onUserScroll"
      @wheel.passive="onUserScroll"
    >
      <div class="lp-spacer-top" />
      <p
        v-for="(line, idx) in player.lyricsLines.value"
        :key="idx"
        :ref="(el) => setLineRef(el, idx)"
        class="lyric-line"
        :class="{ active: idx === active, past: idx < active }"
        :style="lineStyle(idx)"
        @click="player.seekToLyric(idx)"
      >
        <span class="lyric-stamp" aria-hidden="true">{{ stamp(line.time) }}</span>
        <span class="lyric-text">{{ line.text || '♪' }}</span>
      </p>
      <div class="lp-spacer-bottom" />
    </div>

    <!-- Plain lyrics fallback -->
    <div v-else-if="player.lyricsPlain.value" class="plain-scroll">
      <p class="plain-note">
        <Icon icon="ph:info" class="h-3.5 w-3.5" />
        {{ t('lyrics.plainOnly') }}
        <button class="plain-link" @click="onContribute">{{ t('lyrics.addTiming') }}</button>
      </p>
      <div class="selectable whitespace-pre-line leading-relaxed">
        {{ player.lyricsPlain.value }}
      </div>
    </div>

    <!-- No lyrics: the contribute path is the headline action here -->
    <div v-else class="lp-center px-6 text-center">
      <Icon icon="ph:microphone-stage" class="h-10 w-10 text-fg/25" />
      <p class="text-[13px]">{{ t('lyrics.none') }}</p>
      <p class="max-w-[320px] text-[12.5px] leading-relaxed text-fg/45">
        {{ t('lyrics.contributeBlurb') }}
      </p>
      <div class="mt-1 flex flex-wrap items-center justify-center gap-2">
        <button class="btn btn-pill press" :disabled="refreshing" @click="onRefresh">
          <Icon icon="ph:arrows-clockwise" class="h-4 w-4" :class="{ 'animate-spin': refreshing }" />
          {{ t('lyrics.tryAgain') }}
        </button>
        <button class="btn-accent btn-pill press" @click="onContribute">
          <Icon icon="ph:plus" class="h-4 w-4" />
          {{ t('lyrics.contribute') }}
        </button>
      </div>
    </div>

    <!-- Back-to-current pill: shown while the user is browsing the lyrics.
         It disappears on its own once auto-scroll resumes. -->
    <transition name="jump">
      <button v-if="suspended && hasLines" class="lyrics-jump press" @click="jumpToCurrent">
        <Icon icon="ph:crosshair-simple" class="h-3.5 w-3.5" />
        {{ t('lyrics.jump') }}
        <span class="jump-countdown" :key="suspendTick" />
      </button>
    </transition>

    <!-- Sync-offset tweak bar (synced lyrics only) -->
    <transition name="jump">
      <div v-if="ui.lyricsSyncOpen.value && hasLines" class="lyrics-sync menu-surface">
        <span class="sync-label">{{ t('lyrics.sync') }}</span>
        <button class="icon-btn is-round press h-7 w-7" :title="t('lyrics.syncEarlier')" :aria-label="t('lyrics.syncEarlier')" @click="player.adjustLyricsOffset(-0.2)">
          <Icon icon="ph:minus-bold" class="h-3.5 w-3.5" />
        </button>
        <span class="sync-val" :class="{ zero: offsetVal === 0 }">
          {{ offsetVal > 0 ? '+' : '' }}{{ offsetVal.toFixed(1) }}s
        </span>
        <button class="icon-btn is-round press h-7 w-7" :title="t('lyrics.syncLater')" :aria-label="t('lyrics.syncLater')" @click="player.adjustLyricsOffset(0.2)">
          <Icon icon="ph:plus-bold" class="h-3.5 w-3.5" />
        </button>
        <button
          class="icon-btn is-round press h-7 w-7"
          :title="t('lyrics.syncReset')"
          @click="player.resetLyricsOffset()"
        >
          <Icon icon="ph:arrow-counter-clockwise" class="h-3.5 w-3.5" />
        </button>
        <button class="btn-accent btn-pill press h-7 px-3 text-xs" :disabled="saving" @click="onSaveSync">
          <Icon :icon="saved ? 'ph:check-bold' : 'ph:floppy-disk'" class="h-3.5 w-3.5" />
          {{ saved ? t('lyrics.syncSaved') : t('lyrics.syncSave') }}
        </button>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { Icon } from '@iconify/vue'
import { usePlayer } from '/src/model/player'
import { useUi } from '/src/model/ui'
import { useI18n } from '/src/i18n'

// How long the user's own scrolling wins before the panel glides back to the
// line that is playing. The countdown runs whether or not playback is paused
//: "where am I?" should never need a second click.
const RESUME_MS = 3000

defineProps({
  // Big, left-aligned typography for the full Now Playing view.
  large: { type: Boolean, default: false },
})

const { t } = useI18n()
const player = usePlayer()
const ui = useUi()

const panel = ref(null)
const scroll = ref(null)
const lineRefs = ref({})
const refreshing = ref(false)
const suspended = ref(false)
const suspendTick = ref(0)
const saving = ref(false)
const saved = ref(false)
let autoScrolling = false
let autoTimer = null
let resumeTimer = null

const offsetVal = computed(() => player.lyricsOffset.value || 0)
const hasLines = computed(() => player.lyricsLines.value.length > 0)
const active = computed(() => player.activeLyricIndex.value)

// Depth of field. Every line carries how far it is from the one playing, and
// the stylesheet turns that into blur, dimming and scale, so attention falls
// on the current line the way it does on a stage: one thing lit, everything
// else still there. Four steps is as far as it goes; past that the lines are
// only a texture and grading them further costs paint for nothing.
function lineStyle(idx) {
  return { '--d': Math.min(4, Math.abs(idx - active.value)) }
}

function stamp(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

async function onSaveSync() {
  if (saving.value) return
  saving.value = true
  try {
    await player.saveLyricsOffset()
    saved.value = true
    setTimeout(() => (saved.value = false), 2000)
  } finally {
    saving.value = false
  }
}

async function onRefresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    await player.refreshLyrics()
  } finally {
    refreshing.value = false
  }
}

function onContribute() {
  window.dispatchEvent(new CustomEvent('dannify:open-lyrics-submit'))
}

function setLineRef(el, idx) {
  if (el) lineRefs.value[idx] = el
  else delete lineRefs.value[idx]
}

// Centre the active line. `instant` on track changes and big jumps so the
// panel never appears to lag behind the song.
function scrollToActive(instant = false) {
  const el = lineRefs.value[active.value]
  const container = scroll.value
  if (!el || !container) return
  const target = el.offsetTop - container.clientHeight / 2 + el.clientHeight / 2
  autoScrolling = true
  container.scrollTo({ top: target, behavior: instant ? 'auto' : 'smooth' })
  clearTimeout(autoTimer)
  autoTimer = setTimeout(
    () => {
      autoScrolling = false
    },
    instant ? 60 : 450
  )
}

function resume() {
  suspended.value = false
  scrollToActive(false)
}

function jumpToCurrent() {
  clearTimeout(resumeTimer)
  suspended.value = false
  scrollToActive(true)
}

// Manual scrolling hands control to the user: but only for RESUME_MS, after
// which the panel returns to the playing line by itself.
function onUserScroll() {
  if (autoScrolling) return
  suspended.value = true
  suspendTick.value++
  clearTimeout(resumeTimer)
  resumeTimer = setTimeout(resume, RESUME_MS)
}

watch(active, (idx, prev) => {
  if (suspended.value) return
  const instant = prev == null || Math.abs(idx - (prev ?? idx)) > 2
  nextTick(() => scrollToActive(instant))
})

// New lyric set (track change): forget the refs and snap to the start.
watch(
  () => player.lyricsLines.value,
  () => {
    lineRefs.value = {}
    clearTimeout(resumeTimer)
    suspended.value = false
    nextTick(() => scrollToActive(true))
  }
)

// Opened mid-song: land on the current line, not the top of the song.
onMounted(() => nextTick(() => scrollToActive(true)))
onBeforeUnmount(() => clearTimeout(resumeTimer))
</script>

<style scoped>
.lyrics-panel {
  position: relative;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
.lp-center {
  display: flex;
  height: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: rgb(var(--c-fg) / 0.45);
}
.synced-scroll,
.plain-scroll {
  height: 100%;
  overflow-y: auto;
  scrollbar-width: none;
  padding: 0 0.25rem;
  /* WebView2 keeps the scroll anchored to a growing element otherwise, which
     fights our own scrollTo during playback. */
  overflow-anchor: none;
  -webkit-mask-image: linear-gradient(to bottom, transparent 0, #000 14%, #000 86%, transparent 100%);
  mask-image: linear-gradient(to bottom, transparent 0, #000 14%, #000 86%, transparent 100%);
}
.synced-scroll::-webkit-scrollbar,
.plain-scroll::-webkit-scrollbar {
  display: none;
}
.lp-spacer-top {
  height: 38%;
}
.lp-spacer-bottom {
  height: 48%;
}
.plain-scroll {
  padding-top: 0.75rem;
  padding-bottom: 2rem;
  font-size: 15px;
  color: rgb(var(--c-fg) / 0.8);
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
  margin-left: auto;
  flex: none;
  padding: 4px 11px;
  border-radius: 999px;
  font-weight: 700;
  font-size: 12px;
  color: rgb(var(--c-accent-fg));
  background: rgb(var(--c-accent));
  transition:
    filter 0.15s ease,
    transform 0.12s ease;
}
.plain-link:hover {
  filter: brightness(1.08);
}
.plain-link:active {
  transform: scale(0.96);
}

.lyric-line {
  --d: 4;
  position: relative;
  font-family: var(--font-display, theme('fontFamily.display'));
  font-size: 1.4rem;
  line-height: 1.34;
  font-weight: 700;
  letter-spacing: -0.01em;
  padding: 0.3rem 0.55rem;
  margin: 0 -0.55rem;
  border-radius: 10px;
  color: rgb(var(--c-fg) / 0.55);
  cursor: pointer;
  transform-origin: left center;
  /* The graded part: one step away is almost sharp, four steps is scenery. */
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
/* Lines already sung recede further than lines still to come: looking back
   is rarely what you want, and it leaves the road ahead easier to read. */
.lyric-line.past {
  color: rgb(var(--c-fg) / 0.4);
  opacity: calc(0.82 - var(--d) * 0.17);
}
.lyric-line:hover {
  color: rgb(var(--c-fg) / 0.8);
  background: rgb(var(--c-tint) / 0.06);
  filter: none;
  opacity: 1;
}
/* Timestamp gutter appears on hover so a line can be used as a cue point.
   Only where there is room for it: the side panel is narrow. */
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
  font-family: inherit;
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-fg) / 0.4);
  opacity: 0;
  transition: opacity 0.15s ease;
}
.is-large .lyric-line:hover .lyric-stamp {
  opacity: 1;
}

/* The whole line lights up when it starts, rather than colouring in word by
   word as it is sung. Word timings are often a little off, and a sweep that
   runs ahead of the voice is worse than no sweep at all; a line that simply
   arrives, grows and comes into focus is easier to read and easier to sing
   along to. The timing bar underneath still shows how far through the line
   playback is, for anyone syncing. */
.lyric-line.active {
  color: rgb(var(--c-fg));
  font-size: 1.62rem;
  opacity: 1;
  filter: none;
  transform: scale(1.01);
  text-shadow: 0 0 30px rgb(var(--c-accent) / 0.22);
}
/* A soft pool of light behind the line that is playing. Barely there, but
   it is what makes the current line findable at a glance in a wall of text. */
.lyric-line.active::before {
  content: '';
  position: absolute;
  inset: -0.35rem -1.1rem;
  z-index: -1;
  border-radius: 16px;
  background: radial-gradient(
    120% 100% at 0% 50%,
    rgb(var(--c-accent) / 0.13),
    transparent 72%
  );
  animation: lyric-glow 0.5s var(--ease-out) both;
  pointer-events: none;
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
.lyric-line.active:hover {
  color: rgb(var(--c-fg));
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
.is-large .plain-scroll {
  font-size: 1.25rem;
  line-height: 1.7;
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
  background: rgb(var(--c-fg));
  color: rgb(var(--c-panel));
  font-size: 12px;
  font-weight: 700;
  box-shadow: var(--shadow-pop);
  overflow: hidden;
  z-index: 6;
}
/* A hairline that drains as the auto-return countdown runs, so the pill
   explains itself instead of vanishing without warning. */
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
.lyrics-sync {
  position: absolute;
  bottom: 0.75rem;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.3rem 0.4rem 0.3rem 0.8rem;
  border-radius: 9999px;
  z-index: 7;
  white-space: nowrap;
}
.sync-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: rgb(var(--c-fg) / 0.5);
  padding-right: 0.2rem;
}
.sync-val {
  min-width: 2.8rem;
  text-align: center;
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-accent));
}
.sync-val.zero {
  color: rgb(var(--c-fg) / 0.55);
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
@media (max-width: 640px) {
  .lyric-line {
    font-size: 1.2rem;
  }
}
</style>
