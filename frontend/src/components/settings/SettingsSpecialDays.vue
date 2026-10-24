<template>
  <section>
    <h2 class="group-title">{{ t('settings.specialDays') }}</h2>

    <!-- Where first: the days below are the ones kept there, and it is what
         someone changes when they are not the right ones. -->
    <div class="row sd-region">
      <span class="sd-flag" aria-hidden="true">
        <i v-for="(c, i) in flagOf(region)" :key="i" :style="{ background: c }" />
      </span>
      <div class="row-text">
        <p class="row-label">{{ t('settings.region') }}</p>
        <p class="row-hint">{{ t('settings.regionHint') }}</p>
      </div>
      <select class="field-select w-56" :value="regionChoice" :aria-label="t('settings.region')" @change="setRegion($event.target.value)">
        <option value="auto">
          {{ detectedName ? t('settings.regionAuto', { country: detectedName }) : t('settings.regionAutoNone') }}
        </option>
        <option v-for="c in countries" :key="c.code" :value="c.code">{{ c.name }}</option>
      </select>
    </div>

    <!-- The next special day, in its own colours, moving its own way: a
         list of dates said nothing of what the days are like. -->
    <article v-if="next" class="sd-hero" :style="paint(next)">
      <Particles v-if="!still" :look="next.look" :count="26" contain fall="300px" />
      <div class="sd-hero-body">
        <span class="sd-badge" :class="{ 'is-today': isToday(next) }">
          <Icon :icon="next.icon" class="h-3.5 w-3.5" />
          {{ countdown(next) }}
        </span>
        <h3 class="sd-hero-title">{{ words(next).title }}</h3>
        <p class="sd-hero-date">{{ longDate(next) }}</p>
        <p v-if="isToday(next) || lineBefore(next)" class="sd-hero-text">{{ words(next).text }}</p>
        <button v-if="words(next).music" class="sd-hero-btn press" @click="listen(next)">
          <Icon icon="ph:music-notes-fill" class="h-4 w-4" />
          {{ t('occasion.musicFor', { day: words(next).name }) }}
        </button>
      </div>
    </article>

    <!-- The rest of the year, each day a tile in its colours. -->
    <div v-if="rest.length" class="sd-strip-head">
      <p class="row-label">{{ t('settings.comingUp') }}</p>
      <p class="row-hint">{{ t('settings.comingUpHint') }}</p>
    </div>
    <div v-if="rest.length" class="sd-strip" role="list">
      <button
        v-for="(o, i) in rest"
        :key="o.tag + o.day.toDateString()"
        class="sd-tile press"
        role="listitem"
        :style="{ ...paint(o), '--i': i }"
        :title="t('occasion.musicFor', { day: words(o).name })"
        @click="listen(o)"
      >
        <span class="sd-tile-icon"><Icon :icon="o.icon" class="h-5 w-5" /></span>
        <span class="sd-tile-when">{{ shortWhen(o) }}</span>
        <span class="sd-tile-name">{{ words(o).title }}</span>
      </button>
    </div>
    <p v-if="!next" class="sd-empty">{{ t('settings.comingUpNone') }}</p>

  </section>
</template>

<script setup>
import { computed, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import {
  calendar,
  countryChoices,
  countryName,
  dayColors,
  dayRoute,
  detectedRegion,
  lineBefore,
  loadCalendar,
  prefersStill,
  region,
  regionChoice,
  setRegion,
  upcoming,
  wordsFor,
} from '/src/model/occasions'
import { useI18n } from '/src/i18n'

// Special days in Settings, Appearance: always on, so nothing to switch. The
// next one as a card in its own colours and weather, the rest of the year as
// tiles, and where they are kept (found by itself, put right here).
const Particles = defineAsyncComponent(() => import('/src/components/ui/Particles.vue'))
const { t, locale } = useI18n()
const router = useRouter()
loadCalendar()
const still = prefersStill()

const detectedName = computed(() => countryName(detectedRegion.value, locale.value))
const countries = computed(() => countryChoices(calendar.value, locale.value))
const coming = computed(() => (calendar.value ? upcoming(new Date(), region.value, calendar.value, 16) : []))
const next = computed(() => coming.value[0] || null)
const rest = computed(() => coming.value.slice(1))

function words(o) {
  return wordsFor(o, t, locale.value)
}

const paint = dayColors
function flagOf(code) {
  const flag = calendar.value && calendar.value.flags && calendar.value.flags[code]
  return flag && flag.length ? flag.slice(0, 3) : ['rgb(var(--c-accent))']
}

const dayStart = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
function isToday(o) {
  const now = dayStart(new Date())
  return now >= dayStart(o.start) && now < dayStart(o.end)
}
function daysTo(o) {
  return Math.round((dayStart(o.day) - dayStart(new Date())) / 86400000)
}
function countdown(o) {
  if (isToday(o)) return t('settings.today')
  return t('settings.countdown', { count: daysTo(o) })
}
function longDate(o) {
  return new Intl.DateTimeFormat(locale.value, { weekday: 'long', day: 'numeric', month: 'long' }).format(o.day)
}
function shortWhen(o) {
  if (isToday(o)) return t('settings.today')
  const date = new Intl.DateTimeFormat(locale.value, { day: 'numeric', month: 'short' }).format(o.day)
  const days = daysTo(o)
  return days <= 7 ? `${date} · ${t('settings.countdown', { count: days })}` : date
}
// Each day has a page of its own: its music, its countdown, last year's.
function listen(o) {
  router.push(dayRoute(o))
}
</script>

<style scoped>
.sd-hero {
  position: relative;
  overflow: hidden;
  margin: 4px 0 18px;
  border-radius: 20px;
  color: #fff;
  background:
    linear-gradient(180deg, rgb(0 0 0 / 0.18), rgb(0 0 0 / 0.5)),
    linear-gradient(130deg, var(--sd-a), var(--sd-b) 60%, var(--sd-c, var(--sd-b)));
  box-shadow: 0 18px 40px rgb(0 0 0 / 0.22);
  isolation: isolate;
}
.sd-hero-body {
  position: relative;
  z-index: 1;
  display: grid;
  justify-items: start;
  gap: 6px;
  padding: 22px 24px 22px;
}
.sd-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgb(0 0 0 / 0.28);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.02em;
  backdrop-filter: blur(6px);
}
.sd-badge.is-today {
  background: #fff;
  color: #111;
}
.sd-hero-title {
  margin-top: 4px;
  font-size: clamp(22px, 2.6vw, 30px);
  font-weight: 900;
  line-height: 1.1;
  letter-spacing: -0.02em;
  text-shadow: 0 2px 18px rgb(0 0 0 / 0.25);
}
.sd-hero-date {
  font-size: 13.5px;
  font-weight: 700;
  color: rgb(255 255 255 / 0.85);
}
.sd-hero-text {
  max-width: 52ch;
  font-size: 13.5px;
  line-height: 1.45;
  color: rgb(255 255 255 / 0.88);
}
.sd-hero-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  height: 36px;
  padding: 0 16px;
  border-radius: 999px;
  background: #fff;
  color: #111;
  font-size: 13px;
  font-weight: 700;
  box-shadow: 0 8px 20px rgb(0 0 0 / 0.2);
  transition: transform 0.15s ease;
}
.sd-hero-btn:hover {
  transform: scale(1.03);
}
.sd-strip-head {
  padding: 0 2px 8px;
}
/* The rest of the year as a grid that fills the width: a strip to scroll
   sideways was one more scrollbar on a page that already scrolls. */
.sd-strip {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
  margin: 0 0 18px;
}
.sd-tile {
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
  animation: sd-in 0.4s ease both;
  animation-delay: calc(var(--i) * 30ms);
}
.sd-tile:hover {
  transform: translateY(-3px);
  box-shadow: 0 14px 28px rgb(0 0 0 / 0.24);
}
.sd-tile-icon {
  position: absolute;
  top: 10px;
  left: 10px;
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 10px;
  background: rgb(255 255 255 / 0.2);
  backdrop-filter: blur(4px);
}
.sd-tile-when {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.02em;
  color: rgb(255 255 255 / 0.85);
}
.sd-tile-name {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  font-size: 13px;
  font-weight: 800;
  line-height: 1.2;
}
.sd-region {
  margin-bottom: 16px;
}
.sd-flag {
  display: flex;
  align-self: flex-start;
  width: 36px;
  height: 26px;
  flex: none;
  overflow: hidden;
  margin: 5px 0;
  border-radius: 7px;
  box-shadow: 0 0 0 1px rgb(var(--c-tint) / 0.18);
}
.sd-flag i {
  flex: 1;
}
.sd-empty {
  margin: 4px 0 14px;
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.6);
}
@keyframes sd-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
}
@media (prefers-reduced-motion: reduce) {
  .sd-tile {
    animation: none;
  }
}
</style>
