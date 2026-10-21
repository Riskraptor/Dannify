import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

// Weeks that start where the listener is, and the word, once, early in a new
// week or month that its story is ready (model/weekStart.js, storyNudge.js).

const env = vi.hoisted(() => ({ plays: { week: 0, month: 0 }, asked: [], toasts: [], store: {} }))
vi.mock('/src/model/occasions', () => ({ region: ref('KE') }))
vi.mock('/src/model/api', () => ({
  default: {
    getStory: vi.fn((period, year, ago, weekStart) => {
      env.asked.push({ period, ago, weekStart })
      return Promise.resolve({ data: { plays: env.plays[period] } })
    }),
  },
}))
vi.mock('/src/model/toast', () => ({ toast: (msg, opts) => env.toasts.push({ msg, opts }) }))
vi.mock('/src/i18n', () => ({ t: (key, p) => (p && p.month ? `${key}:${p.month}` : key), currentLocale: ref('en') }))
vi.mock('/src/router', () => ({ default: { push: vi.fn() } }))

beforeEach(() => {
  vi.resetModules()
  env.asked.length = 0
  env.toasts.length = 0
  env.store = {}
  env.plays = { week: 0, month: 0 }
  vi.stubGlobal('localStorage', {
    getItem: (k) => env.store[k] ?? null,
    setItem: (k, v) => (env.store[k] = String(v)),
    removeItem: (k) => delete env.store[k],
  })
})

describe('the first day of the week', () => {
  it('follows the country', async () => {
    const { weekStartFor } = await import('../model/weekStart.js')
    expect(weekStartFor('US')).toBe(6)
    expect(weekStartFor('DE')).toBe(0)
    expect(weekStartFor('', 'en-GB')).toBe(0)
    expect(weekStartFor('nonsense', '')).toBe(0)
  })

  it('counts a day from it', async () => {
    const { dayOfWeek } = await import('../model/weekStart.js')
    const sunday = new Date(2026, 9, 18)
    expect(dayOfWeek(sunday, 6)).toBe(0)
    expect(dayOfWeek(sunday, 0)).toBe(6)
    expect(dayOfWeek(new Date(2026, 9, 19), 0)).toBe(0)
  })
})

describe('the story nudge', () => {
  it('says last week is ready, once, early in the week', async () => {
    env.plays.week = 30
    const { nudgeStories } = await import('../model/storyNudge.js')
    // Monday the 19th, weeks from Monday (Germany).
    const monday = new Date(2026, 9, 19, 10)
    const { weekStartFor } = await import('../model/weekStart.js')
    expect(weekStartFor('KE')).toBe(6)
    // Kenya's weeks start on Sunday: Monday is the week's second day, still early.
    expect(await nudgeStories(monday)).toBe('week')
    expect(env.asked[0]).toEqual({ period: 'week', ago: 1, weekStart: 6 })
    expect(env.toasts[0].msg).toBe('story.nudgeWeek')
    expect(env.toasts[0].opts.action.label).toBe('story.nudgeSee')
    expect(await nudgeStories(monday)).toBe('')
    expect(env.toasts).toHaveLength(1)
  })

  it('stays quiet mid-week, and after a quiet week', async () => {
    const { nudgeStories } = await import('../model/storyNudge.js')
    expect(await nudgeStories(new Date(2026, 9, 22, 10))).toBe('')
    expect(env.asked).toHaveLength(0)
    env.plays.week = 3
    expect(await nudgeStories(new Date(2026, 9, 18, 10))).toBe('')
    expect(env.toasts).toHaveLength(0)
  })

  it('says the month gone is ready on its first days', async () => {
    env.plays.month = 80
    const { nudgeStories } = await import('../model/storyNudge.js')
    expect(await nudgeStories(new Date(2026, 10, 2, 10))).toBe('month')
    expect(env.toasts[0].msg).toBe('story.nudgeMonth:October')
  })
})
