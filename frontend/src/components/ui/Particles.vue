<template>
  <!-- A special day's weather (model/occasions.js), drawn by the compositor
       alone: each piece is moved or faded, never repainted. For someone whose
       system asks for less motion it is all there, holding still. -->
  <div
    class="ptl"
    :class="[`is-${look.shape}`, `go-${look.motion}`, { 'is-contained': contain, 'is-still': still }]"
    :style="{ '--fall': fall }"
    aria-hidden="true"
  >
    <template v-if="look.motion === 'burst'">
      <span v-for="b in bursts" :key="b.id" class="ptl-burst" :style="b.style">
        <i v-for="s in b.sparks" :key="s.id" class="ptl-spark" :style="s.style" />
      </span>
    </template>
    <template v-else>
      <i v-for="p in pieces" :key="p.id" class="ptl-p" :class="{ 'is-pale': p.pale }" :style="p.style" />
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { prefersStill } from '/src/model/occasions'

const props = defineProps({
  // { shape, motion, palette }, as model/occasions.js gives it.
  look: { type: Object, default: () => ({ shape: 'dot', motion: 'fall', palette: ['#ffffff'] }) },
  count: { type: Number, default: 40 },
  // Within the nearest positioned parent instead of over the whole window.
  contain: { type: Boolean, default: false },
  // How far a piece travels: the window's height, or the parent's.
  fall: { type: String, default: '110vh' },
})

const still = prefersStill()
const rnd = (a, b) => a + Math.random() * (b - a)
// White and near-white pieces vanish on a light page: they go a pale blue
// there (see is-pale).
function pale(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || ''))
  if (!m) return false
  const n = parseInt(m[1], 16)
  const lum = (0.2126 * (n >> 16) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255
  return lum > 0.86
}

// Size of a piece, by what it is.
const SIZES = {
  dot: [3, 8],
  ribbon: [7, 7],
  heart: [10, 18],
  star: [8, 16],
  note: [12, 20],
  leaf: [12, 20],
  petal: [9, 15],
  clover: [11, 18],
  lantern: [14, 24],
  flame: [9, 15],
  puff: [70, 150],
  crescent: [11, 19],
  egg: [10, 16],
  drop: [7, 12],
  bat: [16, 26],
  lotus: [15, 24],
  flower: [11, 18],
}
// How long a piece takes, by how it moves. Every special day has its own
// shape and movement (packaging/make_occasions.py, LOOKS):
//   fall     straight down, turning           (honey drops)
//   sway     down, side to side               (snow, leaves, eggs, flowers)
//   flutter  down, flipping over              (petals, flag ribbons)
//   shimmer  slowly down, glinting            (Eid's stars)
//   rise     up                               (hearts, sky lanterns, flames)
//   spiral   up, weaving                      (music notes, violets)
//   bob      floating where it is             (lotus, lanterns, red eggs)
//   swing    hanging, swinging                (Lunar New Year's lanterns)
//   twinkle  where it is, growing and fading  (crescents)
//   flicker  low down, a flame's flutter      (Diwali's lamps)
//   flit     across, wings beating            (Halloween's bats)
//   drift    big and soft, spreading          (Holi's colour)
//   burst    fireworks                        (the New Year)
const SECONDS = {
  fall: [6, 13],
  sway: [9, 16],
  flutter: [7, 13],
  shimmer: [10, 16],
  rise: [7, 14],
  spiral: [8, 14],
  bob: [2.4, 4],
  swing: [2, 3.4],
  twinkle: [2.2, 4.4],
  flicker: [0.9, 1.6],
  flit: [7, 12],
  drift: [5, 9],
}
const SPINS = new Set(['ribbon', 'leaf', 'petal', 'flower'])

const pieces = computed(() => {
  const { shape, motion } = props.look
  const palette = props.look.palette && props.look.palette.length ? props.look.palette : ['#ffffff']
  const [s0, s1] = SIZES[shape] || [8, 14]
  const [d0, d1] = SECONDS[motion] || SECONDS.fall
  return Array.from({ length: props.count }, (_, id) => {
    const colour = palette[id % palette.length]
    const style = {
      '--x': `${rnd(0, 100).toFixed(1)}%`,
      '--y': `${rnd(2, 92).toFixed(1)}%`,
      '--drift': `${rnd(-40, 40).toFixed(0)}px`,
      '--d': `${rnd(d0, d1).toFixed(1)}s`,
      // The side-to-side, the glint, the beat of a wing: a period of its own.
      '--sd': `${rnd(2.2, 4.5).toFixed(1)}s`,
      '--delay': `${(-rnd(0, 14)).toFixed(1)}s`,
      '--o': (shape === 'dot' ? rnd(0.45, 0.9) : shape === 'puff' ? rnd(0.18, 0.32) : rnd(0.75, 1)).toFixed(2),
      '--s': `${rnd(s0, s1).toFixed(1)}px`,
      '--r0': `${rnd(-30, 30).toFixed(0)}deg`,
      '--r': `${rnd(-40, 40) + (SPINS.has(shape) ? rnd(300, 720) : 0)}deg`,
      '--c': colour,
    }
    return { id, style, pale: pale(colour) }
  })
})

// Fireworks: bursts here and there, one after another.
const bursts = computed(() => {
  const palette = props.look.palette && props.look.palette.length ? props.look.palette : ['#ffd166']
  const n = Math.max(3, Math.round(props.count / 10))
  return Array.from({ length: n }, (_, id) => {
    const colour = palette[id % palette.length]
    const reach = rnd(40, 90)
    const period = rnd(2.4, 3.8)
    return {
      id,
      style: {
        '--x': `${rnd(8, 92).toFixed(1)}%`,
        '--y': `${rnd(8, 62).toFixed(1)}%`,
        '--d': `${period.toFixed(2)}s`,
        '--delay': `${(-rnd(0, period)).toFixed(2)}s`,
        '--reach': `${reach.toFixed(0)}px`,
        '--c': colour,
      },
      sparks: Array.from({ length: 14 }, (_, k) => ({
        id: k,
        style: { '--a': `${(k * 360) / 14 + rnd(-6, 6)}deg` },
      })),
    }
  })
})
</script>

<style scoped>
.ptl {
  position: fixed;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: 0;
}
.ptl.is-contained {
  position: absolute;
}

/* --- A piece ------------------------------------------------------------- */
.ptl-p {
  position: absolute;
  top: -24px;
  left: var(--x);
  width: var(--s);
  height: var(--s);
  background: var(--c);
  opacity: var(--o);
  will-change: transform, opacity;
  animation: var(--d) linear var(--delay) infinite;
}
[data-mode='light'] .ptl-p.is-pale {
  background: rgb(150 180 215);
}
.is-dot .ptl-p {
  border-radius: 50%;
}
.is-ribbon .ptl-p {
  width: 7px;
  height: 11px;
  border-radius: 2px;
}
.is-puff .ptl-p {
  border-radius: 50%;
  background: radial-gradient(closest-side, var(--c), transparent);
}
/* Shapes: the colour, cut out by an outline. */
.is-heart .ptl-p,
.is-star .ptl-p,
.is-note .ptl-p,
.is-leaf .ptl-p,
.is-petal .ptl-p,
.is-clover .ptl-p,
.is-lantern .ptl-p,
.is-flame .ptl-p,
.is-crescent .ptl-p,
.is-egg .ptl-p,
.is-drop .ptl-p,
.is-bat .ptl-p,
.is-lotus .ptl-p,
.is-flower .ptl-p {
  -webkit-mask: var(--shape) center / contain no-repeat;
  mask: var(--shape) center / contain no-repeat;
}
.is-heart {
  --shape: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54z'/%3E%3C/svg%3E");
}
.is-star {
  --shape: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 0c.6 5.4 2.6 9.4 12 12-9.4 2.6-11.4 6.6-12 12-.6-5.4-2.6-9.4-12-12 9.4-2.6 11.4-6.6 12-12z'/%3E%3C/svg%3E");
}
.is-note {
  --shape: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 3v10.55A4 4 0 1 0 14 17V7h4V3z'/%3E%3C/svg%3E");
}
.is-leaf {
  --shape: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M3 21C3 10 9 3 21 3c0 12-7 18-18 18zm2-2l9-9'/%3E%3C/svg%3E");
}
.is-petal {
  --shape: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 2C8 6 7 11 7 14a5 5 0 0 0 10 0c0-3-1-8-5-12z'/%3E%3C/svg%3E");
}
.is-clover {
  --shape: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M7.8 7a4.2 4.2 0 1 0 8.4 0 4.2 4.2 0 1 0-8.4 0zM3.4 14a4.2 4.2 0 1 0 8.4 0 4.2 4.2 0 1 0-8.4 0zM12.2 14a4.2 4.2 0 1 0 8.4 0 4.2 4.2 0 1 0-8.4 0zM11.3 15h1.4v8h-1.4z'/%3E%3C/svg%3E");
}
.is-lantern {
  --shape: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M10 1h4v2h-4zM6 7c0-2.2 2.7-3.5 6-3.5S18 4.8 18 7v9c0 2.2-2.7 3.5-6 3.5S6 18.2 6 16zM9.5 20h5v1.5h-5zM11.4 21.5h1.2V24h-1.2z'/%3E%3C/svg%3E");
}
.is-flame {
  --shape: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 1c1.5 3.6 6 6.6 6 12a6 6 0 0 1-12 0c0-3.2 1.7-5.3 3-6.8.2 2 1 3.3 2.3 3.8C11.9 7.5 11.5 4.3 12 1z'/%3E%3C/svg%3E");
}

.is-crescent {
  --shape: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M15 2.5A9.6 9.6 0 1 0 21.5 19 7.8 7.8 0 1 1 15 2.5z'/%3E%3C/svg%3E");
}
.is-egg {
  --shape: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 1.5C7.7 1.5 4.5 8.6 4.5 14a7.5 7.5 0 0 0 15 0c0-5.4-3.2-12.5-7.5-12.5z'/%3E%3C/svg%3E");
}
.is-drop {
  --shape: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 1.5S5 10 5 15a7 7 0 0 0 14 0c0-5-7-13.5-7-13.5z'/%3E%3C/svg%3E");
}
.is-bat {
  --shape: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 8.2c-.6 0-1 .3-1.3.8l-.6-1.2-.6 1.3C7.8 8.4 5 8.6 1 7.6c1.6 1.2 2.6 3 2.4 5.2 1.7-1.3 3.6-1.4 5.2-.4.4 1.5 1.3 2.6 2.4 3.4.3-.8.6-1.1 1-1.1s.7.3 1 1.1c1.1-.8 2-1.9 2.4-3.4 1.6-1 3.5-.9 5.2.4-.2-2.2.8-4 2.4-5.2-4 1-6.8.8-8.5-.5l-.6-1.3-.6 1.2c-.3-.5-.7-.8-1.3-.8z'/%3E%3C/svg%3E");
}
.is-lotus {
  --shape: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 3.5c-2 2.4-3 4.9-3 7.4 0 2 1 3.6 3 4.6 2-1 3-2.6 3-4.6 0-2.5-1-5-3-7.4zM3.5 9.5c.4 3.6 2.5 6.1 6.6 6.9-1.5-1.7-2.2-3.5-2.2-5.2-1.4-.9-2.8-1.5-4.4-1.7zm17 0c-1.6.2-3 .8-4.4 1.7 0 1.7-.7 3.5-2.2 5.2 4.1-.8 6.2-3.3 6.6-6.9zM2.5 16.5c2.5 2.2 5.7 3.3 9.5 3.3s7-1.1 9.5-3.3c-2.9.7-6.1 1-9.5 1s-6.6-.3-9.5-1z'/%3E%3C/svg%3E");
}
.is-flower {
  --shape: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 2a3.6 3.6 0 0 1 3.4 4.8 3.6 3.6 0 1 1 1.3 6.3 3.6 3.6 0 1 1-4.7 4.3 3.6 3.6 0 1 1-4.7-4.3 3.6 3.6 0 1 1 1.3-6.3A3.6 3.6 0 0 1 12 2zm0 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4z'/%3E%3C/svg%3E");
}

/* --- How it moves ---------------------------------------------------------- */
/* Two movements at once where a piece both travels and sways, flips or
   glints: the journey on `translate`, the rest on `transform`, each with a
   period of its own, so neither stutters the other. */
.go-sway .ptl-p {
  animation:
    ptl-down var(--d) linear var(--delay) infinite,
    ptl-side var(--sd) ease-in-out var(--delay) infinite alternate;
}
.go-flutter .ptl-p {
  animation:
    ptl-down var(--d) linear var(--delay) infinite,
    ptl-flip var(--d) linear var(--delay) infinite;
}
.go-shimmer .ptl-p {
  animation:
    ptl-down var(--d) linear var(--delay) infinite,
    ptl-side var(--sd) ease-in-out var(--delay) infinite alternate,
    ptl-glint calc(var(--sd) * 0.6) ease-in-out var(--delay) infinite;
}
.go-spiral .ptl-p {
  top: auto;
  bottom: -28px;
  animation:
    ptl-up var(--d) linear var(--delay) infinite,
    ptl-side calc(var(--sd) * 0.6) ease-in-out var(--delay) infinite alternate;
}
.go-bob .ptl-p,
.go-swing .ptl-p,
.go-flicker .ptl-p,
.go-flit .ptl-p {
  top: var(--y);
}
.go-bob .ptl-p {
  animation: ptl-bob var(--d) ease-in-out var(--delay) infinite alternate;
}
/* Hung from above, in the top part of the window. */
.go-swing .ptl-p {
  top: calc(var(--y) * 0.4);
  transform-origin: 50% -70%;
  animation: ptl-swing var(--d) ease-in-out var(--delay) infinite alternate;
}
/* Lamps along the lower part of the window. */
.go-flicker .ptl-p {
  top: calc(52% + var(--y) / 2);
  transform-origin: 50% 100%;
  animation: ptl-flicker var(--d) ease-in-out var(--delay) infinite;
}
.go-flit .ptl-p {
  animation:
    ptl-flit var(--d) ease-in-out var(--delay) infinite,
    ptl-flap 0.32s ease-in-out var(--delay) infinite alternate;
}
@keyframes ptl-down {
  from {
    translate: 0 0;
  }
  to {
    translate: 0 var(--fall);
  }
}
@keyframes ptl-up {
  0% {
    translate: 0 0;
    opacity: 0;
  }
  12%,
  85% {
    opacity: var(--o);
  }
  100% {
    translate: 0 calc(-1 * var(--fall) - 56px);
    opacity: 0;
  }
}
@keyframes ptl-side {
  from {
    transform: translateX(calc(var(--drift) * -1)) rotate(var(--r0));
  }
  to {
    transform: translateX(var(--drift)) rotate(calc(var(--r0) * -1));
  }
}
@keyframes ptl-flip {
  from {
    transform: rotate(var(--r0)) rotate3d(1, 0.3, 0, 0deg);
  }
  to {
    transform: rotate(var(--r)) rotate3d(1, 0.3, 0, 720deg);
  }
}
@keyframes ptl-glint {
  0%,
  100% {
    opacity: 0.25;
  }
  50% {
    opacity: var(--o);
  }
}
@keyframes ptl-bob {
  from {
    transform: translateY(-9px) rotate(calc(var(--r0) * 0.3));
  }
  to {
    transform: translateY(9px) rotate(calc(var(--r0) * -0.3));
  }
}
@keyframes ptl-swing {
  from {
    transform: rotate(-13deg);
  }
  to {
    transform: rotate(13deg);
  }
}
@keyframes ptl-flicker {
  0%,
  100% {
    transform: scale(1, 1);
    opacity: var(--o);
  }
  22% {
    transform: scale(0.92, 1.1);
    opacity: 0.8;
  }
  48% {
    transform: scale(1.06, 0.93);
    opacity: 1;
  }
  74% {
    transform: scale(0.95, 1.12);
    opacity: 0.85;
  }
}
@keyframes ptl-flit {
  0% {
    transform: translate3d(-14vw, 0, 0);
    opacity: 0;
  }
  10%,
  90% {
    opacity: var(--o);
  }
  30% {
    transform: translate3d(-5vw, -26px, 0);
  }
  55% {
    transform: translate3d(4vw, 14px, 0);
  }
  80% {
    transform: translate3d(12vw, -18px, 0);
  }
  100% {
    transform: translate3d(18vw, 0, 0);
    opacity: 0;
  }
}
@keyframes ptl-flap {
  from {
    scale: 1 1;
  }
  to {
    scale: 1 0.55;
  }
}
.go-fall .ptl-p {
  animation-name: ptl-fall;
}
.is-dot.go-fall .ptl-p {
  animation-name: ptl-snow;
}
.go-rise .ptl-p {
  top: auto;
  bottom: -28px;
  animation-name: ptl-rise;
}
.go-twinkle .ptl-p,
.go-drift .ptl-p {
  top: var(--y);
  animation-name: ptl-twinkle;
  animation-timing-function: ease-in-out;
}
.go-drift .ptl-p {
  animation-name: ptl-drift;
}
@keyframes ptl-snow {
  to {
    transform: translate3d(var(--drift), var(--fall), 0);
  }
}
@keyframes ptl-fall {
  from {
    transform: translate3d(0, 0, 0) rotate(var(--r0));
  }
  to {
    transform: translate3d(var(--drift), var(--fall), 0) rotate(var(--r));
  }
}
@keyframes ptl-rise {
  0% {
    transform: translate3d(0, 0, 0) rotate(var(--r0));
    opacity: 0;
  }
  12% {
    opacity: var(--o);
  }
  80% {
    opacity: var(--o);
  }
  100% {
    transform: translate3d(var(--drift), calc(-1 * var(--fall) - 56px), 0) rotate(calc(var(--r0) * -1));
    opacity: 0;
  }
}
@keyframes ptl-twinkle {
  0%,
  100% {
    transform: scale(0.35) rotate(var(--r0));
    opacity: 0.15;
  }
  50% {
    transform: scale(1) rotate(var(--r0));
    opacity: var(--o);
  }
}
@keyframes ptl-drift {
  0% {
    transform: translate3d(0, 0, 0) scale(0.6);
    opacity: 0;
  }
  50% {
    opacity: var(--o);
  }
  100% {
    transform: translate3d(var(--drift), -30px, 0) scale(1.25);
    opacity: 0;
  }
}

/* --- Fireworks ------------------------------------------------------------- */
.ptl-burst {
  position: absolute;
  left: var(--x);
  top: var(--y);
  width: 0;
  height: 0;
}
.ptl-spark {
  position: absolute;
  left: -2px;
  top: -2px;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--c);
  box-shadow: 0 0 6px var(--c);
  will-change: transform, opacity;
  animation: ptl-burst var(--d) cubic-bezier(0.15, 0.7, 0.3, 1) var(--delay) infinite;
}
@keyframes ptl-burst {
  0% {
    transform: rotate(var(--a)) translateX(0) scale(0.6);
    opacity: 0;
  }
  8% {
    opacity: 1;
  }
  55% {
    transform: rotate(var(--a)) translateX(var(--reach)) scale(1);
    opacity: 0.9;
  }
  80%,
  100% {
    transform: rotate(var(--a)) translate(var(--reach), 18px) scale(0.4);
    opacity: 0;
  }
}

/* --- Still, for less motion ------------------------------------------------ */
/* Everything stays where it would be partway through, and stays. */
.is-still .ptl-p {
  animation: none;
  top: var(--y);
  bottom: auto;
  translate: none;
  scale: none;
  transform: rotate(var(--r0));
}
.is-still.go-twinkle .ptl-p,
.is-still.go-drift .ptl-p {
  transform: scale(0.8) rotate(var(--r0));
}
.is-still .ptl-spark {
  animation: none;
  transform: rotate(var(--a)) translateX(calc(var(--reach) * 0.55));
  opacity: 0.85;
}
</style>
