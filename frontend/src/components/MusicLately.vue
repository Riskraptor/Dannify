<template>
  <!-- Today, this week, this month and this year, each a tile of its own
       colour: the minutes, the shape of the listening, and its moments taking
       turns (Backend listens.glance). Each opens its story. -->
  <section v-if="shown" class="lately">
    <header class="lately-head">
      <h2 class="lately-title">{{ t('story.lately') }}</h2>
      <button class="lately-more" @click="open('year')">{{ t('story.open') }}</button>
    </header>
    <div class="lately-grid">
      <button
        v-for="(p, n) in PERIODS"
        :key="p"
        class="lately-tile"
        :class="[`is-${p}`, { 'is-quiet': !glance[p].plays }]"
        :style="{ '--n': n }"
        :aria-label="`${label(p)}: ${line(p)}`"
        @click="open(p)"
        @pointerenter="held = p"
        @pointerleave="held = ''"
      >
        <span class="lately-glow" aria-hidden="true" />
        <span class="lately-top">
          <span class="lately-label">{{ label(p) }}</span>
          <CoverImage v-if="cover(p)" :src="cover(p)" radius="sm" :size="40" class="lately-cover" />
        </span>
        <span class="lately-num">
          <CountUp :value="minutes(p)" :format="number" />
          <small>{{ t('story.minutes', { count: minutes(p) }) }}</small>
        </span>
        <span class="lately-bars" aria-hidden="true">
          <i
            v-for="(h, i) in bars(p)"
            :key="i"
            :class="{ 'is-now': i === nowIndex(p), 'is-later': i > nowIndex(p) }"
            :style="{ '--h': `${h}%`, '--i': i }"
          />
        </span>
        <transition name="lately-line" mode="out-in">
          <span :key="p + turn[p]" class="lately-line">
            <Icon :icon="moment(p) ? momentIcon(moment(p)) : 'ph:play-fill'" class="lately-line-icon" />
            <span>{{ line(p) }}</span>
          </span>
        </transition>
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { coverURL } from '/src/model/playlists'
import { listensEpoch } from '/src/model/listens'
import { PERIODS, momentIcon, momentText } from '/src/model/moments'
import { dayOfWeek, weekStart } from '/src/model/weekStart'
import { away } from '/src/model/power'
import { useI18n } from '/src/i18n'
import CoverImage from '/src/components/ui/CoverImage.vue'
import CountUp from '/src/components/ui/CountUp.vue'

const { t, locale } = useI18n()
const router = useRouter()

const EMPTY = { seconds: 0, plays: 0, chart: [], insights: [], top_song: null }
const data = shallowRef(null)
const glance = computed(() => Object.fromEntries(PERIODS.map((p) => [p, (data.value && data.value[p]) || EMPTY])))
// Shown once there is anything this year to look back on.
const shown = computed(() => !!data.value && glance.value.year.plays > 0)

let asked = 0
async function load() {
  const mine = ++asked
  try {
    const res = await API.getGlance(weekStart.value)
    if (mine === asked) data.value = res.data
  } catch {
    // Not now: the tiles just are not there.
  }
}
load()
watch([listensEpoch, weekStart], load)
onActivated(load)

// Each tile's moments take turns, from a different one each visit, and stay
// put while the pointer is on the tile.
const turn = reactive(Object.fromEntries(PERIODS.map((p) => [p, Math.floor(Math.random() * 3)])))
const held = ref('')
let timer = 0
let beat = 0
function still() {
  try {
    return matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}
function start() {
  stop()
  if (still()) return
  timer = setInterval(() => {
    // Nobody looking: nothing to change.
    if (away()) return
    // One tile at a time, round the row, so they never all change at once.
    const p = PERIODS[beat++ % PERIODS.length]
    if (p !== held.value && glance.value[p].insights.filter((m) => m.kind !== 'minutes').length > 1) turn[p] += 1
  }, 2600)
}
function stop() {
  clearInterval(timer)
  timer = 0
}
onMounted(start)
onActivated(start)
onDeactivated(stop)
onBeforeUnmount(stop)

// The minutes are the tile's big number already: the moments say the rest.
function moment(p) {
  const list = glance.value[p].insights.filter((m) => m.kind !== 'minutes')
  if (list.length) return list[turn[p] % list.length]
  const song = glance.value[p].top_song
  return song ? { kind: 'top_song', song, plays: song.plays } : null
}
function line(p) {
  const m = moment(p)
  if (!m) return t(`story.startNow.${p}`)
  if (m.kind === 'top_song' && m.plays < 2) return `${m.song.title} · ${(m.song.artists || []).join(', ')}`
  return momentText(m, p, t, { number, dateText })
}
function label(p) {
  return p === 'year' ? String(new Date().getFullYear()) : t(`story.period.${p}`)
}
function minutes(p) {
  return Math.round(glance.value[p].seconds / 60)
}
function cover(p) {
  const song = glance.value[p].top_song
  return song ? coverURL(song.cover_url || (song.file ? `file:${song.file}` : '')) : ''
}
// The shape of the listening: hours of today, days of the week and the
// month, months of the year; what is still to come, faint.
function bars(p) {
  const chart = glance.value[p].chart
  const top = Math.max(1, ...chart)
  return chart.map((s) => (s ? Math.max(8, Math.round((s / top) * 100)) : 4))
}
function nowIndex(p) {
  const d = new Date()
  if (p === 'day') return d.getHours()
  if (p === 'week') return dayOfWeek(d)
  if (p === 'month') return d.getDate() - 1
  return d.getMonth()
}
function open(p) {
  router.push(p === 'year' ? { name: 'Recap' } : { name: 'Recap', query: { period: p } })
}

const formatter = computed(() => new Intl.NumberFormat(locale.value || 'en'))
function number(n) {
  return formatter.value.format(n || 0)
}
function dateText(iso) {
  const [y, m, d] = String(iso).split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(locale.value || 'en', { day: 'numeric', month: 'long' })
}
</script>

<style scoped>
.lately {
  margin-bottom: 30px;
  container-type: inline-size;
}
.lately-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
  padding: 0 10px;
}
.lately-title {
  font-size: 21px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.lately-more {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--c-fg) / var(--fg-55));
}
.lately-more:hover {
  color: rgb(var(--c-fg));
  text-decoration: underline;
}
/* Four in a row, or two by two: never three and one left over. */
.lately-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 0 10px;
}
@container (min-width: 720px) {
  .lately-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
  .lately-num {
    font-size: clamp(26px, 3.9cqi, 36px);
  }
}
@container (max-width: 380px) {
  .lately-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
/* Each stretch in its own colour, the same the story opens in. */
.lately-tile {
  --a: #ff8a3c;
  --b: #e5306b;
  position: relative;
  isolation: isolate;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 178px;
  padding: 14px 16px 14px;
  overflow: hidden;
  border-radius: 18px;
  color: #fff;
  text-align: left;
  background: linear-gradient(140deg, var(--a), var(--b));
  box-shadow: 0 10px 28px -12px color-mix(in srgb, var(--b) 70%, transparent);
  transition:
    transform 0.2s cubic-bezier(0.2, 0.9, 0.2, 1.2),
    box-shadow 0.2s ease;
  animation: lately-in 0.5s cubic-bezier(0.2, 0.9, 0.2, 1.1) both;
  animation-delay: calc(var(--n) * 70ms);
}
.lately-tile.is-week {
  --a: #0fb5a6;
  --b: #2459d6;
}
.lately-tile.is-month {
  --a: #7c4dff;
  --b: #d03fd0;
}
.lately-tile.is-year {
  --a: #4a1260;
  --b: #ff6f3c;
}
.lately-tile:hover {
  transform: translateY(-4px);
  box-shadow: 0 18px 36px -14px color-mix(in srgb, var(--b) 80%, transparent);
}
.lately-tile:active {
  transform: translateY(-1px) scale(0.99);
}
.lately-tile:focus-visible {
  outline: 2px solid rgb(var(--c-fg));
  outline-offset: 3px;
}
.lately-glow {
  position: absolute;
  inset: -40% -30% auto auto;
  z-index: -1;
  width: 70%;
  aspect-ratio: 1;
  border-radius: 999px;
  background: radial-gradient(circle, rgb(255 255 255 / 0.35), transparent 65%);
  transition: transform 0.6s ease;
  pointer-events: none;
}
/* Its light moves only while the pointer is on it: a page left open costs
   nothing to look at. */
.lately-tile:hover .lately-glow {
  animation: lately-float 3.5s ease-in-out infinite alternate;
}
.lately-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.lately-label {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgb(255 255 255 / 0.85);
}
.lately-cover {
  width: 40px;
  height: 40px;
  flex: none;
  box-shadow: 0 6px 16px rgb(0 0 0 / 0.3);
  transform: rotate(4deg);
  transition: transform 0.25s ease;
}
.lately-tile:hover .lately-cover {
  transform: rotate(-3deg) scale(1.06);
}
.lately-num {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 6px;
  margin-top: -6px;
  font-size: 34px;
  font-weight: 900;
  line-height: 1;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
}
.lately-num small {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0;
  color: rgb(255 255 255 / 0.8);
}
.lately-bars {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 30px;
}
.lately-bars i {
  flex: 1;
  height: var(--h);
  min-width: 2px;
  border-radius: 2px;
  background: rgb(255 255 255 / 0.55);
  transform-origin: bottom;
  animation: lately-grow 0.6s ease both;
  animation-delay: calc(var(--n) * 70ms + var(--i) * 12ms + 150ms);
}
.lately-bars i.is-now {
  background: #fff;
  box-shadow: 0 0 10px rgb(255 255 255 / 0.8);
}
.lately-bars i.is-later {
  background: rgb(255 255 255 / 0.18);
}
.lately-line {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  min-height: 2.6em;
  font-size: 12.5px;
  font-weight: 650;
  line-height: 1.3;
}
.lately-line > span {
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.lately-line-icon {
  flex: none;
  width: 15px;
  height: 15px;
  margin-top: 1px;
}
.lately-tile.is-quiet .lately-line {
  color: rgb(255 255 255 / 0.85);
  font-style: italic;
}
.lately-line-enter-active,
.lately-line-leave-active {
  transition:
    opacity 0.3s ease,
    transform 0.3s ease;
}
.lately-line-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.lately-line-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
@keyframes lately-in {
  from {
    opacity: 0;
    transform: translateY(14px) scale(0.97);
  }
}
@keyframes lately-grow {
  from {
    transform: scaleY(0);
  }
}
@keyframes lately-float {
  to {
    transform: translate(-30%, 25%) scale(1.2);
  }
}
@media (prefers-reduced-motion: reduce) {
  .lately-tile,
  .lately-glow,
  .lately-bars i {
    animation: none;
  }
}
</style>
