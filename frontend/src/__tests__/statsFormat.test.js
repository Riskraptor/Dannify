import { describe, expect, it } from 'vitest'
import {
  axisLabels,
  bucketDate,
  bucketTitle,
  change,
  durationText,
  hourText,
  peakHour,
  timeScale,
} from '../model/statsFormat.js'

// The words the app would say them in, near enough.
const t = (key, p) =>
  key === 'common.hoursMinutes' ? `${p.h} hr ${p.m} min` : key === 'common.hours' ? `${p.h} hr` : `${p.m} min`

describe('durationText()', () => {
  it('says minutes, and hours once there are any', () => {
    expect(durationText(0, t)).toBe('0 min')
    expect(durationText(59, t)).toBe('1 min')
    expect(durationText(45 * 60, t)).toBe('45 min')
    expect(durationText(3 * 3600 + 5 * 60, t)).toBe('3 hr 5 min')
  })
  it('never says sixty minutes, nor nought', () => {
    expect(durationText(3599, t)).toBe('1 hr')
    expect(durationText(6 * 3600, t)).toBe('6 hr')
  })
})

describe('timeScale()', () => {
  it('counts in round figures, in no more than four steps', () => {
    for (const max of [0, 40, 61, 500, 1800, 5400, 20000, 86400, 3 * 86400, 30 * 86400]) {
      const scale = timeScale(max, t)
      expect(scale.max).toBeGreaterThanOrEqual(Math.max(60, max))
      expect(scale.ticks.length).toBeGreaterThan(0)
      expect(scale.ticks.length).toBeLessThanOrEqual(4)
      expect(scale.ticks[scale.ticks.length - 1].value).toBe(scale.max)
    }
  })
  it('picks the step a person would', () => {
    // An hour and a half at most: half-hour lines.
    expect(timeScale(5400, t).ticks.map((x) => x.label)).toEqual(['30 min', '1 hr', '1 hr 30 min'])
    // Four minutes at most: a line a minute.
    expect(timeScale(240, t).ticks.map((x) => x.value)).toEqual([60, 120, 180, 240])
  })
})

describe('the names under the bars', () => {
  const week = ['2026-10-08', '2026-10-09', '2026-10-10', '2026-10-11', '2026-10-12', '2026-10-13', '2026-10-14']

  it('reads a day or a month label as a date here', () => {
    expect(bucketDate('2026-10-14').getDate()).toBe(14)
    expect(bucketDate('2026-10-14').getMonth()).toBe(9)
    expect(bucketDate('2026-10').getDate()).toBe(1)
  })

  it('names every day of a week', () => {
    const labels = axisLabels(week, 'day', 'en')
    expect(labels.map((l) => l.index)).toEqual([0, 1, 2, 3, 4, 5, 6])
    expect(labels[6].text).toBe('Wed')
  })

  it('names every few days of a month, always including the latest', () => {
    const month = Array.from({ length: 30 }, (_, i) => `2026-09-${String(i + 1).padStart(2, '0')}`)
    const labels = axisLabels(month, 'day', 'en')
    expect(labels.length).toBeLessThanOrEqual(8)
    expect(labels[labels.length - 1]).toEqual({ index: 29, text: 'Sep 30' })
  })

  it('says the year where it changes', () => {
    const months = ['2025-11', '2025-12', '2026-01', '2026-02']
    expect(axisLabels(months, 'month', 'en').map((l) => l.text)).toEqual(['Nov 2025', 'Dec', 'Jan 2026', 'Feb'])
  })

  it('names a bar in full for its tooltip', () => {
    expect(bucketTitle('2026-10-14', 'day', 'en')).toBe('Wed, Oct 14')
    expect(bucketTitle('2026-10', 'month', 'en')).toBe('October 2026')
  })

  it('has nothing to name with no bars', () => {
    expect(axisLabels([], 'day', 'en')).toEqual([])
  })
})

describe('change()', () => {
  it('compares a stretch with the one before', () => {
    expect(change(150, 100)).toEqual({ direction: 'up', percent: 50 })
    expect(change(50, 100)).toEqual({ direction: 'down', percent: 50 })
    expect(change(100, 100)).toEqual({ direction: 'same', percent: 0 })
  })
  it('has nothing to say when there was nothing before', () => {
    expect(change(100, 0)).toBeNull()
    expect(change(100, undefined)).toBeNull()
  })
})

describe('the hours of the day', () => {
  it('finds the hour with the most listening', () => {
    const hours = new Array(24).fill(0)
    hours[21] = 900
    hours[8] = 300
    expect(peakHour(hours)).toBe(21)
    expect(peakHour(new Array(24).fill(0))).toBe(-1)
    expect(peakHour(undefined)).toBe(-1)
  })
  it('writes an hour the way the listener does', () => {
    expect(hourText(21, 'en-US')).toMatch(/9\s?PM/i)
    expect(hourText(21, 'fr')).toMatch(/21/)
    // A clock that writes a bare number still reads as a time.
    expect(hourText(9, 'en-GB')).toBe('09:00')
  })
})
