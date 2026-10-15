// How the Stats page says its numbers: lengths of time, the scale beside a
// chart, the names under its bars, and how one stretch compares with the one
// before. Nothing here draws or fetches anything, so all of it is tested.

/** Whole minutes and hours, as `t` words them: "45 min", "3 hr 5 min", "6 hr". */
export function durationText(seconds, t) {
  const total = Math.max(0, Math.round((seconds || 0) / 60))
  const h = Math.floor(total / 60)
  const m = total % 60
  if (!h) return t('common.minutes', { m })
  // "6 hr 0 min" beside a chart is a figure with a word of noise in it.
  return m ? t('common.hoursMinutes', { h, m }) : t('common.hours', { h })
}

// Steps a time axis may count in, in seconds: the first that needs no more
// than four lines is used, so the figures beside the chart are round ones.
const STEPS = [
  60, 120, 300, 600, 900, 1800,
  3600, 7200, 10800, 21600, 43200, 86400,
]

/**
 * The scale for a chart of listening time: `{ max, ticks }`, with `max` a
 * round figure at or above the tallest bar and a tick at each step up to it.
 */
export function timeScale(maxSeconds, t) {
  const top = Math.max(60, maxSeconds || 0)
  let step = STEPS.find((s) => top / s <= 4)
  // Beyond four days a bar: count in whole days.
  if (!step) step = Math.ceil(top / 4 / 86400) * 86400
  const max = Math.ceil(top / step) * step
  const ticks = []
  for (let value = step; value <= max; value += step) {
    ticks.push({ value, label: durationText(value, t) })
  }
  return { max, ticks }
}

/** The date a bucket's label ("2026-10-14", or "2026-10" for a month) names. */
export function bucketDate(label) {
  const [y, m, d] = String(label).split('-').map(Number)
  return new Date(y, (m || 1) - 1, d || 1)
}

/** A bar's own name, in full, for its tooltip and the table behind the chart. */
export function bucketTitle(label, bucket, locale) {
  const when = bucketDate(label)
  const options =
    bucket === 'month'
      ? { month: 'long', year: 'numeric' }
      : { weekday: 'short', day: 'numeric', month: 'short' }
  return new Intl.DateTimeFormat(locale, options).format(when)
}

/**
 * The few names written under the bars: `[{ index, text }]`. Every bar has
 * one when there is room (a week of days, a year of months); otherwise every
 * few, counted back from the latest so "today" is always named.
 */
export function axisLabels(labels, bucket, locale, room = 8) {
  const n = labels.length
  if (!n) return []
  const every = Math.max(1, Math.ceil(n / room))
  const short = (label, i) => {
    const when = bucketDate(label)
    if (bucket === 'month') {
      // The year is said where it changes, and at the start. In full: "Sep
      // 26" read as the 26th of September, not as September 2026.
      const options = when.getMonth() === 0 || i === 0 ? { month: 'short', year: 'numeric' } : { month: 'short' }
      return new Intl.DateTimeFormat(locale, options).format(when)
    }
    if (n <= 7) return new Intl.DateTimeFormat(locale, { weekday: 'short' }).format(when)
    return new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' }).format(when)
  }
  const out = []
  for (let i = n - 1; i >= 0; i -= every) out.unshift({ index: i, text: short(labels[i], i) })
  return out
}

/**
 * This stretch against the one before: `{ direction, percent }`, or null when
 * there is nothing to compare with (no stretch before, or nothing in it).
 */
export function change(now, before) {
  if (!(before > 0)) return null
  const percent = Math.round(((now - before) / before) * 100)
  if (!percent) return { direction: 'same', percent: 0 }
  return { direction: percent > 0 ? 'up' : 'down', percent: Math.abs(percent) }
}

/** The hour most of the listening happens in (0-23), or -1 with none. */
export function peakHour(byHour) {
  let best = -1
  let most = 0
  ;(byHour || []).forEach((seconds, hour) => {
    if (seconds > most) {
      most = seconds
      best = hour
    }
  })
  return best
}

/** An hour of the day the way the listener's clock writes it: "9 PM", "21 h". */
export function hourText(hour, locale) {
  const text = new Intl.DateTimeFormat(locale, { hour: 'numeric' }).format(new Date(2026, 0, 1, hour))
  // Some clocks write the hour as a bare number ("09"), which on its own
  // does not read as a time.
  return /^\d+$/.test(text) ? `${text}:00` : text
}
