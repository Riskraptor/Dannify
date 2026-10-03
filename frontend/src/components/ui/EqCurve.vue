<template>
  <!-- What the equalizer does to the sound, as its filters compute it: 20 Hz
       to 20 kHz across, -12 to +12 dB up the side. Redrawn as the bands
       glide to a new setting, so a preset is seen as well as heard. -->
  <div ref="wrap" class="eqc" :class="{ 'is-off': !on }">
    <canvas ref="canvas" class="eqc-canvas" aria-hidden="true" />
    <span class="eqc-label eqc-top">+12</span>
    <span class="eqc-label eqc-mid">0 dB</span>
    <span class="eqc-label eqc-low">−12</span>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { usePlayer } from '/src/model/player'

const props = defineProps({
  on: { type: Boolean, default: true },
  // Changes whenever the bands do (the gains), to trigger a redraw.
  gains: { type: Array, default: () => [] },
})

const player = usePlayer()
const wrap = ref(null)
const canvas = ref(null)
const POINTS = 160
const freqs = Array.from({ length: POINTS }, (_, i) => 20 * Math.pow(1000, i / (POINTS - 1)))
let frame = 0
let until = 0
let resize = null

function color(name, alpha = 1) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '29 185 84'
  return `rgb(${v} / ${alpha})`
}

function draw() {
  const c = canvas.value
  if (!c || !wrap.value) return
  const w = wrap.value.clientWidth
  const h = wrap.value.clientHeight
  const dpr = window.devicePixelRatio || 1
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr)
    c.height = Math.round(h * dpr)
  }
  const g = c.getContext('2d')
  g.setTransform(dpr, 0, 0, dpr, 0, 0)
  g.clearRect(0, 0, w, h)

  const pad = 6
  const y = (db) => h / 2 - (Math.max(-12, Math.min(12, db)) / 12) * (h / 2 - pad)
  // Grid: the 0 dB line, and each decade.
  g.strokeStyle = color('--c-tint', 0.08)
  g.lineWidth = 1
  g.beginPath()
  g.moveTo(0, Math.round(h / 2) + 0.5)
  g.lineTo(w, Math.round(h / 2) + 0.5)
  for (const f of [100, 1000, 10000]) {
    const x = Math.round((Math.log10(f / 20) / 3) * w) + 0.5
    g.moveTo(x, pad)
    g.lineTo(x, h - pad)
  }
  g.stroke()

  const curve = props.on ? player.eqCurve(freqs) : new Float32Array(POINTS)
  const pts = freqs.map((_, i) => [(i / (POINTS - 1)) * w, y(curve[i] || 0)])
  const accent = props.on ? '--c-accent' : '--c-fg'
  // Fill to the 0 dB line, then the line itself.
  const fill = g.createLinearGradient(0, 0, 0, h)
  fill.addColorStop(0, color(accent, props.on ? 0.28 : 0.06))
  fill.addColorStop(0.5, color(accent, 0.02))
  fill.addColorStop(1, color(accent, props.on ? 0.28 : 0.06))
  g.beginPath()
  g.moveTo(0, h / 2)
  for (const [x, yy] of pts) g.lineTo(x, yy)
  g.lineTo(w, h / 2)
  g.closePath()
  g.fillStyle = fill
  g.fill()
  g.beginPath()
  pts.forEach(([x, yy], i) => (i ? g.lineTo(x, yy) : g.moveTo(x, yy)))
  g.strokeStyle = color(accent, props.on ? 0.95 : 0.3)
  g.lineWidth = 2
  g.lineJoin = 'round'
  g.stroke()
}

// The filters glide to a new setting over a fraction of a second: drawn
// every frame while they do.
function animate() {
  draw()
  if (performance.now() < until) frame = requestAnimationFrame(animate)
  else frame = 0
}
function redraw() {
  until = performance.now() + 450
  if (!frame) frame = requestAnimationFrame(animate)
}

watch(() => [props.on, ...props.gains], redraw)
onMounted(() => {
  redraw()
  resize = new ResizeObserver(redraw)
  resize.observe(wrap.value)
})
onBeforeUnmount(() => {
  if (frame) cancelAnimationFrame(frame)
  if (resize) resize.disconnect()
})
</script>

<style scoped>
.eqc {
  position: relative;
  width: 100%;
  height: 96px;
  border-radius: 10px;
  background: rgb(var(--c-tint) / 0.035);
  overflow: hidden;
}
.eqc-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.eqc-label {
  position: absolute;
  left: 8px;
  font-size: 9.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-fg) / 0.35);
  pointer-events: none;
}
.eqc-top {
  top: 4px;
}
.eqc-mid {
  top: 50%;
  transform: translateY(-115%);
}
.eqc-low {
  bottom: 4px;
}
.eqc.is-off {
  opacity: 0.7;
}
</style>
