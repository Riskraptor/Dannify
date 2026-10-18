<template>
  <figure class="bc" :class="{ 'is-dense': dense }" :style="{ '--bc-h': `${height}px` }">
    <div
      ref="plot"
      class="bc-plot"
      tabindex="0"
      role="group"
      :aria-label="label"
      @keydown="onKey"
      @focus="onFocus"
      @blur="at = -1"
      @pointerleave="at = -1"
    >
      <div class="bc-grid" aria-hidden="true">
        <div
          v-for="tick in scale.ticks"
          :key="tick.value"
          class="bc-line"
          :style="{ bottom: share(tick.value) }"
        >
          <span class="bc-tick">{{ tick.label }}</span>
        </div>
      </div>
      <div class="bc-bars" aria-hidden="true">
        <div
          v-for="(bar, i) in bars"
          :key="bar.key"
          class="bc-col"
          :class="{ 'is-on': i === at }"
          @pointerenter="at = i"
          @pointerdown="at = i"
        >
          <span class="bc-bar" :style="{ height: share(bar.value) }" />
        </div>
      </div>
      <div v-if="shown" class="bc-tip menu-surface" :class="tipSide" :style="tipPlace" aria-hidden="true">
        <strong class="bc-tip-value">{{ shown.text }}</strong>
        <span class="bc-tip-label">{{ shown.title }}</span>
        <span v-if="shown.note" class="bc-tip-label">{{ shown.note }}</span>
      </div>
    </div>
    <div class="bc-axis" aria-hidden="true">
      <span
        v-for="l in labels"
        :key="l.index"
        class="bc-label"
        :class="{ 'is-last': bars.length > 12 && l.index === bars.length - 1 }"
        :style="{ left: centre(l.index) }"
      >
        {{ l.text }}
      </span>
    </div>
    <!-- Said as the arrow keys move along the bars. -->
    <p class="sr-only" aria-live="polite">{{ shown && byKeys ? `${shown.title}: ${shown.text}` : '' }}</p>
    <!-- Every figure, without a pointer and without the colour: what a
         screen reader reads in place of the bars. -->
    <table class="sr-only">
      <caption>{{ label }}</caption>
      <thead>
        <tr>
          <th scope="col">{{ columns[0] }}</th>
          <th scope="col">{{ columns[1] }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="bar in bars" :key="bar.key">
          <th scope="row">{{ bar.title }}</th>
          <td>{{ bar.text }}</td>
        </tr>
      </tbody>
    </table>
  </figure>
</template>

<script setup>
import { computed, ref } from 'vue'

// One series of upright bars: listening by the day, by the month, by the
// hour. Drawn with boxes, not a charting library: there is one colour, one
// axis and at most a few dozen bars, and a library for that would be most of
// the page's weight.
const props = defineProps({
  // [{ key, value, title, text, note? }]: `title` names the bar ("Mon 12
  // Oct"), `text` is its value in words ("1 hr 4 min").
  bars: { type: Array, required: true },
  // { max, ticks: [{ value, label }] } (see statsFormat.timeScale).
  scale: { type: Object, required: true },
  // [{ index, text }]: the names written under some of the bars.
  labels: { type: Array, default: () => [] },
  label: { type: String, required: true },
  // The table's two headings: what a bar is, and what its height is.
  columns: { type: Array, required: true },
  height: { type: Number, default: 180 },
  dense: { type: Boolean, default: false },
})

const plot = ref(null)
// The bar the pointer or the arrow keys are on.
const at = ref(-1)
const byKeys = ref(false)
const shown = computed(() => (at.value >= 0 ? props.bars[at.value] || null : null))

function share(value) {
  const max = props.scale.max || 1
  return `${Math.max(0, Math.min(100, ((value || 0) / max) * 100))}%`
}
// Where bar `i` is across the plot, past the gutter the scale is written in.
function centre(i) {
  const n = props.bars.length || 1
  return `calc(var(--bc-gutter) + (100% - var(--bc-gutter)) * ${(i + 0.5) / n})`
}

// The tooltip sits over its bar, and leans inward at either end so it is
// never cut off by the edge of the chart.
const tipSide = computed(() => {
  const n = props.bars.length
  if (n < 4) return ''
  if (at.value < n * 0.18) return 'is-start'
  if (at.value > n * 0.82 - 1) return 'is-end'
  return ''
})
const tipPlace = computed(() => ({
  left: centre(at.value),
  bottom: `calc(${shown.value ? share(shown.value.value) : '0%'} + 10px)`,
}))

function onFocus() {
  // Reached with Tab: start on the latest bar. A click has put it where the
  // pointer is already.
  byKeys.value = !!(plot.value && plot.value.matches(':focus-visible'))
  if (byKeys.value && at.value < 0) at.value = props.bars.length - 1
}
function onKey(e) {
  const n = props.bars.length
  if (!n) return
  const to = {
    ArrowLeft: at.value - 1,
    ArrowRight: at.value + 1,
    Home: 0,
    End: n - 1,
  }[e.key]
  if (e.key === 'Escape' && at.value >= 0) {
    e.preventDefault()
    e.stopPropagation()
    at.value = -1
    return
  }
  if (to === undefined) return
  // The arrows are the player's too (seek); here they are the chart's.
  e.preventDefault()
  e.stopPropagation()
  byKeys.value = true
  at.value = Math.max(0, Math.min(n - 1, at.value < 0 ? n - 1 : to))
}
</script>

<style scoped>
.bc {
  --bc-gutter: 58px;
  margin: 0;
}
.bc-plot {
  position: relative;
  height: var(--bc-h);
  border-radius: 6px;
  outline: none;
}
.bc-plot:focus-visible {
  outline: 2px solid rgb(var(--c-accent));
  outline-offset: 6px;
}
/* The baseline everything grows from: a shade firmer than the grid. */
.bc-grid {
  position: absolute;
  inset: 0;
  border-bottom: 1px solid rgb(var(--c-tint) / 0.18);
}
.bc-line {
  position: absolute;
  left: var(--bc-gutter);
  right: 0;
  height: 0;
  border-top: 1px solid rgb(var(--c-tint) / 0.07);
}
.bc-tick {
  position: absolute;
  right: 100%;
  top: 0;
  width: var(--bc-gutter);
  padding-right: 10px;
  transform: translateY(-50%);
  font-size: 11px;
  line-height: 1;
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-fg) / var(--fg-50));
}
.bc-bars {
  position: absolute;
  inset: 0 0 0 var(--bc-gutter);
  display: flex;
  align-items: stretch;
}
/* The whole slot answers the pointer, not just the bar in it: a day with
   two minutes of listening is two pixels tall. */
.bc-col {
  position: relative;
  display: flex;
  flex: 1 1 0;
  min-width: 0;
  align-items: flex-end;
  justify-content: center;
  border-radius: 4px 4px 0 0;
}
.bc-col.is-on {
  background: rgb(var(--c-tint) / 0.06);
}
/* Never the full width of its slot: the gap either side is what tells one
   bar from the next. Rounded where the value ends, square where it stands. */
.bc-bar {
  width: calc(100% - 2px);
  max-width: 24px;
  border-radius: 4px 4px 0 0;
  background: rgb(var(--c-accent));
  transition:
    height 0.45s var(--ease-out),
    background-color 0.1s ease;
}
.bc.is-dense .bc-bar {
  max-width: 14px;
  border-radius: 3px 3px 0 0;
}
.bc-col.is-on .bc-bar {
  background: rgb(var(--c-accent-hover));
}
.bc-tip {
  position: absolute;
  z-index: 5;
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 7px 10px;
  transform: translateX(-50%);
  white-space: nowrap;
  pointer-events: none;
}
.bc-tip.is-start {
  transform: translateX(-14px);
}
.bc-tip.is-end {
  transform: translateX(calc(-100% + 14px));
}
/* The figure first and in full ink: whoever is on a bar knows which day it
   is, and wants the number. */
.bc-tip-value {
  font-size: 13.5px;
  font-weight: 700;
  color: rgb(var(--c-fg));
}
.bc-tip-label {
  font-size: 12px;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.bc-axis {
  position: relative;
  height: 22px;
}
.bc-label {
  position: absolute;
  top: 7px;
  transform: translateX(-50%);
  font-size: 11px;
  line-height: 1;
  white-space: nowrap;
  color: rgb(var(--c-fg) / var(--fg-50));
}
.bc-label.is-last {
  transform: translateX(calc(-100% + 10px));
}
</style>
