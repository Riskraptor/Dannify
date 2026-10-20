<template>
  <section>
    <h2 class="group-title">{{ t('settings.specialDays') }}</h2>
    <div class="row">
      <Icon icon="ph:globe-hemisphere-east" class="row-icon" />
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
    <!-- The year ahead, so it can all be seen: the days kept where you are. -->
    <div class="row sd-row">
      <Icon icon="ph:calendar-star" class="row-icon" />
      <div class="row-text">
        <p class="row-label">{{ t('settings.comingUp') }}</p>
        <p class="row-hint">{{ t('settings.comingUpHint') }}</p>
        <ol v-if="coming.length" class="sd-list">
          <li v-for="o in coming" :key="o.tag + o.day.toDateString()" class="sd-item" :class="{ 'is-today': isToday(o) }">
            <span class="sd-mark" :style="{ '--tone': toneOf(o) }"><Icon :icon="o.icon" class="h-4 w-4" /></span>
            <span class="sd-name">{{ wordsFor(o, t, locale).title }}</span>
            <span class="sd-when">{{ whenOf(o) }}</span>
          </li>
        </ol>
        <p v-else class="sd-empty">{{ t('settings.comingUpNone') }}</p>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import {
  calendar,
  countryName,
  detectedRegion,
  loadCalendar,
  region,
  regionChoice,
  setRegion,
  toneOf,
  upcoming,
  wordsFor,
} from '/src/model/occasions'
import { useI18n } from '/src/i18n'

// Special days in Settings, Appearance: always on, so nothing to switch;
// where they are kept (found by itself, and put right here when the computer
// has it wrong), and the year ahead.
const { t, locale } = useI18n()
loadCalendar()

const detectedName = computed(() => countryName(detectedRegion.value, locale.value))
// Every country the calendar knows of, by its name in this language.
const countries = computed(() => {
  const data = calendar.value
  if (!data) return []
  const codes = new Set(Object.keys(data.national || {}))
  for (const list of Object.values(data.zones || {})) for (const code of list) codes.add(code)
  const collator = new Intl.Collator(locale.value)
  return [...codes]
    .map((code) => ({ code, name: countryName(code, locale.value) }))
    .filter((c) => c.name && c.name !== c.code)
    .sort((a, b) => collator.compare(a.name, b.name))
})
const coming = computed(() => (calendar.value ? upcoming(new Date(), region.value, calendar.value, 14) : []))

const dayStart = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
function isToday(o) {
  const now = dayStart(new Date())
  return now >= dayStart(o.start) && now < dayStart(o.end)
}
function whenOf(o) {
  if (isToday(o)) return t('settings.today')
  const days = Math.round((dayStart(o.day) - dayStart(new Date())) / 86400000)
  const date = new Intl.DateTimeFormat(locale.value, { weekday: 'short', day: 'numeric', month: 'short' }).format(o.day)
  return days <= 30 ? t('settings.inDays', { count: days, date }) : date
}
</script>

<style scoped>
.sd-row {
  align-items: flex-start;
}
.sd-list {
  display: grid;
  gap: 2px;
  margin-top: 12px;
}
.sd-item {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  min-height: 36px;
  padding: 4px 8px 4px 4px;
  border-radius: 10px;
}
.sd-item.is-today {
  background: rgb(var(--c-accent) / 0.1);
}
.sd-mark {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  color: var(--tone);
  background: color-mix(in srgb, var(--tone) 16%, transparent);
}
.sd-name {
  overflow: hidden;
  font-size: 13.5px;
  font-weight: 600;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.sd-when {
  font-size: 12.5px;
  color: rgb(var(--c-fg) / 0.6);
  font-variant-numeric: tabular-nums;
}
.is-today .sd-when {
  color: rgb(var(--c-accent));
  font-weight: 700;
}
.sd-empty {
  margin-top: 8px;
  font-size: 13px;
  color: rgb(var(--c-fg) / 0.6);
}
</style>
