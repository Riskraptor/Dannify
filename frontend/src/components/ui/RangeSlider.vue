<template>
  <div
    ref="root"
    class="rs"
    :class="{ 'is-dragging': dragging, 'is-disabled': disabled }"
    role="slider"
    :tabindex="disabled ? -1 : 0"
    :aria-label="label"
    aria-valuemin="0"
    aria-valuemax="100"
    :aria-valuenow="Math.round(shown * 100)"
    :aria-valuetext="tooltip ? tooltip(shown) : undefined"
    @pointerdown="onDown"
    @pointermove="onHover"
    @pointerleave="hoverRatio = null"
    @wheel="onWheel"
    @keydown="onKey"
  >
    <div class="rs-track">
      <div class="rs-fill" :style="{ width: `${shown * 100}%` }" />
    </div>
    <div class="rs-thumb" :style="{ left: `${shown * 100}%` }" />
    <div
      v-if="tooltip && (dragging || hoverRatio !== null)"
      class="rs-tip"
      :style="{ left: `${(dragging ? shown : hoverRatio) * 100}%` }"
    >
      {{ tooltip(dragging ? shown : hoverRatio) }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

// A pointer-driven slider for 0..1 values.
//   live=true  → emits `input` continuously while dragging (volume)
//   live=false → previews while dragging, emits `change` on release (seek)
const props = defineProps({
  value: { type: Number, default: 0 },
  disabled: { type: Boolean, default: false },
  live: { type: Boolean, default: true },
  step: { type: Number, default: 0.05 },
  label: { type: String, default: '' },
  tooltip: { type: Function, default: null },
})
const emit = defineEmits(['input', 'change'])

const root = ref(null)
const dragging = ref(false)
const dragRatio = ref(0)
const hoverRatio = ref(null)

const clamp = (v) => Math.max(0, Math.min(1, Number(v) || 0))
const shown = computed(() => (dragging.value ? dragRatio.value : clamp(props.value)))

function ratioAt(clientX) {
  const rect = root.value.getBoundingClientRect()
  return clamp((clientX - rect.left) / rect.width)
}

function onDown(e) {
  if (props.disabled || e.button !== 0) return
  e.preventDefault()
  root.value.focus({ preventScroll: true })
  root.value.setPointerCapture(e.pointerId)
  dragging.value = true
  dragRatio.value = ratioAt(e.clientX)
  if (props.live) emit('input', dragRatio.value)
  const move = (ev) => {
    dragRatio.value = ratioAt(ev.clientX)
    if (props.live) emit('input', dragRatio.value)
  }
  const up = () => {
    root.value.removeEventListener('pointermove', move)
    root.value.removeEventListener('pointerup', up)
    root.value.removeEventListener('pointercancel', up)
    const final = dragRatio.value
    dragging.value = false
    emit('change', final)
    if (!props.live) emit('input', final)
  }
  root.value.addEventListener('pointermove', move)
  root.value.addEventListener('pointerup', up)
  root.value.addEventListener('pointercancel', up)
}

function onHover(e) {
  if (!props.tooltip || props.disabled) return
  hoverRatio.value = ratioAt(e.clientX)
}

function nudge(delta) {
  const next = clamp(clamp(props.value) + delta)
  emit('input', next)
  emit('change', next)
}

function onWheel(e) {
  if (props.disabled) return
  e.preventDefault()
  nudge(e.deltaY < 0 ? props.step : -props.step)
}

function onKey(e) {
  if (props.disabled) return
  const map = {
    ArrowRight: props.step,
    ArrowUp: props.step,
    ArrowLeft: -props.step,
    ArrowDown: -props.step,
    PageUp: props.step * 4,
    PageDown: -props.step * 4,
  }
  if (e.key in map) {
    e.preventDefault()
    nudge(map[e.key])
  } else if (e.key === 'Home' || e.key === 'End') {
    e.preventDefault()
    const v = e.key === 'Home' ? 0 : 1
    emit('input', v)
    emit('change', v)
  }
}
</script>

<style scoped>
.rs {
  position: relative;
  display: flex;
  align-items: center;
  height: 16px;
  flex: 1;
  min-width: 0;
  touch-action: none;
}
.rs:focus-visible {
  outline-offset: 4px;
  border-radius: 4px;
}
.rs-track {
  position: relative;
  width: 100%;
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.18);
}
.rs-fill {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: 999px;
  background: rgb(var(--c-fg) / 0.85);
}
.rs:hover .rs-fill,
.rs.is-dragging .rs-fill,
.rs:focus-visible .rs-fill {
  background: rgb(var(--c-accent));
}
.rs-thumb {
  position: absolute;
  top: 50%;
  width: 12px;
  height: 12px;
  margin-left: -6px;
  border-radius: 999px;
  background: #fff;
  box-shadow: 0 1px 4px rgb(0 0 0 / 0.4);
  transform: translateY(-50%) scale(0);
  transition: transform 0.12s ease;
}
.rs:hover .rs-thumb,
.rs.is-dragging .rs-thumb,
.rs:focus-visible .rs-thumb {
  transform: translateY(-50%) scale(1);
}
.rs.is-disabled {
  opacity: 0.4;
}
.rs.is-disabled .rs-thumb {
  display: none;
}
.rs-tip {
  position: absolute;
  bottom: calc(100% + 8px);
  padding: 3px 7px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  color: rgb(var(--c-fg));
  background: rgb(var(--c-elev));
  box-shadow: var(--shadow-pop);
  transform: translateX(-50%);
  pointer-events: none;
}
</style>
