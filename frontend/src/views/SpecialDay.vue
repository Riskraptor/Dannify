<template>
  <div class="sday" :style="colors">
    <EmptyState v-if="lost" icon="ph:calendar-x" :title="t('day.lost')" :text="t('day.lostText')">
      <button class="btn btn-pill" @click="router.push({ name: 'Settings', query: { pane: 'days' } })">
        {{ t('settings.specialDays') }}
      </button>
    </EmptyState>

    <template v-else-if="day">
      <!-- The day in its own colours and weather. -->
      <header class="sday-hero">
        <Particles v-if="!still" :look="day.look" :count="day.look.motion === 'burst' ? 44 : 36" contain fall="460px" />
        <div class="sday-hero-body view-pad">
          <span class="sday-icon"><Icon :icon="day.icon" class="h-7 w-7" /></span>
          <p class="sday-date">{{ longDate }}</p>
          <h1 class="sday-title">{{ words.title }}</h1>
          <p v-if="when === 'today' || lineBefore(day)" class="sday-text">{{ words.text }}</p>

          <!-- The day itself, or the time to it, ticking. -->
          <p v-if="when === 'today'" class="sday-now"><span class="sday-pulse" />{{ t('day.today') }}</p>
          <div v-else-if="when === 'coming'" class="sday-clock" role="timer">
            <span class="sday-clock-label">{{ t('day.startsIn') }}</span>
            <span v-for="u in clock" :key="u.key" class="sday-unit">
              <b>{{ u.value }}</b>
              <small>{{ t(`day.${u.key}`) }}</small>
            </span>
          </div>
          <p v-else class="sday-now is-past">{{ t('day.past') }}</p>

          <div class="sday-actions">
            <button class="sday-play press" :disabled="!songRows.length" @click="playAll">
              <Icon :icon="playingHere ? 'ph:pause-fill' : 'ph:play-fill'" class="h-5 w-5" />
              {{ t('day.play') }}
            </button>
            <button class="sday-ghost press" :disabled="!songRows.length" @click="shuffleRows(songRows)">
              <Icon icon="ph:shuffle" class="h-4 w-4" />
              {{ t('actions.shuffle') }}
            </button>
          </div>
        </div>
      </header>

      <div class="view-pad sday-body">
        <OfflineCard v-if="offline" class="mb-8" />
        <div v-else-if="loading" class="sday-wait" aria-busy="true">
          <div v-for="n in 5" :key="n" class="skeleton sday-wait-card" />
        </div>
        <p v-else-if="!playlists.length && !songRows.length" class="sday-none">{{ t('day.nothing') }}</p>

        <Shelf v-if="playlists.length" :title="t('occasion.musicFor', { day: words.name })">
          <MediaCard
            v-for="p in playlists"
            :key="p.browse_id"
            :item="p"
            kind="playlist"
            @open="router.push({ name: 'ExplorePlaylist', params: { id: p.browse_id } })"
          />
        </Shelf>

        <section v-if="songRows.length" class="sday-section">
          <h2 class="sday-h">{{ t('day.songs') }}</h2>
          <TrackTable :rows="songRows" show-cover :on-play="(i) => playRows(songRows, i)" />
        </section>

        <!-- What this day sounded like for them, the last time it came. -->
        <section v-if="pastRows.length" class="sday-past">
          <header class="sday-past-head">
            <div>
              <h2 class="sday-h">{{ t('day.lastTime', { day: words.name }) }}</h2>
              <p class="sday-sub">{{ t('day.lastTimeText', { date: pastDate, time: durationText(past.seconds, t) }) }}</p>
            </div>
            <button class="btn btn-pill h-8" @click="playRows(pastRows, 0, { toggle: false })">
              <Icon icon="ph:play-fill" class="h-3.5 w-3.5" />
              {{ t('actions.play') }}
            </button>
          </header>
          <ol class="sday-past-list">
            <li v-for="(row, i) in pastRows.slice(0, 6)" :key="row.key">
              <button class="sday-past-row press" :class="{ 'is-current': isRowCurrent(row) }" @click="playRows(pastRows, i)">
                <CoverImage :src="row.cover" radius="sm" class="h-12 w-12 shrink-0" />
                <span class="sday-past-text">
                  <b>{{ row.title }}</b>
                  <small>{{ row.artistText || t('common.unknownArtist') }}</small>
                </span>
                <span class="sday-past-n">{{ t('stats.playCount', { count: row.plays }) }}</span>
              </button>
            </li>
          </ol>
        </section>

        <!-- The days after this one, each with a page like this. -->
        <section v-if="others.length" class="sday-section">
          <h2 class="sday-h">{{ t('settings.comingUp') }}</h2>
          <div class="sday-others">
            <button
              v-for="(o, i) in others"
              :key="o.tag + o.day.toDateString()"
              class="sday-tile press"
              :style="{ ...dayColors(o), '--i': i }"
              @click="router.push(dayRoute(o))"
            >
              <span class="sday-tile-icon"><Icon :icon="o.icon" class="h-5 w-5" /></span>
              <span class="sday-tile-when">{{ shortDate(o.day) }}</span>
              <span class="sday-tile-name">{{ wordsFor(o, t, locale).title }}</span>
            </button>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import API from '/src/model/api'
import { useI18n } from '/src/i18n'
import { usePlayer } from '/src/model/player'
import { failedForNetwork, whenOnline } from '/src/model/connectivity'
import { entryRow } from '/src/model/playlists'
import { songRow, playRows, shuffleRows, isRowCurrent } from '/src/model/tracks'
import { durationText } from '/src/model/statsFormat'
import {
  calendar,
  dayColors,
  dayRoute,
  findOccasion,
  lineBefore,
  loadCalendar,
  prefersStill,
  previousOf,
  region,
  upcoming,
  wordsFor,
} from '/src/model/occasions'
import Particles from '/src/components/ui/Particles.vue'
import Shelf from '/src/components/ui/Shelf.vue'
import MediaCard from '/src/components/MediaCard.vue'
import TrackTable from '/src/components/ui/TrackTable.vue'
import CoverImage from '/src/components/ui/CoverImage.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'
import OfflineCard from '/src/components/ui/OfflineCard.vue'

// A special day's own page: its colours and weather, the time to it ticking
// down, music for it from YouTube Music, what the listener played on it the
// year before, and the days after it.
const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const player = usePlayer()
const still = prefersStill()
loadCalendar()

const day = computed(() => (calendar.value ? findOccasion(route.params.id, route.params.date) : null))
const lost = computed(() => !!calendar.value && route.name === 'SpecialDay' && !day.value)
const words = computed(() => wordsFor(day.value, t, locale.value))
const colors = computed(() => (day.value ? dayColors(day.value) : {}))
const longDate = computed(() =>
  day.value ? new Intl.DateTimeFormat(locale.value, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(day.value.day) : ''
)
function shortDate(date) {
  return new Intl.DateTimeFormat(locale.value, { day: 'numeric', month: 'short' }).format(date)
}

// ----- the clock ---------------------------------------------------------------
const now = ref(Date.now())
const when = computed(() => {
  const o = day.value
  if (!o) return ''
  if (now.value < o.start.getTime()) return 'coming'
  return now.value < o.end.getTime() ? 'today' : 'past'
})
const clock = computed(() => {
  let left = Math.max(0, Math.floor((day.value.start.getTime() - now.value) / 1000))
  const days = Math.floor(left / 86400)
  left -= days * 86400
  const hours = Math.floor(left / 3600)
  left -= hours * 3600
  const units = [
    { key: 'hours', value: hours },
    { key: 'minutes', value: Math.floor(left / 60) },
    { key: 'seconds', value: left % 60 },
  ]
  if (days) units.unshift({ key: 'days', value: days })
  return units.map((u) => ({ ...u, value: u.key === 'days' ? String(u.value) : String(u.value).padStart(2, '0') }))
})
// Ticking only while there is something to count down to.
let ticker = 0
watch(
  when,
  (state) => {
    clearInterval(ticker)
    if (state === 'coming') ticker = setInterval(() => (now.value = Date.now()), 1000)
  },
  { immediate: true }
)
onBeforeUnmount(() => clearInterval(ticker))

// ----- the day's music ---------------------------------------------------------
const playlists = shallowRef([])
const songs = shallowRef([])
const loading = ref(false)
const offline = ref(false)
const songRows = computed(() => songs.value.map(songRow))
let asked = ''
async function loadMusic(query) {
  if (!query) return
  asked = query
  loading.value = true
  offline.value = false
  try {
    const res = await API.exploreSearch(query, 20)
    if (asked !== query) return
    playlists.value = ((res.data && res.data.playlists) || []).slice(0, 12)
    songs.value = ((res.data && res.data.songs) || []).slice(0, 20)
  } catch (err) {
    if (asked !== query) return
    if (await failedForNetwork(err)) {
      offline.value = true
      whenOnline(() => asked === query && loadMusic(query))
    }
  } finally {
    if (asked === query) loading.value = false
  }
}
watch(
  () => words.value.music,
  (query) => {
    playlists.value = []
    songs.value = []
    loadMusic(query)
  },
  { immediate: true }
)

const currentHere = computed(() => songRows.value.some((r) => isRowCurrent(r)))
const playingHere = computed(() => currentHere.value && player.isPlaying.value)
function playAll() {
  if (currentHere.value) return player.toggle()
  playRows(songRows.value, 0)
}

// ----- the last time it came ---------------------------------------------------
const past = shallowRef(null)
const pastDay = shallowRef(null)
const pastRows = computed(() =>
  ((past.value && past.value.songs) || []).map((song, i) => ({ ...entryRow(song, i), plays: song.plays }))
)
const pastDate = computed(() =>
  pastDay.value ? new Intl.DateTimeFormat(locale.value, { day: 'numeric', month: 'long', year: 'numeric' }).format(pastDay.value.day) : ''
)
watch(
  day,
  async (o) => {
    past.value = null
    const before = previousOf(o)
    pastDay.value = before
    if (!before) return
    try {
      const res = await API.getListensBetween(Math.floor(before.start.getTime() / 1000), Math.floor(before.end.getTime() / 1000), 20)
      if (pastDay.value === before) past.value = res.data
    } catch {
      // Nothing to look back on is shown as nothing.
    }
  },
  { immediate: true }
)

// ----- the days after ----------------------------------------------------------
const others = computed(() => {
  if (!day.value || !calendar.value) return []
  return upcoming(new Date(), region.value, calendar.value, 9)
    .filter((o) => !(o.rowId === day.value.rowId && o.day.getTime() === day.value.day.getTime()))
    .slice(0, 8)
})
</script>

<style scoped>
.sday-hero {
  position: relative;
  overflow: hidden;
  isolation: isolate;
  color: #fff;
  background:
    linear-gradient(180deg, rgb(0 0 0 / 0.12) 0%, rgb(0 0 0 / 0.42) 70%, rgb(var(--c-panel)) 100%),
    linear-gradient(130deg, var(--sd-a), var(--sd-b) 60%, var(--sd-c, var(--sd-b)));
}
.sday-hero-body {
  position: relative;
  z-index: 1;
  display: grid;
  justify-items: start;
  gap: 8px;
  padding-top: 48px;
  padding-bottom: 40px;
  animation: sday-rise 0.5s var(--ease-out) both;
}
.sday-icon {
  display: grid;
  width: 56px;
  height: 56px;
  place-items: center;
  border-radius: 18px;
  background: rgb(255 255 255 / 0.2);
  box-shadow: 0 10px 30px rgb(0 0 0 / 0.18);
  backdrop-filter: blur(8px);
  animation: sday-pop 0.6s var(--ease-out) both;
}
.sday-date {
  margin-top: 6px;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: rgb(255 255 255 / 0.85);
}
.sday-title {
  font-size: clamp(30px, 4.4vw, 56px);
  font-weight: 900;
  line-height: 1.04;
  letter-spacing: -0.03em;
  text-shadow: 0 4px 30px rgb(0 0 0 / 0.25);
}
.sday-text {
  max-width: 60ch;
  font-size: 15px;
  line-height: 1.5;
  color: rgb(255 255 255 / 0.9);
}
.sday-now {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  padding: 6px 14px;
  border-radius: 999px;
  background: #fff;
  color: #111;
  font-size: 13px;
  font-weight: 800;
}
.sday-now.is-past {
  background: rgb(0 0 0 / 0.3);
  color: #fff;
}
.sday-pulse {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--sd-a);
  animation: sday-beat 1.4s ease-in-out infinite;
}
.sday-clock {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.sday-clock-label {
  margin-right: 4px;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: rgb(255 255 255 / 0.8);
}
.sday-unit {
  display: grid;
  min-width: 62px;
  justify-items: center;
  padding: 8px 10px 6px;
  border-radius: 14px;
  background: rgb(0 0 0 / 0.26);
  backdrop-filter: blur(8px);
}
.sday-unit b {
  font-size: 26px;
  font-weight: 900;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.sday-unit small {
  margin-top: 3px;
  font-size: 11px;
  font-weight: 700;
  color: rgb(255 255 255 / 0.75);
}
.sday-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}
.sday-play,
.sday-ghost {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 44px;
  padding: 0 20px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 800;
  transition:
    transform 0.15s ease,
    opacity 0.15s ease;
}
.sday-play {
  background: #fff;
  color: #111;
  box-shadow: 0 10px 26px rgb(0 0 0 / 0.25);
}
.sday-ghost {
  background: rgb(0 0 0 / 0.28);
  color: #fff;
  backdrop-filter: blur(8px);
}
.sday-play:hover:not(:disabled),
.sday-ghost:hover:not(:disabled) {
  transform: scale(1.04);
}
.sday-play:disabled,
.sday-ghost:disabled {
  opacity: 0.55;
}
.sday-body {
  padding-top: 8px;
}
.sday-wait {
  display: flex;
  gap: 16px;
  overflow: hidden;
  margin: 18px 0 32px;
}
.sday-wait-card {
  width: 170px;
  height: 220px;
  flex: none;
  border-radius: 12px;
}
.sday-none {
  margin: 18px 0 28px;
  font-size: 14px;
  color: rgb(var(--c-fg) / 0.6);
}
.sday-section {
  margin: 8px 0 32px;
}
.sday-h {
  margin-bottom: 12px;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.01em;
}
.sday-sub {
  margin-top: -6px;
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.65);
}
.sday-past {
  margin: 8px 0 32px;
  padding: 20px;
  border-radius: 20px;
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--sd-a) 22%, transparent), color-mix(in srgb, var(--sd-b) 10%, transparent)),
    rgb(var(--c-tint) / 0.04);
  box-shadow: inset 0 0 0 1px rgb(var(--c-tint) / 0.08);
}
.sday-past-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.sday-past-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 8px;
}
.sday-past-row {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 12px;
  padding: 8px;
  border-radius: 12px;
  text-align: left;
  transition: background 0.15s ease;
}
.sday-past-row:hover {
  background: rgb(var(--c-tint) / 0.08);
}
.sday-past-row.is-current b {
  color: rgb(var(--c-accent));
}
.sday-past-text {
  display: grid;
  min-width: 0;
  flex: 1;
}
.sday-past-text b,
.sday-past-text small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sday-past-text b {
  font-size: 14px;
}
.sday-past-text small {
  font-size: 12.5px;
  color: rgb(var(--c-fg) / 0.6);
}
.sday-past-n {
  flex: none;
  font-size: 12px;
  font-weight: 700;
  color: rgb(var(--c-fg) / 0.6);
}
.sday-others {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}
.sday-tile {
  position: relative;
  display: grid;
  align-content: end;
  justify-items: start;
  gap: 2px;
  min-width: 0;
  height: 120px;
  padding: 12px;
  overflow: hidden;
  border-radius: 16px;
  color: #fff;
  text-align: left;
  background:
    linear-gradient(180deg, rgb(0 0 0 / 0.05), rgb(0 0 0 / 0.55)),
    linear-gradient(140deg, var(--sd-a), var(--sd-b));
  box-shadow: 0 8px 20px rgb(0 0 0 / 0.16);
  transition:
    transform 0.18s var(--ease-out),
    box-shadow 0.18s ease;
  animation: sday-rise 0.4s ease both;
  animation-delay: calc(var(--i) * 30ms);
}
.sday-tile:hover {
  transform: translateY(-3px);
  box-shadow: 0 14px 28px rgb(0 0 0 / 0.24);
}
.sday-tile-icon {
  position: absolute;
  top: 10px;
  left: 10px;
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 10px;
  background: rgb(255 255 255 / 0.2);
}
.sday-tile-when {
  font-size: 11px;
  font-weight: 800;
  color: rgb(255 255 255 / 0.85);
}
.sday-tile-name {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  font-size: 13px;
  font-weight: 800;
  line-height: 1.2;
}
@keyframes sday-rise {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
}
@keyframes sday-pop {
  from {
    opacity: 0;
    transform: scale(0.6) rotate(-12deg);
  }
}
@keyframes sday-beat {
  50% {
    transform: scale(1.6);
    opacity: 0.5;
  }
}
@media (prefers-reduced-motion: reduce) {
  .sday-hero-body,
  .sday-icon,
  .sday-tile,
  .sday-pulse {
    animation: none;
  }
}
</style>
