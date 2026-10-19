<template>
  <div class="recap" tabindex="-1">
    <div class="recap-glow" aria-hidden="true" />

    <header class="recap-top">
      <button class="icon-btn recap-btn" :title="t('common.close')" :aria-label="t('common.close')" @click="close">
        <Icon icon="ph:x" class="h-5 w-5" />
      </button>
      <div v-if="slides.length > 1" class="recap-steps" aria-hidden="true">
        <span v-for="(s, i) in slides" :key="s.id" class="recap-step" :class="{ 'is-done': i <= at }" />
      </div>
      <select
        v-if="data && data.years && data.years.length > 1"
        class="recap-year"
        :value="year"
        :aria-label="t('recap.pickYear')"
        @change="router.replace({ name: 'Recap', params: { year: $event.target.value } })"
      >
        <option v-for="y in data.years" :key="y" :value="y">{{ y }}</option>
      </select>
    </header>

    <div v-if="state === 'loading'" class="recap-center">
      <span class="spinner h-8 w-8" />
    </div>

    <div v-else-if="state === 'error'" class="recap-center">
      <p class="recap-small">{{ t('recap.failed') }}</p>
      <button class="recap-cta" @click="load">{{ t('common.retry') }}</button>
    </div>

    <div v-else-if="!data || !data.plays" class="recap-center">
      <p class="recap-eyebrow">{{ year }}</p>
      <h1 class="recap-big">{{ t('recap.emptyTitle') }}</h1>
      <p class="recap-small">{{ t('recap.emptyText') }}</p>
    </div>

    <template v-else>
      <transition :name="direction > 0 ? 'slide-next' : 'slide-prev'" mode="out-in">
        <section :key="slide.id" class="recap-slide" @click="onSlideClick">
          <template v-if="slide.id === 'intro'">
            <p class="recap-eyebrow">{{ t('recap.eyebrow') }}</p>
            <h1 class="recap-huge">{{ year }}</h1>
            <p class="recap-lead">{{ t('recap.intro') }}</p>
            <button class="recap-cta" @click.stop="go(1)">
              {{ t('recap.start') }} <Icon icon="ph:arrow-right-bold" class="h-4 w-4" />
            </button>
          </template>

          <template v-else-if="slide.id === 'minutes'">
            <p class="recap-eyebrow">{{ t('recap.minutesEyebrow') }}</p>
            <h1 class="recap-huge">{{ number(Math.round(data.seconds / 60)) }}</h1>
            <p class="recap-lead">{{ t('recap.minutesUnit') }}</p>
            <p class="recap-small">{{ t('recap.minutesDetail', { plays: number(data.plays), days: data.days }) }}</p>
          </template>

          <template v-else-if="slide.id === 'artist'">
            <p class="recap-eyebrow">{{ t('recap.topArtist') }}</p>
            <div class="recap-portrait">
              <CoverImage :src="artistPicture" kind="artist" round :size="220" class="h-full w-full" eager />
            </div>
            <h1 class="recap-big">{{ topArtist.name }}</h1>
            <p class="recap-small">{{ t('recap.together', { minutes: number(Math.round(topArtist.seconds / 60)) }) }}</p>
          </template>

          <template v-else-if="slide.id === 'songs'">
            <p class="recap-eyebrow">{{ t('recap.topSongs') }}</p>
            <ol class="recap-list">
              <li v-for="(row, i) in songRows" :key="row.key" class="recap-row" :style="{ '--i': i }">
                <span class="recap-rank">{{ i + 1 }}</span>
                <CoverImage :src="row.cover" radius="sm" :size="56" class="recap-thumb" />
                <span class="min-w-0 flex-1">
                  <span class="recap-row-title">{{ row.title }}</span>
                  <span class="recap-row-sub">{{ row.artistText }}</span>
                </span>
                <span class="recap-row-count">{{ t('stats.playCount', { count: data.top_songs[i].plays }) }}</span>
              </li>
            </ol>
          </template>

          <template v-else-if="slide.id === 'albums'">
            <p class="recap-eyebrow">{{ t('recap.topAlbums') }}</p>
            <div class="recap-albums">
              <figure v-for="(a, i) in data.top_albums" :key="a.name + a.artist" class="recap-album" :style="{ '--i': i }">
                <CoverImage :src="coverURL(a.cover)" kind="album" radius="md" :size="160" class="recap-album-art" />
                <figcaption>
                  <span class="recap-row-title">{{ a.name }}</span>
                  <span class="recap-row-sub">{{ a.artist }}</span>
                </figcaption>
              </figure>
            </div>
          </template>

          <template v-else-if="slide.id === 'habits'">
            <p class="recap-eyebrow">{{ t('recap.habits') }}</p>
            <div class="recap-facts">
              <div v-if="data.peak_hour != null" class="recap-fact">
                <Icon icon="ph:clock" class="recap-fact-icon" />
                <p class="recap-fact-value">{{ hourText(data.peak_hour, locale) }}</p>
                <p class="recap-fact-label">{{ t('recap.peakHour') }}</p>
              </div>
              <div class="recap-fact">
                <Icon icon="ph:flame" class="recap-fact-icon" />
                <p class="recap-fact-value">{{ t('recap.daysValue', { count: data.longest_streak }) }}</p>
                <p class="recap-fact-label">{{ t('recap.streak') }}</p>
              </div>
              <div v-if="data.busiest_day" class="recap-fact">
                <Icon icon="ph:calendar-star" class="recap-fact-icon" />
                <p class="recap-fact-value">{{ dayText(data.busiest_day.date) }}</p>
                <p class="recap-fact-label">
                  {{ t('recap.busiest', { minutes: number(Math.round(data.busiest_day.seconds / 60)) }) }}
                </p>
              </div>
            </div>
          </template>

          <template v-else-if="slide.id === 'discovery'">
            <p class="recap-eyebrow">{{ t('recap.discovery') }}</p>
            <h1 class="recap-huge">{{ number(data.new_artists) }}</h1>
            <p class="recap-lead">{{ t('recap.newArtists', { count: data.new_artists }) }}</p>
            <div class="recap-months" role="img" :aria-label="t('recap.monthsLabel')">
              <span
                v-for="(secs, m) in data.months"
                :key="m"
                class="recap-month"
                :style="{ '--h': `${Math.max(4, (secs / maxMonth) * 100)}%`, '--i': m }"
                :title="monthText(m)"
              />
            </div>
          </template>

          <template v-else-if="slide.id === 'outro'">
            <p class="recap-eyebrow">{{ year }}</p>
            <h1 class="recap-big">{{ t('recap.thanks') }}</h1>
            <p class="recap-lead">{{ t('recap.outro') }}</p>
            <button class="recap-cta" :disabled="!songRows.length" @click.stop="playTop">
              <Icon icon="ph:play-fill" class="h-4 w-4" /> {{ t('recap.playTop') }}
            </button>
          </template>
        </section>
      </transition>

      <nav class="recap-nav">
        <button class="icon-btn recap-btn" :disabled="at === 0" :aria-label="t('recap.previous')" @click="go(-1)">
          <Icon icon="ph:caret-left-bold" class="h-5 w-5" />
        </button>
        <button class="icon-btn recap-btn" :disabled="at >= slides.length - 1" :aria-label="t('recap.next')" @click="go(1)">
          <Icon icon="ph:caret-right-bold" class="h-5 w-5" />
        </button>
      </nav>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { coverURL, entryRow } from '/src/model/playlists'
import { useArtistLinks } from '/src/model/artistLinks'
import { playRows } from '/src/model/tracks'
import { hourText } from '/src/model/statsFormat'
import { useI18n } from '/src/i18n'
import CoverImage from '/src/components/ui/CoverImage.vue'

// "Your year in music": the year's listening as a few slides to step
// through, made from the app's own history (Backend listens.recap).

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const year = computed(() => Number(route.params.year) || new Date().getFullYear())
const data = shallowRef(null)
const state = ref('loading')
const at = ref(0)
const direction = ref(1)
let asked = 0

async function load() {
  const mine = ++asked
  state.value = 'loading'
  try {
    const res = await API.getRecap(year.value)
    if (mine !== asked) return
    data.value = res.data
    state.value = 'ready'
    at.value = 0
  } catch {
    if (mine === asked) state.value = 'error'
  }
}
watch(year, load, { immediate: true })

const topArtist = computed(() => (data.value && data.value.top_artists[0]) || null)
// The artist's own photo where the app knows it, else the cover of their song.
const artistLinks = useArtistLinks()
const artistPicture = computed(() => {
  const a = topArtist.value
  return a ? artistLinks.artistPhoto(a.name, 440) || coverURL(a.cover) : ''
})
const songRows = computed(() => ((data.value && data.value.top_songs) || []).map(entryRow))
const maxMonth = computed(() => Math.max(1, ...((data.value && data.value.months) || [0])))

const slides = computed(() => {
  const d = data.value
  if (!d || !d.plays) return []
  const out = [{ id: 'intro' }, { id: 'minutes' }]
  if (topArtist.value) out.push({ id: 'artist' })
  if (d.top_songs.length) out.push({ id: 'songs' })
  if (d.top_albums.length) out.push({ id: 'albums' })
  out.push({ id: 'habits' })
  if (d.new_artists) out.push({ id: 'discovery' })
  out.push({ id: 'outro' })
  return out
})
const slide = computed(() => slides.value[Math.min(at.value, slides.value.length - 1)] || { id: 'intro' })

function go(step) {
  const next = Math.max(0, Math.min(slides.value.length - 1, at.value + step))
  if (next === at.value) return
  direction.value = step
  at.value = next
}

function onSlideClick(e) {
  // The right two thirds steps on, the left third back: how stories work.
  const box = e.currentTarget.getBoundingClientRect()
  go(e.clientX - box.left < box.width / 3 ? -1 : 1)
}

// The arrows step through the story wherever the focus is, ahead of the
// player's own (which would seek the song): the window hears them first, and
// a key handled here is marked so the player leaves it alone.
function onKey(e) {
  if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return
  const el = e.target
  const tag = (el && el.tagName) || ''
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (el && el.isContentEditable)) return
  // Space on a button presses it; anywhere else it steps on.
  const onButton = tag === 'BUTTON' || tag === 'A'
  if (e.key === 'ArrowRight' || (e.key === ' ' && !onButton)) {
    e.preventDefault()
    go(1)
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault()
    go(-1)
  } else if (e.key === 'Escape') {
    e.preventDefault()
    close()
  }
}
onMounted(() => window.addEventListener('keydown', onKey, true))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey, true))

function close() {
  if (window.history.length > 1) router.back()
  else router.push({ name: 'Stats' })
}

function playTop() {
  if (songRows.value.length) playRows(songRows.value, 0)
}

const formatter = computed(() => new Intl.NumberFormat(locale.value || 'en'))
function number(n) {
  return formatter.value.format(n || 0)
}
function dayText(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(locale.value || 'en', { day: 'numeric', month: 'long' })
}
function monthText(m) {
  return new Date(year.value, m, 1).toLocaleDateString(locale.value || 'en', { month: 'long' })
}
</script>

<style scoped>
.recap {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 100%;
  overflow: hidden;
  color: #fff;
  outline: none;
  background: linear-gradient(130deg, #2b0d4a, #6b1d6e 40%, #c2185b 75%, #ff6f3c);
  background-size: 220% 220%;
  animation: recap-shift 18s ease-in-out infinite alternate;
  --c-fg: 255 255 255;
  --c-tint: 255 255 255;
}
.recap-glow {
  position: absolute;
  inset: -20%;
  background:
    radial-gradient(40% 35% at 20% 25%, rgb(255 255 255 / 0.16), transparent 70%),
    radial-gradient(45% 40% at 80% 75%, rgb(255 190 120 / 0.18), transparent 70%);
  animation: recap-float 14s ease-in-out infinite alternate;
  pointer-events: none;
}
@keyframes recap-shift {
  from {
    background-position: 0% 30%;
  }
  to {
    background-position: 100% 70%;
  }
}
@keyframes recap-float {
  from {
    transform: translate(0, 0) scale(1);
  }
  to {
    transform: translate(3%, -2%) scale(1.06);
  }
}
.recap-top {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px 0;
}
.recap-steps {
  display: flex;
  flex: 1;
  gap: 5px;
}
.recap-step {
  flex: 1;
  height: 3px;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.28);
  transition: background-color 0.3s ease;
}
.recap-step.is-done {
  background: #fff;
}
.recap-year {
  height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgb(255 255 255 / 0.3);
  background: rgb(0 0 0 / 0.2);
  color: #fff;
  font-weight: 600;
}
.recap-btn {
  color: rgb(255 255 255 / 0.85);
}
.recap-btn:hover:not(:disabled) {
  color: #fff;
  background: rgb(255 255 255 / 0.14);
}
.recap-center,
.recap-slide {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px clamp(20px, 6vw, 72px);
  text-align: center;
}
.recap-slide {
  cursor: pointer;
  user-select: none;
}
.recap-eyebrow {
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgb(255 255 255 / 0.78);
}
.recap-huge {
  font-size: clamp(4rem, 14vw, 9rem);
  font-weight: 900;
  line-height: 0.95;
  letter-spacing: -0.05em;
  font-variant-numeric: tabular-nums;
  animation: recap-pop 0.6s cubic-bezier(0.2, 0.9, 0.2, 1.2) both;
}
.recap-big {
  font-size: clamp(2rem, 6vw, 3.6rem);
  font-weight: 800;
  line-height: 1.05;
  letter-spacing: -0.03em;
  max-width: 18ch;
}
.recap-lead {
  font-size: clamp(1.05rem, 2.4vw, 1.5rem);
  font-weight: 600;
  color: rgb(255 255 255 / 0.92);
}
.recap-small {
  max-width: 40ch;
  font-size: 1rem;
  color: rgb(255 255 255 / 0.8);
}
.recap-cta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  height: 46px;
  padding: 0 24px;
  border-radius: 999px;
  background: #fff;
  color: #3a0f4f;
  font-weight: 700;
  box-shadow: 0 12px 30px rgb(0 0 0 / 0.25);
  transition: transform 0.15s ease;
}
.recap-cta:hover:not(:disabled) {
  transform: scale(1.04);
}
.recap-portrait {
  width: clamp(140px, 24vw, 220px);
  aspect-ratio: 1;
  border-radius: 999px;
  box-shadow: 0 20px 50px rgb(0 0 0 / 0.35);
  animation: recap-pop 0.6s cubic-bezier(0.2, 0.9, 0.2, 1.2) both;
}
.recap-list {
  display: grid;
  gap: 8px;
  width: min(560px, 100%);
  text-align: left;
}
.recap-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 12px;
  border-radius: 12px;
  background: rgb(0 0 0 / 0.18);
  animation: recap-in 0.45s ease both;
  animation-delay: calc(var(--i) * 80ms);
}
.recap-rank {
  width: 1.5em;
  font-size: 1.3rem;
  font-weight: 800;
  text-align: center;
}
.recap-thumb {
  width: 48px;
  height: 48px;
  flex: none;
}
.recap-row-title,
.recap-row-sub {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recap-row-title {
  font-weight: 700;
}
.recap-row-sub {
  font-size: 0.85rem;
  color: rgb(255 255 255 / 0.75);
}
.recap-row-count {
  flex: none;
  font-size: 0.8rem;
  color: rgb(255 255 255 / 0.75);
}
.recap-albums {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 160px));
  justify-content: center;
  gap: 18px;
  width: min(900px, 100%);
}
.recap-album {
  display: grid;
  gap: 8px;
  text-align: left;
  animation: recap-in 0.45s ease both;
  animation-delay: calc(var(--i) * 80ms);
}
.recap-album-art {
  width: 100%;
  aspect-ratio: 1;
  box-shadow: 0 12px 30px rgb(0 0 0 / 0.3);
}
.recap-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
  width: min(760px, 100%);
}
.recap-fact {
  display: grid;
  justify-items: center;
  gap: 6px;
  padding: 22px 16px;
  border-radius: 18px;
  background: rgb(0 0 0 / 0.2);
}
.recap-fact-icon {
  width: 28px;
  height: 28px;
  color: rgb(255 255 255 / 0.85);
}
.recap-fact-value {
  font-size: 1.6rem;
  font-weight: 800;
}
.recap-fact-label {
  font-size: 0.9rem;
  color: rgb(255 255 255 / 0.8);
}
.recap-months {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  width: min(420px, 100%);
  height: 90px;
  margin-top: 10px;
}
.recap-month {
  flex: 1;
  height: var(--h);
  border-radius: 4px 4px 2px 2px;
  background: rgb(255 255 255 / 0.85);
  transform-origin: bottom;
  animation: recap-grow 0.6s ease both;
  animation-delay: calc(var(--i) * 40ms);
}
.recap-nav {
  position: relative;
  display: flex;
  justify-content: center;
  gap: 12px;
  padding: 0 0 22px;
}
@keyframes recap-pop {
  from {
    opacity: 0;
    transform: scale(0.85);
  }
}
@keyframes recap-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
}
@keyframes recap-grow {
  from {
    transform: scaleY(0);
  }
}
.slide-next-enter-active,
.slide-next-leave-active,
.slide-prev-enter-active,
.slide-prev-leave-active {
  transition:
    opacity 0.28s ease,
    transform 0.28s ease;
}
.slide-next-enter-from,
.slide-prev-leave-to {
  opacity: 0;
  transform: translateX(28px);
}
.slide-next-leave-to,
.slide-prev-enter-from {
  opacity: 0;
  transform: translateX(-28px);
}
@media (prefers-reduced-motion: reduce) {
  .recap,
  .recap-glow,
  .recap-huge,
  .recap-portrait,
  .recap-row,
  .recap-album,
  .recap-month {
    animation: none;
  }
}
</style>
