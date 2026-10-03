<template>
  <!-- The equalizer, drawn and played with: the music's spectrum as it plays,
       the curve the filters make of it, and a handle on each band to drag.
       Double-click a handle for 0 dB; the wheel nudges it; with the graph
       focused, Left and Right pick a band and Up and Down move it. -->
  <div
    ref="wrap"
    class="eqg"
    :class="{ 'is-off': !on, 'is-dragging': dragging >= 0 }"
    tabindex="0"
    role="group"
    :aria-label="t('settings.equalizer')"
    @pointerdown="onDown"
    @pointermove="onMove"
    @pointerup="onUp"
    @pointercancel="onUp"
    @pointerleave="hover = -1"
    @dblclick="onDouble"
    @wheel.prevent="onWheel"
    @keydown="onKey"
  >
    <canvas ref="canvas" class="eqg-canvas" aria-hidden="true" />
    <div v-if="tip" class="eqg-tip" :style="{ left: `${tip.x}px`, top: `${tip.y}px` }">
      {{ tip.text }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { usePlayer } from '/src/model/player'
import { EQ_BANDS } from '/src/model/audioEngine'
import { useI18n } from '/src/i18n'

const props = defineProps({
  on: { type: Boolean, default: true },
  gains: { type: Array, default: () => [] },
  // Whether to draw the live spectrum behind (the mixer, not Settings).
  live: { type: Boolean, default: true },
})
const emit = defineEmits(['band'])

const { t } = useI18n()
const player = usePlayer()
const wrap = ref(null)
const canvas = ref(null)
const hover = ref(-1)
const dragging = ref(-1)
const focusBand = ref(-1)

const PAD_X = 22
const PAD_TOP = 14
const PAD_BOTTOM = 22
const F_MIN = 20
const F_MAX = 20000
const POINTS = 180
const freqs = Array.from({ length: POINTS }, (_, i) => F_MIN * Math.pow(F_MAX / F_MIN, i / (POINTS - 1)))
let spectrumBuf = null
let size = { w: 0, h: 0 }
let frame = 0
let lastDraw = 0
let resize = null

function colour(name, alpha = 1) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '29 185 84'
  return `rgb(${v} / ${alpha})`
}
const xOf = (f) => PAD_X + (Math.log(f / F_MIN) / Math.log(F_MAX / F_MIN)) * (size.w - PAD_X * 2)
const yOf = (db) => PAD_TOP + ((12 - Math.max(-12, Math.min(12, db))) / 24) * (size.h - PAD_TOP - PAD_BOTTOM)
const dbOf = (y) => 12 - ((y - PAD_TOP) / (size.h - PAD_TOP - PAD_BOTTOM)) * 24

const handles = computed(() =>
  EQ_BANDS.map((f, i) => ({ f, i, db: Number(props.gains[i]) || 0 }))
)

const tip = computed(() => {
  const i = dragging.value >= 0 ? dragging.value : hover.value >= 0 ? hover.value : focusBand.value
  if (i < 0 || !size.w) return null
  const h = handles.value[i]
  const db = h.db > 0 ? `+${h.db.toFixed(1)}` : h.db.toFixed(1)
  const hz = h.f >= 1000 ? `${h.f / 1000} kHz` : `${h.f} Hz`
  return { x: xOf(h.f), y: yOf(h.db) - 30, text: `${hz}  ${db} dB` }
})

function draw(now = performance.now()) {
  const c = canvas.value
  if (!c || !wrap.value) return
  lastDraw = now
  const w = wrap.value.clientWidth
  const h = wrap.value.clientHeight
  size = { w, h }
  const dpr = window.devicePixelRatio || 1
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr)
    c.height = Math.round(h * dpr)
  }
  const g = c.getContext('2d')
  g.setTransform(dpr, 0, 0, dpr, 0, 0)
  g.clearRect(0, 0, w, h)

  // Grid: 0 dB and +/-6, and the decades.
  g.lineWidth = 1
  for (const db of [12, 6, 0, -6, -12]) {
    g.strokeStyle = colour('--c-tint', db === 0 ? 0.14 : 0.06)
    g.beginPath()
    g.moveTo(PAD_X, Math.round(yOf(db)) + 0.5)
    g.lineTo(w - PAD_X, Math.round(yOf(db)) + 0.5)
    g.stroke()
  }
  g.fillStyle = colour('--c-fg', 0.38)
  g.font = '600 9.5px system-ui, sans-serif'
  g.textAlign = 'center'
  for (const f of EQ_BANDS) {
    g.fillText(f >= 1000 ? `${f / 1000}k` : String(f), xOf(f), h - 6)
  }
  g.textAlign = 'left'
  g.fillText('+12', 2, yOf(12) + 3)
  g.fillText('0', 6, yOf(0) + 3)
  g.fillText('-12', 2, yOf(-12) + 3)

  // The music, as it plays.
  if (props.live && player.isPlaying.value) {
    const info = player.spectrumInfo()
    if (info.bins) {
      if (!spectrumBuf || spectrumBuf.length !== info.bins) spectrumBuf = new Float32Array(info.bins)
      if (player.spectrum(spectrumBuf)) {
        const nyquist = info.sampleRate / 2
        const grad = g.createLinearGradient(0, PAD_TOP, 0, h - PAD_BOTTOM)
        grad.addColorStop(0, colour('--c-accent', 0.32))
        grad.addColorStop(1, colour('--c-accent', 0.02))
        g.beginPath()
        g.moveTo(PAD_X, h - PAD_BOTTOM)
        const steps = 120
        for (let s = 0; s <= steps; s++) {
          const f = F_MIN * Math.pow(F_MAX / F_MIN, s / steps)
          const bin = Math.min(info.bins - 1, Math.round((f / nyquist) * info.bins))
          const level = Math.max(0, Math.min(1, (spectrumBuf[bin] + 100) / 80))
          g.lineTo(xOf(f), h - PAD_BOTTOM - level * (h - PAD_TOP - PAD_BOTTOM))
        }
        g.lineTo(w - PAD_X, h - PAD_BOTTOM)
        g.closePath()
        g.fillStyle = grad
        g.fill()
      }
    }
  }

  // The curve the filters make.
  const curve = props.on ? player.eqCurve(freqs) : new Float32Array(POINTS)
  g.beginPath()
  freqs.forEach((f, i) => {
    const x = xOf(f)
    const y = yOf(curve[i] || 0)
    if (i) g.lineTo(x, y)
    else g.moveTo(x, y)
  })
  g.strokeStyle = colour(props.on ? '--c-accent' : '--c-fg', props.on ? 1 : 0.35)
  g.lineWidth = 2.25
  g.lineJoin = 'round'
  g.stroke()

  // The handles.
  for (const hd of handles.value) {
    const active = hd.i === dragging.value || hd.i === hover.value || hd.i === focusBand.value
    const x = xOf(hd.f)
    const y = yOf(hd.db)
    g.beginPath()
    g.arc(x, y, active ? 7.5 : 5.5, 0, Math.PI * 2)
    g.fillStyle = props.on ? colour('--c-accent', 1) : colour('--c-fg', 0.4)
    g.fill()
    g.lineWidth = 2
    g.strokeStyle = colour('--c-panel', 1)
    g.stroke()
  }
}

// Redrawn while the music plays (for the spectrum), or once after a change.
function loop(now) {
  frame = 0
  const playing = props.live && player.isPlaying.value
  if (now - lastDraw >= 33) draw(now) // about 30 a second is plenty
  if (playing && document.visibilityState === 'visible') frame = requestAnimationFrame(loop)
}
function redraw() {
  if (frame) return
  frame = requestAnimationFrame((now) => {
    frame = 0
    draw(now)
    if (props.live && player.isPlaying.value) frame = requestAnimationFrame(loop)
  })
}

function nearest(e) {
  const r = wrap.value.getBoundingClientRect()
  const x = e.clientX - r.left
  const y = e.clientY - r.top
  let best = -1
  let bestD = Infinity
  for (const hd of handles.value) {
    const d = Math.hypot(xOf(hd.f) - x, yOf(hd.db) - y)
    if (d < bestD) {
      bestD = d
      best = hd.i
    }
  }
  // Close to a handle, or anywhere in its column.
  const col = handles.value[best]
  const inColumn = col && Math.abs(xOf(col.f) - x) < 14
  return bestD < 16 || inColumn ? { i: best, y } : null
}

function setFromY(i, y) {
  const db = Math.round(dbOf(y) * 2) / 2
  emit('band', i, Math.max(-12, Math.min(12, db)))
}

function onDown(e) {
  if (e.button !== 0) return
  const hit = nearest(e)
  if (!hit) return
  e.preventDefault()
  wrap.value.setPointerCapture(e.pointerId)
  dragging.value = hit.i
  focusBand.value = hit.i
  setFromY(hit.i, hit.y)
}
function onMove(e) {
  if (dragging.value >= 0) {
    const r = wrap.value.getBoundingClientRect()
    setFromY(dragging.value, e.clientY - r.top)
    return
  }
  const hit = nearest(e)
  hover.value = hit ? hit.i : -1
}
function onUp(e) {
  if (dragging.value < 0) return
  try {
    wrap.value.releasePointerCapture(e.pointerId)
  } catch {
    // released already
  }
  dragging.value = -1
}
function onDouble(e) {
  const hit = nearest(e)
  if (hit) emit('band', hit.i, 0)
}
function onWheel(e) {
  const hit = nearest(e)
  const i = hit ? hit.i : focusBand.value
  if (i < 0) return
  const now = Number(props.gains[i]) || 0
  emit('band', i, Math.max(-12, Math.min(12, now + (e.deltaY < 0 ? 0.5 : -0.5))))
}
function onKey(e) {
  const n = EQ_BANDS.length
  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    e.preventDefault()
    e.stopPropagation()
    const at = focusBand.value < 0 ? 0 : focusBand.value
    focusBand.value = (at + (e.key === 'ArrowRight' ? 1 : -1) + n) % n
  } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
    e.preventDefault()
    e.stopPropagation()
    const i = focusBand.value < 0 ? 0 : focusBand.value
    focusBand.value = i
    const now = Number(props.gains[i]) || 0
    emit('band', i, Math.max(-12, Math.min(12, now + (e.key === 'ArrowUp' ? 0.5 : -0.5))))
  } else if (e.key === '0' || e.key === 'Delete') {
    if (focusBand.value >= 0) emit('band', focusBand.value, 0)
  }
}

watch(() => [props.on, ...props.gains], () => {
  // The filters glide to the new setting: draw for a moment while they do.
  const until = performance.now() + 400
  const glide = (now) => {
    draw(now)
    if (now < until) requestAnimationFrame(glide)
  }
  requestAnimationFrame(glide)
})
watch([hover, dragging, focusBand], redraw)
watch(() => player.isPlaying.value, redraw)

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
.eqg {
  position: relative;
  width: 100%;
  height: 170px;
  border-radius: 10px;
  background: rgb(var(--c-tint) / 0.035);
  cursor: crosshair;
  outline: none;
  touch-action: none;
}
.eqg:focus-visible {
  box-shadow: 0 0 0 2px rgb(var(--c-accent) / 0.6);
}
.eqg.is-dragging {
  cursor: ns-resize;
}
.eqg.is-off {
  opacity: 0.75;
}
.eqg-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.eqg-tip {
  position: absolute;
  z-index: 1;
  transform: translateX(-50%);
  padding: 3px 8px;
  border-radius: 6px;
  white-space: nowrap;
  pointer-events: none;
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  background: rgb(var(--c-elev));
  color: rgb(var(--c-fg));
  box-shadow: var(--shadow-pop);
}
</style>
