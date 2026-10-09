<template>
  <div class="transport">
    <div class="rail">
      <button
        class="play press"
        :title="playing ? t('player.pause') : t('player.play')"
        :aria-label="playing ? t('player.pause') : t('player.play')"
        @click="player.toggle()"
      >
        <Icon :icon="playing ? 'ph:pause-fill' : 'ph:play-fill'" class="h-5 w-5" />
      </button>

      <!-- The song as a bar: drag or click to move through it, each timed
           line a mark on it, the looped stretch shaded. -->
      <div
        ref="scrubEl"
        class="scrub"
        role="slider"
        tabindex="0"
        :aria-label="t('publish.position')"
        aria-valuemin="0"
        :aria-valuemax="Math.round(duration)"
        :aria-valuenow="Math.round(now)"
        :aria-valuetext="formatClock(now)"
        @pointerdown="onScrubDown"
        @keydown="onScrubKey"
      >
        <div class="track"><div class="fill" :style="{ width: progress + '%' }" /></div>
        <div v-if="loop" class="loop" :style="loop" />
        <span
          v-for="tick in ticks"
          :key="tick.index"
          class="tick"
          :class="{ error: tick.error, on: tick.index === editor.active.value }"
          :style="{ left: tick.left + '%' }"
          :title="formatLrcTime(tick.time) + '  ' + tick.text"
        />
        <span class="thumb" :style="{ left: progress + '%' }" />
      </div>

      <div class="clock" data-time>
        <span class="now">{{ formatClock(now) }}</span>
        <span class="sep">/</span>
        <span>{{ formatClock(duration) }}</span>
      </div>
    </div>

    <!-- Three named groups: eleven bare buttons in a row is a puzzle, three
         labelled ones a toolbar that reads at a glance. -->
    <div class="tools" role="toolbar" :aria-label="t('publish.toolsLabel')">
      <div class="group" role="group" :aria-label="t('publish.groupSeek')">
        <span class="group-label" aria-hidden="true">{{ t('publish.groupSeek') }}</span>
        <button
          v-for="b in SEEKS"
          :key="b.by"
          class="tool press"
          :title="t(b.label)"
          :aria-label="t(b.label)"
          @click="session.seekBy(b.by)"
        >
          <Icon :icon="b.icon" class="h-4 w-4" />
          <span>{{ Math.abs(b.by) }}s</span>
        </button>
      </div>

      <div class="group" role="group" :aria-label="t('publish.playbackSpeed')">
        <span class="group-label" aria-hidden="true">{{ t('publish.groupSpeed') }}</span>
        <div class="seg">
          <button
            v-for="r in RATES"
            :key="r"
            class="seg-item speed"
            :class="{ 'is-active': Math.abs(rate - r) < 0.01 }"
            :aria-pressed="Math.abs(rate - r) < 0.01 ? 'true' : 'false'"
            @click="session.setRate(r)"
          >
            {{ r }}×
          </button>
        </div>
      </div>

      <div class="group" role="group" :aria-label="t('publish.groupEdit')">
        <span class="group-label" aria-hidden="true">{{ t('publish.groupEdit') }}</span>
        <button
          class="tool press"
          :disabled="!editor.canUndo.value"
          :title="t('publish.undoHint')"
          :aria-label="t('publish.undoHint')"
          @click="editor.undo()"
        >
          <Icon icon="ph:arrow-counter-clockwise-bold" class="h-4 w-4" />
        </button>
        <button
          class="tool press"
          :disabled="!editor.canRedo.value"
          :title="t('publish.redoHint')"
          :aria-label="t('publish.redoHint')"
          @click="editor.redo()"
        >
          <Icon icon="ph:arrow-clockwise-bold" class="h-4 w-4" />
        </button>
        <button
          class="tool press is-danger"
          :disabled="!editor.timed.value"
          :title="t('publish.reset')"
          :aria-label="t('publish.reset')"
          @click="session.clearAll()"
        >
          <Icon icon="ph:trash-bold" class="h-4 w-4" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, onBeforeUnmount } from 'vue'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { LYRICS_EDITOR } from '/src/model/lyrics/useLyricsSubmit'
import { formatClock, formatLrcTime } from '/src/model/lyrics/lrc'
import { stampTicks } from '/src/model/lyrics/timing'

const SEEKS = [
  { by: -10, icon: 'ph:rewind-fill', label: 'publish.back10' },
  { by: -2, icon: 'ph:skip-back-fill', label: 'publish.back2' },
  { by: 2, icon: 'ph:skip-forward-fill', label: 'publish.fwd2' },
  { by: 10, icon: 'ph:fast-forward-fill', label: 'publish.fwd10' },
]
const RATES = [0.5, 0.75, 1, 1.25, 1.5]

const { t } = useI18n()
const { s, session, player } = inject(LYRICS_EDITOR)
const editor = s.editor

const scrubEl = ref(null)
const playing = computed(() => player.isPlaying.value)
const now = computed(() => player.currentTime.value || 0)
const duration = computed(() => player.duration.value || 0)
const rate = computed(() => player.playbackRate.value || 1)
const progress = computed(() => (duration.value ? Math.min(100, Math.max(0, (now.value / duration.value) * 100)) : 0))
const ticks = computed(() => stampTicks(editor.lines.value, duration.value, editor.quality.value))
const loop = computed(() => {
  const a = player.clipLoopStart.value
  const b = player.clipLoopEnd.value
  const d = duration.value
  if (a == null || b == null || !d) return null
  return { left: (a / d) * 100 + '%', width: Math.max(1, ((b - a) / d) * 100) + '%' }
})

function scrubAt(clientX) {
  const rect = scrubEl.value?.getBoundingClientRect()
  if (!rect || !rect.width || !duration.value) return
  const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
  player.seek(duration.value * ratio)
}

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
  else if (e.key === 'Home') player.seek(0)
  else if (e.key === 'End' && duration.value) player.seek(Math.max(0, duration.value - 1))
  else return
  e.preventDefault()
}
</script>

<style scoped>
.transport {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.rail {
  display: flex;
  align-items: center;
  gap: 12px;
}
.play {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  border-radius: 999px;
  background: rgb(var(--c-fg));
  color: rgb(var(--c-elev));
  transition: transform 0.1s ease;
}
.play:hover {
  transform: scale(1.04);
}
.scrub {
  position: relative;
  flex: 1;
  height: 28px;
  min-width: 80px;
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
.loop {
  position: absolute;
  top: 4px;
  bottom: 4px;
  border-radius: 4px;
  background: rgb(var(--c-accent) / 0.18);
  border: 1px solid rgb(var(--c-accent) / 0.5);
  pointer-events: none;
}
.tick {
  position: absolute;
  top: 6px;
  width: 2px;
  height: 16px;
  margin-left: -1px;
  border-radius: 2px;
  background: rgb(var(--c-fg) / 0.35);
}
.tick.on {
  background: rgb(var(--c-accent));
}
.tick.error {
  background: rgb(var(--c-danger));
}
.thumb {
  position: absolute;
  top: 50%;
  width: 14px;
  height: 14px;
  border-radius: 999px;
  background: rgb(var(--c-fg));
  box-shadow: 0 1px 4px rgb(0 0 0 / 0.35);
  transform: translate(-50%, -50%);
  pointer-events: none;
}
.clock {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  font-size: 12.5px;
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
.tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 18px;
}
.group {
  display: flex;
  align-items: center;
  gap: 2px;
}
.group-label {
  margin-right: 6px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: rgb(var(--c-fg) / 0.4);
}
.tool {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 8px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-fg) / 0.7);
  transition:
    background-color 0.12s ease,
    color 0.12s ease;
}
.tool:hover:not(:disabled) {
  background: rgb(var(--c-tint) / 0.08);
  color: rgb(var(--c-fg));
}
.tool:disabled {
  opacity: 0.35;
}
.tool.is-danger:hover:not(:disabled) {
  color: rgb(var(--c-danger));
}
.speed {
  height: 26px;
  padding: 0 8px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
@container editor (max-width: 720px) {
  .group-label {
    display: none;
  }
  .tools {
    gap: 8px 10px;
  }
}
@container editor (max-width: 480px) {
  .clock .sep,
  .clock span:last-child {
    display: none;
  }
}
</style>
