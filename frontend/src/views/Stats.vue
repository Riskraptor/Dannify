<template>
  <div class="stats pb-12">
    <ViewHeader
      :title="t('stats.title')"
      :eyebrow="t('nav.yourLibrary')"
      :tile="{ icon: 'ph:chart-bar-fill', kind: 'tile-stats' }"
    >
      <template #meta>
        <template v-if="data && data.first">{{ t('stats.since', { date: sinceDate }) }}</template>
        <template v-else>{{ t('stats.subtitle') }}</template>
      </template>
      <template #actions>
        <router-link :to="{ name: 'History' }" class="btn btn-pill">
          <Icon icon="ph:clock-counter-clockwise" class="h-4 w-4" />
          {{ t('history.title') }}
        </router-link>
      </template>
    </ViewHeader>

    <div class="view-pad">
      <!-- Not being counted: said first, with the way to change it. -->
      <div v-if="!listens.keeping.value" class="stats-off">
        <Icon icon="ph:pause-circle" class="h-5 w-5 shrink-0" />
        <p class="min-w-0 flex-1">{{ t('stats.off') }}</p>
        <button class="btn btn-pill h-7 text-xs" @click="listens.setKeeping(true)">{{ t('stats.turnOn') }}</button>
      </div>

      <div v-if="!data && !failed" class="space-y-3 pt-2">
        <div class="skeleton h-8 w-80 max-w-full" />
        <div class="skeleton h-28" />
        <div class="skeleton h-56" />
      </div>

      <EmptyState v-else-if="failed && !data" icon="ph:cloud-warning" :title="t('stats.failed')">
        <button class="btn-accent btn-pill press" @click="load">
          <Icon icon="ph:arrows-clockwise" class="h-4 w-4" />
          {{ t('common.retry') }}
        </button>
      </EmptyState>

      <EmptyState
        v-else-if="!data.first"
        icon="ph:chart-bar"
        :title="t('stats.emptyTitle')"
        :text="t('stats.emptyText')"
      >
        <button class="btn-accent btn-pill" @click="ui.focusSearch()">
          <Icon icon="ph:magnifying-glass" class="h-4 w-4" />
          {{ t('nav.browse') }}
        </button>
      </EmptyState>

      <template v-else>
        <!-- The one filter. Everything under it is for the stretch it names,
             so the figures on the page always agree with each other. -->
        <div class="seg" role="radiogroup" :aria-label="t('stats.period')">
          <button
            v-for="p in PERIODS"
            :key="p.days"
            class="seg-item"
            role="radio"
            :aria-checked="days === p.days"
            :class="{ 'is-active': days === p.days }"
            @click="setDays(p.days)"
          >
            {{ t(p.label) }}
          </button>
        </div>

        <!-- While another stretch loads, the last one stays where it is,
             dimmed: no blank page, and nothing jumps. -->
        <div class="stats-body" :class="{ 'is-stale': loading }" :aria-busy="loading">
          <div class="tiles">
            <div class="tile is-hero">
              <p class="tile-label">{{ t('stats.timeListened') }}</p>
              <p class="tile-value">{{ durationText(data.seconds, t) }}</p>
              <p v-if="trend" class="tile-note">
                <Icon v-if="trend.direction !== 'same'" :icon="trend.direction === 'up' ? 'ph:arrow-up-bold' : 'ph:arrow-down-bold'" class="h-3 w-3" />
                {{ trendText }}
              </p>
            </div>
            <div class="tile">
              <p class="tile-label">{{ t('stats.plays') }}</p>
              <p class="tile-value">{{ number(data.plays) }}</p>
              <p class="tile-note">{{ t('stats.differentSongs', { count: data.songs }) }}</p>
            </div>
            <div class="tile">
              <p class="tile-label">{{ t('stats.artists') }}</p>
              <p class="tile-value">{{ number(data.artists) }}</p>
              <p v-if="data.albums" class="tile-note">{{ t('stats.albumCount', { count: data.albums }) }}</p>
            </div>
            <div class="tile">
              <p class="tile-label">{{ t('stats.streak') }}</p>
              <p class="tile-value">{{ number(data.streak) }}</p>
              <p class="tile-note">{{ t('stats.streakLongest', { count: data.longest_streak }) }}</p>
            </div>
          </div>

          <p v-if="!data.plays" class="stats-none">{{ t('stats.emptyPeriod') }}</p>

          <template v-else>
            <div class="charts">
              <section class="panel">
                <h2 class="panel-title">{{ data.bucket === 'month' ? t('stats.byMonth') : t('stats.byDay') }}</h2>
                <BarChart
                  :bars="dayBars"
                  :scale="dayScale"
                  :labels="dayLabels"
                  :label="data.bucket === 'month' ? t('stats.byMonth') : t('stats.byDay')"
                  :columns="[data.bucket === 'month' ? t('stats.colMonth') : t('stats.colDay'), t('stats.timeListened')]"
                />
              </section>
              <section class="panel">
                <h2 class="panel-title">{{ t('stats.byHour') }}</h2>
                <p v-if="peak >= 0" class="panel-sub">{{ t('stats.byHourPeak', { hour: hourText(peak, locale) }) }}</p>
                <BarChart
                  dense
                  :height="132"
                  :bars="hourBars"
                  :scale="hourScale"
                  :labels="hourLabels"
                  :label="t('stats.byHour')"
                  :columns="[t('stats.colHour'), t('stats.timeListened')]"
                />
              </section>
            </div>

            <section class="top">
              <header class="top-head">
                <h2 class="top-title">{{ t('stats.topSongs') }}</h2>
                <div class="flex items-center gap-1">
                  <button class="btn-ghost btn-pill h-8" @click="saveTop">
                    <Icon icon="ph:playlist" class="h-4 w-4" />
                    {{ t('playlists.saveQueue') }}
                  </button>
                  <button class="btn btn-pill h-8" @click="playRows(songRows, 0, { toggle: false })">
                    <Icon icon="ph:play-fill" class="h-3.5 w-3.5" />
                    {{ t('actions.play') }}
                  </button>
                </div>
              </header>
              <ol class="rank-list">
                <li v-for="(row, i) in shownSongs" :key="row.key">
                  <div
                    class="rank press"
                    role="button"
                    tabindex="0"
                    :class="{ 'is-current': isRowCurrent(row), 'is-gone': row.gone }"
                    :title="`${row.title}. ${row.artistText}`"
                    @click="playRows(songRows, i)"
                    @keydown.enter.prevent="playRows(songRows, i)"
                    @contextmenu="onSongMenu($event, row)"
                  >
                    <span class="rank-n">{{ i + 1 }}</span>
                    <CoverImage :src="row.cover" radius="sm" :size="44" class="rank-cover" />
                    <span class="rank-text">
                      <span class="rank-title">{{ row.title }}</span>
                      <span class="rank-sub">{{ row.artistText || t('common.unknownArtist') }}</span>
                    </span>
                    <span class="rank-meter" aria-hidden="true">
                      <span :style="{ width: `${Math.max(4, (row.plays / topPlays) * 100)}%` }" />
                    </span>
                    <span class="rank-plays">{{ t('stats.playCount', { count: row.plays }) }}</span>
                    <span class="rank-time">{{ durationText(row.seconds, t) }}</span>
                  </div>
                </li>
              </ol>
              <button v-if="songRows.length > FIRST" class="more-btn" @click="allSongs = !allSongs">
                {{ allSongs ? t('explore.showLess') : t('home.showAll') }}
              </button>
            </section>

            <!-- A shelf's cards have their own padding: pulled out by that
                 much, their pictures line up with everything above. -->
            <div class="stats-shelves">
              <Shelf v-if="data.top_artists.length" :title="t('stats.topArtists')">
                <MediaCard
                  v-for="a in data.top_artists.slice(0, 16)"
                  :key="a.name"
                  :item="{ name: a.name, cover: artistPicture(a), fallback: coverURL(a.cover) }"
                  kind="artist"
                  :subtitle-text="`${t('stats.playCount', { count: a.plays })} · ${durationText(a.seconds, t)}`"
                  @open="openArtist(a)"
                />
              </Shelf>

              <Shelf v-if="data.top_albums.length" :title="t('stats.topAlbums')">
                <MediaCard
                  v-for="a in data.top_albums.slice(0, 16)"
                  :key="a.name + a.artist"
                  :item="{ name: a.name, cover: coverURL(a.cover) }"
                  kind="album"
                  :subtitle-text="`${a.artist} · ${t('stats.playCount', { count: a.plays })}`"
                  @open="openAlbum(a)"
                />
              </Shelf>
            </div>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, shallowRef, computed, watch, onActivated, onDeactivated } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useListens } from '/src/model/listens'
import { useLibrary, albumRoute } from '/src/model/library'
import { useUi } from '/src/model/ui'
import { useArtistLinks } from '/src/model/artistLinks'
import { usePlaylists, entryRow, coverURL } from '/src/model/playlists'
import { playRows, isRowCurrent, trackMenu } from '/src/model/tracks'
import { openContextMenu } from '/src/model/contextMenu'
import { onRefresh } from '/src/model/useRefresh'
import {
  axisLabels,
  bucketTitle,
  change,
  durationText,
  hourText,
  peakHour,
  timeScale,
} from '/src/model/statsFormat'
import { useI18n } from '/src/i18n'
import ViewHeader from '/src/components/ui/ViewHeader.vue'
import EmptyState from '/src/components/ui/EmptyState.vue'
import BarChart from '/src/components/ui/BarChart.vue'
import CoverImage from '/src/components/ui/CoverImage.vue'
import Shelf from '/src/components/ui/Shelf.vue'
import MediaCard from '/src/components/MediaCard.vue'

// Your listening, added up: how much, what most, and when. All of it from
// the app's own history (model/listens.js), which never leaves this computer.

const { t, locale } = useI18n()
const router = useRouter()
const ui = useUi()
const lib = useLibrary()
const listens = useListens()
const artistLinks = useArtistLinks()
const playlists = usePlaylists()

lib.ensureLoaded()

const PERIODS = [
  { days: 7, label: 'stats.days7', before: 'stats.before7' },
  { days: 30, label: 'stats.days30', before: 'stats.before30' },
  { days: 365, label: 'stats.days365', before: 'stats.before365' },
  { days: 0, label: 'stats.ever', before: '' },
]
const DAYS_KEY = 'dn.statsDays'
function storedDays() {
  try {
    const raw = localStorage.getItem(DAYS_KEY)
    // Nothing stored is not "0": that is All time, and the page opened on
    // it the first time.
    const v = raw === null ? NaN : Number(raw)
    return PERIODS.some((p) => p.days === v) ? v : 30
  } catch {
    return 30
  }
}
const days = ref(storedDays())
function setDays(v) {
  days.value = v
  try {
    localStorage.setItem(DAYS_KEY, String(v))
  } catch {
    // remembered for this run only
  }
}

const data = shallowRef(null)
const loading = ref(false)
const failed = ref(false)
// Only the answer to the latest question is shown: switching from a year to
// a week and back must not leave the week's figures under the year's name.
let asked = 0
let seenEpoch = -1
async function load() {
  const mine = ++asked
  loading.value = true
  seenEpoch = listens.listensEpoch.value
  try {
    const got = await listens.fetchStats(days.value)
    if (mine !== asked) return
    data.value = got
    failed.value = false
  } catch {
    if (mine === asked) failed.value = true
  } finally {
    if (mine === asked) loading.value = false
  }
}
watch(days, load, { immediate: true })

// A song that ends while the page is open is counted on it there and then;
// one that ends while it is away, when it comes back.
let active = true
watch(listens.listensEpoch, () => {
  if (active) load()
})
onActivated(() => {
  active = true
  if (seenEpoch !== listens.listensEpoch.value) load()
})
onDeactivated(() => {
  active = false
})
onRefresh(load)

const sinceDate = computed(() =>
  data.value && data.value.first
    ? new Intl.DateTimeFormat(locale.value, { day: 'numeric', month: 'long', year: 'numeric' }).format(
        new Date(data.value.first * 1000)
      )
    : ''
)

function number(n) {
  return new Intl.NumberFormat(locale.value).format(n || 0)
}

// ----- against the stretch before ---------------------------------------------
const trend = computed(() =>
  data.value && data.value.previous ? change(data.value.seconds, data.value.previous.seconds) : null
)
const trendText = computed(() => {
  const period = PERIODS.find((p) => p.days === (data.value ? data.value.days : days.value))
  const before = period && period.before ? t(period.before) : ''
  if (!trend.value || !before) return ''
  if (trend.value.direction === 'same') return t('stats.same', { period: before })
  return t(trend.value.direction === 'up' ? 'stats.up' : 'stats.down', {
    percent: trend.value.percent,
    period: before,
  })
})

// ----- the charts -------------------------------------------------------------
const dayBars = computed(() =>
  data.value.buckets.map((b) => ({
    key: b.label,
    value: b.seconds,
    title: bucketTitle(b.label, data.value.bucket, locale.value),
    text: durationText(b.seconds, t),
    note: b.plays ? t('stats.playCount', { count: b.plays }) : '',
  }))
)
const dayScale = computed(() => timeScale(Math.max(0, ...data.value.buckets.map((b) => b.seconds)), t))
const dayLabels = computed(() =>
  axisLabels(
    data.value.buckets.map((b) => b.label),
    data.value.bucket,
    locale.value
  )
)

const peak = computed(() => peakHour(data.value.by_hour))
const hourBars = computed(() =>
  data.value.by_hour.map((seconds, hour) => ({
    key: hour,
    value: seconds,
    title: hourText(hour, locale.value),
    text: durationText(seconds, t),
  }))
)
const hourScale = computed(() => timeScale(Math.max(0, ...data.value.by_hour), t))
const hourLabels = computed(() =>
  [0, 6, 12, 18].map((hour) => ({ index: hour, text: hourText(hour, locale.value) }))
)

// ----- what was played most ---------------------------------------------------
const FIRST = 10
const allSongs = ref(false)
watch(days, () => {
  allSongs.value = false
})
// Rows the way a playlist makes them: from the library when the song is
// saved, from YouTube when it is not.
const songRows = computed(() => {
  // Re-made when the library is read again: a song saved since plays from disk.
  void lib.tracks.value
  return ((data.value && data.value.top_songs) || []).map((song, i) => ({
    ...entryRow(song, i),
    plays: song.plays,
    seconds: song.seconds,
  }))
})
const shownSongs = computed(() => (allSongs.value ? songRows.value : songRows.value.slice(0, FIRST)))
const topPlays = computed(() => Math.max(1, ...songRows.value.map((r) => r.plays)))

function onSongMenu(e, row) {
  openContextMenu(e, trackMenu([row], { source: songRows.value }))
}

function saveTop() {
  const period = PERIODS.find((p) => p.days === days.value)
  playlists.createPlaylist(songRows.value, {
    name: t('stats.topPlaylistName', { period: t(period.label) }),
  })
}

const savedArtists = computed(() => new Set(lib.artists.value.map((a) => a.name)))
function artistPicture(a) {
  return artistLinks.artistPhoto(a.name, 220) || coverURL(a.cover)
}
function openArtist(a) {
  // Their page in the library when there is one: it has what is saved of
  // theirs first, and the rest of their music under it.
  if (savedArtists.value.has(a.name)) router.push({ name: 'Artist', params: { name: a.name } })
  else if (a.id) router.push({ name: 'ExploreArtist', params: { id: a.id } })
  else router.push({ name: 'Search', params: { query: a.name } })
}
function openAlbum(a) {
  const saved = lib.albums.value.find(
    (x) => x.name.toLowerCase() === a.name.toLowerCase() && x.artist.toLowerCase() === a.artist.toLowerCase()
  )
  if (saved) router.push(albumRoute(saved))
  else if (a.album_id) router.push({ name: 'ExploreAlbum', params: { id: a.album_id } })
  else router.push({ name: 'Search', params: { query: `${a.artist} ${a.name}`.trim() } })
}
</script>

<style scoped>
.stats {
  container: stats / inline-size;
}
.stats-off {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgb(var(--c-warn) / 0.12);
  font-size: 13px;
}
.stats-body {
  margin-top: 18px;
  transition: opacity 0.15s ease;
}
.stats-body.is-stale {
  opacity: 0.55;
}
.stats-none {
  margin: 28px 0;
  font-size: 13.5px;
  color: rgb(var(--c-fg) / var(--fg-60));
}

/* ----- the figures ----- */
.tiles {
  display: grid;
  grid-template-columns: 1.5fr repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.tile {
  min-width: 0;
  padding: 16px 18px;
  border-radius: 12px;
  border: 1px solid rgb(var(--c-tint) / 0.06);
  background: rgb(var(--c-raised));
}
.tile-label {
  font-size: 12.5px;
  font-weight: 600;
  color: rgb(var(--c-fg) / var(--fg-60));
}
/* Proportional figures: a number this size set in tabular ones looks as if
   it had been typed with spaces in it. */
.tile-value {
  margin-top: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-display, inherit);
  font-size: 26px;
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.02em;
}
/* The one figure the page leads with. */
.tile.is-hero .tile-value {
  font-size: 48px;
  letter-spacing: -0.03em;
}
.tile-note {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 6px;
  font-size: 12.5px;
  color: rgb(var(--c-fg) / var(--fg-60));
}
@container stats (max-width: 860px) {
  .tiles {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .tile.is-hero {
    grid-column: 1 / -1;
  }
}
@container stats (max-width: 520px) {
  .tiles {
    grid-template-columns: minmax(0, 1fr);
  }
  .tile.is-hero .tile-value {
    font-size: 38px;
  }
}

/* ----- the charts ----- */
.charts {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
  gap: 10px;
  margin-top: 10px;
}
@container stats (max-width: 860px) {
  .charts {
    grid-template-columns: minmax(0, 1fr);
  }
}
.panel {
  min-width: 0;
  padding: 18px 20px 14px;
  border-radius: 12px;
  border: 1px solid rgb(var(--c-tint) / 0.06);
  background: rgb(var(--c-raised));
}
.panel-title {
  font-size: 15px;
  font-weight: 700;
}
.panel-sub {
  margin-top: 2px;
  font-size: 12.5px;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.panel :deep(.bc) {
  margin-top: 22px;
}

/* ----- played most ----- */
.top {
  margin: 30px 0 28px;
}
.top-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  margin-bottom: 8px;
}
.top-title {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.015em;
}
.rank-list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.rank {
  display: flex;
  align-items: center;
  gap: 14px;
  height: 56px;
  padding: 0 12px 0 8px;
  border-radius: 6px;
  outline: none;
}
.rank:hover,
.rank:focus-visible {
  background: rgb(var(--c-tint) / 0.06);
}
.rank:focus-visible {
  box-shadow: inset 0 0 0 2px rgb(var(--c-accent) / 0.7);
}
.rank.is-gone {
  opacity: 0.45;
}
.rank-n {
  width: 22px;
  flex-shrink: 0;
  text-align: right;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--c-fg) / var(--fg-55));
}
.rank-cover {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
}
.rank-text {
  min-width: 0;
  flex: 1 1 0;
}
.rank-title,
.rank-sub {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rank-title {
  font-size: 14px;
  font-weight: 600;
}
.rank.is-current .rank-title {
  color: rgb(var(--c-accent));
}
.rank-sub {
  font-size: 12.5px;
  color: rgb(var(--c-fg) / var(--fg-55));
}
/* How each song stands against the one played most. */
.rank-meter {
  width: 22%;
  max-width: 220px;
  height: 4px;
  flex-shrink: 0;
  border-radius: 999px;
  background: rgb(var(--c-accent) / 0.16);
}
.rank-meter > span {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: rgb(var(--c-accent));
}
.rank-plays,
.rank-time {
  flex-shrink: 0;
  font-size: 12.5px;
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.rank-plays {
  width: 76px;
  color: rgb(var(--c-fg) / 0.85);
}
.rank-time {
  width: 84px;
  color: rgb(var(--c-fg) / var(--fg-55));
}
@container stats (max-width: 720px) {
  .rank-meter,
  .rank-time {
    display: none;
  }
}
.stats-shelves {
  margin: 0 -10px;
}
.more-btn {
  margin: 8px 0 0 8px;
  font-size: 13px;
  font-weight: 700;
  color: rgb(var(--c-fg) / var(--fg-60));
}
.more-btn:hover {
  color: rgb(var(--c-fg));
  text-decoration: underline;
}
</style>
