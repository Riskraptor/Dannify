<template>
  <!-- The song, played from right beside the words: lyrics are as often
       written down while listening as pasted, and the player bar is under
       the editor. The keys work while typing in the box. -->
  <div class="listen" role="group" :aria-label="t('publish.listenLabel')">
    <div class="listen-row">
      <button
        class="play press"
        :title="`${playing ? t('player.pause') : t('player.play')} (Ctrl+Space)`"
        :aria-label="playing ? t('player.pause') : t('player.play')"
        @mousedown.prevent
        @click="listen.toggle()"
      >
        <Icon :icon="playing ? 'ph:pause-fill' : 'ph:play-fill'" class="h-4 w-4" />
      </button>
      <button
        class="skip press"
        :title="`${t('publish.back5')} (Alt+←)`"
        :aria-label="t('publish.back5')"
        @mousedown.prevent
        @click="listen.back()"
      >
        <Icon icon="ph:arrow-counter-clockwise-bold" class="h-4 w-4" />
        <span>5</span>
      </button>
      <button
        class="skip press"
        :title="`${t('publish.fwd5')} (Alt+→)`"
        :aria-label="t('publish.fwd5')"
        @mousedown.prevent
        @click="listen.forward()"
      >
        <span>5</span>
        <Icon icon="ph:arrow-clockwise-bold" class="h-4 w-4" />
      </button>

      <div
        ref="scrubEl"
        class="scrub"
        role="slider"
        tabindex="0"
        :aria-label="t('publish.position')"
        aria-valuemin="0"
        :aria-valuemax="Math.round(duration)"
        :aria-valuenow="Math.round(now)"
        :aria-valuetext="formatShort(now)"
        @mousedown.prevent
        @pointerdown="onScrubDown"
        @keydown="onScrubKey"
      >
        <div class="track"><div class="fill" :style="{ width: progress + '%' }" /></div>
        <span class="thumb" :style="{ left: progress + '%' }" />
      </div>

      <div class="clock" data-time>
        <span class="now">{{ formatShort(now) }}</span>
        <span class="sep">/</span>
        <span class="total">{{ formatShort(duration) }}</span>
      </div>

      <div class="seg rates" role="group" :aria-label="t('publish.playbackSpeed')">
        <button
          v-for="r in RATES"
          :key="r"
          class="seg-item rate"
          :class="{ 'is-active': Math.abs(rate - r) < 0.01 }"
          :aria-pressed="Math.abs(rate - r) < 0.01 ? 'true' : 'false'"
          @mousedown.prevent
          @click="session.setRate(r)"
        >
          {{ r }}×
        </button>
      </div>
    </div>

    <div class="listen-help">
      <span class="keys">
        <span><kbd class="kbd">Ctrl Space</kbd> {{ t('publish.keyPlay') }}</span>
        <span><kbd class="kbd">Alt ←</kbd><kbd class="kbd">Alt →</kbd> {{ t('publish.keySkip') }}</span>
      </span>
      <button
        class="replay press"
        :class="{ on: listen.replay.value }"
        :aria-pressed="listen.replay.value ? 'true' : 'false'"
        :title="t('publish.replayHint')"
        @mousedown.prevent
        @click="listen.setReplay(!listen.replay.value)"
      >
        <Icon :icon="listen.replay.value ? 'ph:check-bold' : 'ph:clock-counter-clockwise-bold'" class="h-3.5 w-3.5" />
        {{ t('publish.replay') }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, onBeforeUnmount } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { LYRICS_EDITOR } from '/src/model/lyrics/useLyricsSubmit'
import { formatShort } from '/src/model/lyrics/lrc'

// Slower, not faster: fast words are what need catching.
const RATES = [0.5, 0.75, 1]

const { t } = useI18n()
const { session, player, listen } = inject(LYRICS_EDITOR)

const scrubEl = ref(null)
const playing = computed(() => player.isPlaying.value)
const now = computed(() => player.currentTime.value || 0)
const duration = computed(() => player.duration.value || 0)
const rate = computed(() => player.playbackRate.value || 1)
const progress = computed(() => (duration.value ? Math.min(100, Math.max(0, (now.value / duration.value) * 100)) : 0))

function scrubAt(clientX) {
  const rect = scrubEl.value?.getBoundingClientRect()
  if (!rect || !rect.width || !duration.value) return
  const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
  session.seekTo(duration.value * ratio)
}

// The words box keeps the focus: a click on the bar moves the song, and the
// typing carries on where it was.
let stopDrag = null
function onScrubDown(e) {
  scrubAt(e.clientX)
  const move = (ev) => scrubAt(ev.clientX)
  const up = () => stopDrag?.()
  stopDrag = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
    stopDrag = null
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}
onBeforeUnmount(() => stopDrag?.())

const SCRUB_KEYS = { ArrowLeft: -5, ArrowDown: -5, ArrowRight: 5, ArrowUp: 5, PageDown: -15, PageUp: 15 }
function onScrubKey(e) {
  if (e.altKey || e.ctrlKey || e.metaKey) return
  if (e.key in SCRUB_KEYS) session.seekBy(SCRUB_KEYS[e.key])
  else if (e.key === 'Home') session.seekTo(0)
  else if (e.key === 'End' && duration.value) session.seekTo(duration.value - 1)
  else return
  e.preventDefault()
}
</script>

<style scoped>
.listen {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px 7px;
  border-radius: 12px;
  border: 1px solid rgb(var(--c-tint) / 0.08);
  background: rgb(var(--c-tint) / 0.04);
}
.listen-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.play {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 999px;
  background: rgb(var(--c-fg));
  color: rgb(var(--c-elev));
  transition: transform 0.1s ease;
}
.play:hover {
  transform: scale(1.04);
}
.skip {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 3px;
  height: 30px;
  padding: 0 7px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-fg) / 0.7);
  transition:
    background-color 0.12s ease,
    color 0.12s ease;
}
.skip:hover {
  background: rgb(var(--c-tint) / 0.08);
  color: rgb(var(--c-fg));
}
.scrub {
  position: relative;
  flex: 1;
  height: 26px;
  min-width: 60px;
  margin: 0 6px;
  border-radius: 6px;
  cursor: pointer;
  touch-action: none;
}
.scrub:focus-visible {
  outline-offset: 2px;
}
.track {
  position: absolute;
  inset: 11px 0;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.12);
}
.fill {
  height: 100%;
  background: rgb(var(--c-accent));
}
.thumb {
  position: absolute;
  top: 50%;
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: rgb(var(--c-fg));
  box-shadow: 0 1px 4px rgb(0 0 0 / 0.35);
  transform: translate(-50%, -50%);
  pointer-events: none;
}
.clock {
  display: flex;
  flex-shrink: 0;
  gap: 4px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-fg) / 0.55);
}
.clock .now {
  color: rgb(var(--c-fg));
  font-weight: 600;
}
.clock .sep {
  opacity: 0.5;
}
.rates {
  flex-shrink: 0;
  margin-left: 4px;
}
.rate {
  height: 26px;
  padding: 0 7px;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}
.listen-help {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 4px 12px;
  padding-left: 2px;
  font-size: 11.5px;
  color: rgb(var(--c-fg) / 0.5);
}
.keys {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 14px;
}
.keys > span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.keys .kbd {
  height: 18px;
}
.replay {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 24px;
  padding: 0 9px;
  border-radius: 999px;
  border: 1px solid rgb(var(--c-tint) / 0.12);
  font-size: 11.5px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.6);
  transition:
    background-color 0.12s ease,
    border-color 0.12s ease,
    color 0.12s ease;
}
.replay:hover {
  border-color: rgb(var(--c-tint) / 0.22);
  color: rgb(var(--c-fg) / 0.85);
}
.replay.on {
  border-color: rgb(var(--c-accent) / 0.45);
  background: rgb(var(--c-accent) / 0.1);
  color: rgb(var(--c-accent));
}
/* Narrow: the bar gets a row of its own, the buttons and speeds above it. */
@container editor (max-width: 620px) {
  .listen-row {
    flex-wrap: wrap;
  }
  .scrub {
    order: 5;
    flex-basis: 100%;
    margin: 0 4px;
  }
  .clock {
    margin-left: auto;
  }
}
@container editor (max-width: 400px) {
  .clock .sep,
  .clock .total {
    display: none;
  }
  .keys {
    display: none;
  }
}
</style>
