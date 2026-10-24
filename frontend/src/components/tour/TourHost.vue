<template>
  <Teleport to="body">
    <div class="tour" role="dialog" aria-modal="true" :aria-label="t('tour.label')">
      <!-- The dim, in four parts round a hole where the thing is: a click on
           the dim does nothing, the thing itself can be used. -->
      <template v-if="hole">
        <div class="tour-dim" :style="dims.top" />
        <div class="tour-dim" :style="dims.bottom" />
        <div class="tour-dim" :style="dims.left" />
        <div class="tour-dim" :style="dims.right" />
        <div class="tour-ring" :class="{ 'is-try': tryOn && !tried }" :style="ringStyle" />
      </template>
      <div v-else class="tour-dim is-full" />

      <!-- From the words to the thing they are about. -->
      <svg v-if="arrow" class="tour-arrow" aria-hidden="true">
        <defs>
          <marker id="tour-head" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
            <path d="M1 1 L11 6 L1 11 z" />
          </marker>
        </defs>
        <path :key="`a${index}`" class="tour-arrow-path" :d="arrow" marker-end="url(#tour-head)" />
      </svg>

      <Particles v-if="step.celebrate" :look="CONFETTI" :count="90" />

      <section
        ref="card"
        :key="`c${index}`"
        class="tour-card"
        :class="[`is-${placed}`, { 'is-center': !hole }]"
        :style="cardStyle"
        aria-live="polite"
      >
        <span v-if="step.icon" class="tour-icon"><Icon :icon="step.icon" class="h-6 w-6" /></span>
        <p class="tour-count">{{ t('tour.step', { n: index + 1, total: steps.length }) }}</p>
        <h2 class="tour-title">{{ t(`tour.${step.id}Title`) }}</h2>
        <p class="tour-text">{{ t(`tour.${step.id}Text`) }}</p>
        <p v-if="tryOn" class="tour-try" :class="{ 'is-done': tried }">
          <Icon :icon="tried ? 'ph:check-circle-fill' : 'ph:hand-pointing-fill'" class="h-4 w-4 shrink-0" />
          {{ tried ? t('tour.nice') : t(`tour.${step.id}Try`) }}
        </p>
        <div class="tour-dots" aria-hidden="true">
          <span v-for="(s, i) in steps" :key="s.id" :class="{ 'is-on': i === index, 'is-past': i < index }" />
        </div>
        <footer class="tour-foot">
          <button v-if="!last" class="tour-skip" @click="end">{{ t('tour.skip') }}</button>
          <span class="flex-1" />
          <button v-if="index > 0 && !last" class="btn btn-pill h-9" @click="back">{{ t('tour.back') }}</button>
          <button ref="nextBtn" class="btn-accent btn-pill h-9 px-5" @click="next">
            {{ last ? t('tour.finish') : tryOn && !tried ? t('tour.skipStep') : t('tour.next') }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useI18n } from '/src/i18n'
import { endTour, tour } from '/src/model/tour'
import Particles from '/src/components/ui/Particles.vue'
import { TOURS } from './steps'

const CONFETTI = { shape: 'ribbon', motion: 'burst', palette: ['#1ed760', '#ff8fab', '#ffd166', '#7aa2ff', '#c084fc'] }
const PAD = 8
const GAP = 36
const EDGE = 14
const TALL = 0.5

const { t } = useI18n()
const router = useRouter()

const steps = computed(() => TOURS[(tour.value && tour.value.name) || 'welcome'] || TOURS.welcome)
const index = ref(0)
const step = computed(() => steps.value[index.value] || {})
const last = computed(() => index.value === steps.value.length - 1)

const target = shallowRef(null)
const tryEl = shallowRef(null)
const rect = ref(null)
const tried = ref(false)
const tryOn = computed(() => !!step.value.try && (step.value.try === 'type' || !!tryEl.value))
const card = ref(null)
const nextBtn = ref(null)
const cardSize = ref({ w: 360, h: 220 })
const view = ref({ w: window.innerWidth, h: window.innerHeight })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
function find(name) {
  if (!name) return null
  const el = document.querySelector(`[data-tour="${name}"]`)
  if (!el) return null
  const r = el.getBoundingClientRect()
  return r.width > 0 && r.height > 0 ? el : null
}

let token = 0
async function show(i, dir = 1) {
  const mine = ++token
  const s = steps.value[i]
  if (!s) return end()
  index.value = i
  tried.value = false
  target.value = null
  tryEl.value = null
  rect.value = null
  if (s.route && router.currentRoute.value.name !== s.route) {
    await router.push({ name: s.route }).catch(() => {})
  }
  let el = null
  if (s.target) {
    for (let n = 0; n < 40 && !el; n++) {
      el = find(s.target)
      if (!el) await sleep(50)
      if (mine !== token) return
    }
    if (!el && s.optional) {
      const to = i + dir
      if (to >= 0 && to < steps.value.length) return show(to, dir)
    }
  }
  if (el) {
    const tall = el.getBoundingClientRect().height > window.innerHeight * TALL
    el.scrollIntoView({ block: tall ? 'start' : 'nearest', inline: 'nearest' })
    target.value = el
    tryEl.value = s.try === 'click' ? find(s.tryTarget) : null
  }
  measure()
  await nextTick()
  measureCard()
  if (s.try === 'type' && el) {
    const input = el.querySelector('input, textarea')
    if (input) input.focus({ preventScroll: true })
  } else if (nextBtn.value) {
    nextBtn.value.focus({ preventScroll: true })
  }
}

function next() {
  if (last.value) return end()
  show(index.value + 1, 1)
}
function back() {
  if (index.value > 0) show(index.value - 1, -1)
}
function end() {
  token++
  endTour()
}

// ----- where everything goes -------------------------------------------------
function measure() {
  view.value = { w: window.innerWidth, h: window.innerHeight }
  const el = target.value
  if (!el || !el.isConnected) {
    rect.value = null
    return
  }
  const r = el.getBoundingClientRect()
  if (!r.width || !r.height) {
    rect.value = null
    return
  }
  // What the thing opens under itself (the search suggestions) is lit too.
  let { top, left, right, bottom } = r
  for (const more of el.querySelectorAll('[data-tour-grow]')) {
    const m = more.getBoundingClientRect()
    if (!m.width || !m.height) continue
    top = Math.min(top, m.top)
    left = Math.min(left, m.left)
    right = Math.max(right, m.right)
    bottom = Math.max(bottom, m.bottom)
  }
  // Something taller than half the window (a whole page section): its top
  // is lit, leaving room for the words.
  bottom = Math.min(bottom, top + window.innerHeight * TALL)
  rect.value = { top, left, width: right - left, height: bottom - top }
}
function measureCard() {
  const el = card.value
  if (el) cardSize.value = { w: el.offsetWidth || 360, h: el.offsetHeight || 220 }
}

const hole = computed(() => {
  const r = rect.value
  if (!r) return null
  const top = Math.max(0, r.top - PAD)
  const left = Math.max(0, r.left - PAD)
  const right = Math.min(view.value.w, r.left + r.width + PAD)
  const bottom = Math.min(view.value.h, r.top + r.height + PAD)
  return { top, left, right, bottom, width: right - left, height: bottom - top, cx: (left + right) / 2, cy: (top + bottom) / 2 }
})
const dims = computed(() => {
  const h = hole.value
  return {
    top: { top: 0, left: 0, right: 0, height: `${h.top}px` },
    bottom: { top: `${h.bottom}px`, left: 0, right: 0, bottom: 0 },
    left: { top: `${h.top}px`, left: 0, width: `${h.left}px`, height: `${h.height}px` },
    right: { top: `${h.top}px`, left: `${h.right}px`, right: 0, height: `${h.height}px` },
  }
})
const ringStyle = computed(() => {
  const h = hole.value
  return { top: `${h.top}px`, left: `${h.left}px`, width: `${h.width}px`, height: `${h.height}px` }
})

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))
// Where the words go: the side asked for, else the side with room.
const layout = computed(() => {
  const h = hole.value
  const { w, h: ch } = cardSize.value
  const { w: vw, h: vh } = view.value
  if (!h) return { place: 'center', left: (vw - w) / 2, top: (vh - ch) / 2 }
  const fits = {
    bottom: h.bottom + GAP + ch <= vh - EDGE,
    top: h.top - GAP - ch >= EDGE,
    right: h.right + GAP + w <= vw - EDGE,
    left: h.left - GAP - w >= EDGE,
  }
  const order = [step.value.place || 'bottom', 'bottom', 'top', 'right', 'left']
  const place = order.find((p) => fits[p]) || 'center'
  if (place === 'bottom') return { place, top: h.bottom + GAP, left: clamp(h.cx - w / 2, EDGE, vw - w - EDGE) }
  if (place === 'top') return { place, top: h.top - GAP - ch, left: clamp(h.cx - w / 2, EDGE, vw - w - EDGE) }
  if (place === 'right') return { place, left: h.right + GAP, top: clamp(h.cy - ch / 2, EDGE, vh - ch - EDGE) }
  if (place === 'left') return { place, left: h.left - GAP - w, top: clamp(h.cy - ch / 2, EDGE, vh - ch - EDGE) }
  return { place: 'center', left: (vw - w) / 2, top: (vh - ch) / 2 }
})
const placed = computed(() => layout.value.place)
const cardStyle = computed(() => ({ left: `${layout.value.left}px`, top: `${layout.value.top}px` }))

// A curve from the card's near edge to the thing, ending in a point.
const arrow = computed(() => {
  const h = hole.value
  const l = layout.value
  if (!h || l.place === 'center') return ''
  const { w, h: ch } = cardSize.value
  let sx, sy, ex, ey
  if (l.place === 'bottom') {
    sx = clamp(h.cx, l.left + 40, l.left + w - 40)
    sy = l.top - 4
    ex = h.cx
    ey = h.bottom + 3
  } else if (l.place === 'top') {
    sx = clamp(h.cx, l.left + 40, l.left + w - 40)
    sy = l.top + ch + 4
    ex = h.cx
    ey = h.top - 3
  } else if (l.place === 'right') {
    sx = l.left - 4
    sy = clamp(h.cy, l.top + 30, l.top + ch - 30)
    ex = h.right + 3
    ey = h.cy
  } else {
    sx = l.left + w + 4
    sy = clamp(h.cy, l.top + 30, l.top + ch - 30)
    ex = h.left - 3
    ey = h.cy
  }
  const vertical = l.place === 'bottom' || l.place === 'top'
  // A gentle curve, never more than the way is long.
  const bend = Math.min(34, Math.hypot(ex - sx, ey - sy) * 0.3)
  const cx = (sx + ex) / 2 + (vertical ? bend : 0)
  const cy = (sy + ey) / 2 + (vertical ? 0 : -bend)
  return `M ${sx.toFixed(1)} ${sy.toFixed(1)} Q ${cx.toFixed(1)} ${cy.toFixed(1)} ${ex.toFixed(1)} ${ey.toFixed(1)}`
})

// ----- trying it ---------------------------------------------------------------
function done() {
  if (tried.value) return
  tried.value = true
  const at = index.value
  setTimeout(() => {
    if (index.value === at && tour.value) next()
  }, 1100)
}
function onInput(e) {
  if (step.value.try !== 'type' || !target.value || !target.value.contains(e.target)) return
  if (String(e.target.value || '').trim().length >= 2) done()
}
function onClick(e) {
  if (step.value.try !== 'click' || !tryEl.value || !tryEl.value.contains(e.target)) return
  done()
}
function onKey(e) {
  if (!tour.value) return
  const typing = e.target && /^(INPUT|TEXTAREA)$/.test(e.target.tagName)
  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    end()
    return
  }
  if (typing) return
  if (e.key === 'ArrowRight' || (e.key === 'Enter' && document.activeElement === document.body)) {
    e.preventDefault()
    next()
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault()
    back()
  }
}

let frame = 0
function onMove() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(() => {
    measure()
    measureCard()
  })
}
let ticker = 0
onMounted(() => {
  window.addEventListener('resize', onMove)
  document.addEventListener('scroll', onMove, true)
  document.addEventListener('input', onInput, true)
  document.addEventListener('click', onClick, true)
  window.addEventListener('keydown', onKey, true)
  // Pages settle after they open (pictures, shelves): followed for a while.
  ticker = setInterval(onMove, 400)
  show(0)
})
onBeforeUnmount(() => {
  token++
  clearInterval(ticker)
  cancelAnimationFrame(frame)
  window.removeEventListener('resize', onMove)
  document.removeEventListener('scroll', onMove, true)
  document.removeEventListener('input', onInput, true)
  document.removeEventListener('click', onClick, true)
  window.removeEventListener('keydown', onKey, true)
})
</script>

<style scoped>
.tour {
  position: fixed;
  inset: 0;
  z-index: 1300;
  pointer-events: none;
}
.tour-dim {
  position: fixed;
  pointer-events: auto;
  background: rgb(0 0 0 / 0.62);
  transition:
    top 0.45s cubic-bezier(0.2, 0.8, 0.2, 1),
    left 0.45s cubic-bezier(0.2, 0.8, 0.2, 1),
    width 0.45s cubic-bezier(0.2, 0.8, 0.2, 1),
    height 0.45s cubic-bezier(0.2, 0.8, 0.2, 1);
}
.tour-dim.is-full {
  inset: 0;
  background: rgb(0 0 0 / 0.66);
  animation: tour-fade 0.3s ease both;
}
[data-mode='light'] .tour-dim {
  background: rgb(15 23 42 / 0.5);
}
.tour-ring {
  position: fixed;
  border-radius: 14px;
  box-shadow:
    0 0 0 2px rgb(var(--c-accent)),
    0 0 0 8px rgb(var(--c-accent) / 0.25),
    0 0 40px rgb(var(--c-accent) / 0.45);
  transition:
    top 0.45s cubic-bezier(0.2, 0.8, 0.2, 1),
    left 0.45s cubic-bezier(0.2, 0.8, 0.2, 1),
    width 0.45s cubic-bezier(0.2, 0.8, 0.2, 1),
    height 0.45s cubic-bezier(0.2, 0.8, 0.2, 1);
  animation: tour-pulse 2.2s ease-in-out infinite;
}
.tour-ring.is-try {
  animation-duration: 1.2s;
}
@keyframes tour-pulse {
  0%,
  100% {
    box-shadow:
      0 0 0 2px rgb(var(--c-accent)),
      0 0 0 8px rgb(var(--c-accent) / 0.25),
      0 0 40px rgb(var(--c-accent) / 0.45);
  }
  50% {
    box-shadow:
      0 0 0 2px rgb(var(--c-accent)),
      0 0 0 14px rgb(var(--c-accent) / 0.12),
      0 0 60px rgb(var(--c-accent) / 0.6);
  }
}
.tour-arrow {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
  pointer-events: none;
}
.tour-arrow-path {
  fill: none;
  stroke: rgb(var(--c-accent));
  stroke-width: 3;
  stroke-linecap: round;
  stroke-dasharray: 400;
  stroke-dashoffset: 400;
  filter: drop-shadow(0 2px 6px rgb(0 0 0 / 0.45));
  animation: tour-draw 0.55s 0.2s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}
.tour-arrow marker path {
  fill: rgb(var(--c-accent));
}
@keyframes tour-draw {
  to {
    stroke-dashoffset: 0;
  }
}
.tour-card {
  position: fixed;
  width: min(360px, calc(100vw - 28px));
  padding: 20px 20px 16px;
  border-radius: 18px;
  pointer-events: auto;
  background: rgb(var(--c-elev));
  color: rgb(var(--c-fg));
  box-shadow:
    0 24px 60px rgb(0 0 0 / 0.5),
    inset 0 0 0 1px rgb(var(--c-tint) / 0.1);
  animation: tour-in 0.4s cubic-bezier(0.2, 0.9, 0.25, 1.15) both;
}
.tour-card.is-center {
  width: min(420px, calc(100vw - 28px));
  text-align: center;
}
.tour-card.is-bottom {
  --from: translateY(-10px);
}
.tour-card.is-top {
  --from: translateY(10px);
}
.tour-card.is-right {
  --from: translateX(-10px);
}
.tour-card.is-left {
  --from: translateX(10px);
}
@keyframes tour-in {
  from {
    opacity: 0;
    transform: var(--from, scale(0.94));
  }
}
@keyframes tour-fade {
  from {
    opacity: 0;
  }
}
.tour-icon {
  display: inline-grid;
  width: 48px;
  height: 48px;
  margin-bottom: 10px;
  place-items: center;
  border-radius: 999px;
  background: rgb(var(--c-accent) / 0.16);
  color: rgb(var(--c-accent));
  animation: tour-bob 2.4s ease-in-out infinite;
}
@keyframes tour-bob {
  0%,
  100% {
    transform: translateY(0) rotate(0);
  }
  50% {
    transform: translateY(-3px) rotate(-6deg);
  }
}
.tour-count {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(var(--c-accent));
}
.tour-title {
  margin-top: 4px;
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.01em;
}
.tour-text {
  margin-top: 6px;
  font-size: 13.5px;
  line-height: 1.55;
  color: rgb(var(--c-fg) / 0.78);
}
.tour-try {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 12px;
  padding: 8px 11px;
  border-radius: 10px;
  background: rgb(var(--c-accent) / 0.12);
  font-size: 12.5px;
  font-weight: 700;
  color: rgb(var(--c-accent));
}
.tour-card.is-center .tour-try {
  justify-content: center;
}
.tour-try.is-done {
  background: rgb(var(--c-accent) / 0.2);
  animation: tour-pop 0.5s cubic-bezier(0.2, 0.9, 0.2, 1.4);
}
@keyframes tour-pop {
  40% {
    transform: scale(1.04);
  }
}
.tour-dots {
  display: flex;
  justify-content: center;
  gap: 5px;
  margin-top: 14px;
}
.tour-dots span {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: rgb(var(--c-tint) / 0.25);
  transition:
    width 0.3s ease,
    background-color 0.3s ease;
}
.tour-dots .is-past {
  background: rgb(var(--c-accent) / 0.5);
}
.tour-dots .is-on {
  width: 18px;
  background: rgb(var(--c-accent));
}
.tour-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
}
.tour-skip {
  font-size: 12.5px;
  font-weight: 600;
  color: rgb(var(--c-fg) / 0.55);
}
.tour-skip:hover {
  color: rgb(var(--c-fg));
  text-decoration: underline;
}
@media (prefers-reduced-motion: reduce) {
  .tour-ring,
  .tour-icon,
  .tour-card,
  .tour-arrow-path {
    animation: none;
  }
  .tour-arrow-path {
    stroke-dashoffset: 0;
  }
  .tour-dim,
  .tour-ring {
    transition: none;
  }
}
</style>
