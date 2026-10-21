import { computed } from 'vue'
import { region } from '/src/model/occasions'

// The day weeks start where the listener is, Monday 0 to Sunday 6 (the way
// the stories count, see Backend listens._bounds): from the country picked or
// found in Settings, Special days, and the system's language after that.
// Sunday in Kenya and the United States, Monday in most of Europe, as every
// calendar there shows it (the browser's own calendar data, CLDR).

export function weekStartFor(regionCode, language) {
  const tags = []
  if (regionCode && /^[A-Z]{2}$/.test(regionCode)) tags.push(`und-${regionCode}`)
  if (language) tags.push(language)
  for (const tag of tags) {
    try {
      const loc = new Intl.Locale(tag)
      const info = typeof loc.getWeekInfo === 'function' ? loc.getWeekInfo() : loc.weekInfo
      if (info && info.firstDay >= 1 && info.firstDay <= 7) return info.firstDay - 1
    } catch {
      // an engine without week data: the next guess
    }
  }
  return 0
}

function language() {
  try {
    return navigator.language || ''
  } catch {
    return ''
  }
}

export const weekStart = computed(() => weekStartFor(region.value, language()))

/** Which day of its week a date is, counted from the week's own first day. */
export function dayOfWeek(date, start = weekStart.value) {
  return ((date.getDay() + 6) % 7 - start + 7) % 7
}
