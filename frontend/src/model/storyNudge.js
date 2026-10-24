// "Your week in music is ready": once, early in a new week, a word that last
// week's story can be seen, and on the first days of a month the same for the
// month gone. Only when there is a story worth seeing, never twice for the
// same stretch, and as a toast that goes by itself, never a pop-up.

import { navigate } from '/src/model/navigate'
import API from '/src/model/api'
import { t, currentLocale } from '/src/i18n'
import { toast } from '/src/model/toast'
import { dayOfWeek, weekStart } from '/src/model/weekStart'

const WEEK_KEY = 'dn.nudge.week'
const MONTH_KEY = 'dn.nudge.month'
// Enough listening for a story: a few songs a day.
export const WEEK_PLAYS = 10
export const MONTH_PLAYS = 25

function read(key) {
  try {
    return localStorage.getItem(key) || ''
  } catch {
    return ''
  }
}
function write(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // shown again next start, at worst
  }
}

function iso(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function open(query) {
  navigate({ name: 'Recap', query })
}

/** Say so if last month's or last week's story is ready and not yet seen. */
export async function nudgeStories(now = new Date()) {
  const start = weekStart.value
  // The month gone, on the first three days of a new one: the bigger news.
  if (now.getDate() <= 3) {
    const month = `${now.getFullYear()}-${now.getMonth() + 1}`
    if (read(MONTH_KEY) !== month) {
      try {
        const res = await API.getStory('month', 0, 1, start)
        // Asked and answered: not again this month, shown or not.
        write(MONTH_KEY, month)
        if ((res.data && res.data.plays) >= MONTH_PLAYS) {
          const name = new Date(now.getFullYear(), now.getMonth() - 1, 1).toLocaleDateString(currentLocale.value || 'en', {
            month: 'long',
          })
          toast(t('story.nudgeMonth', { month: name }), {
            icon: 'ph:confetti',
            timeout: 14000,
            action: { label: t('story.nudgeSee'), run: () => open({ period: 'month', ago: 1 }) },
          })
          return 'month'
        }
      } catch {
        // offline: asked again at the next start
      }
    }
  }
  // The week gone, on the first two days of a new one.
  const into = dayOfWeek(now, start)
  if (into > 1) return ''
  const weekStarted = new Date(now.getFullYear(), now.getMonth(), now.getDate() - into)
  const key = iso(weekStarted)
  if (read(WEEK_KEY) === key) return ''
  try {
    const res = await API.getStory('week', 0, 1, start)
    write(WEEK_KEY, key)
    if ((res.data && res.data.plays) >= WEEK_PLAYS) {
      toast(t('story.nudgeWeek'), {
        icon: 'ph:confetti',
        timeout: 14000,
        action: { label: t('story.nudgeSee'), run: () => open({ period: 'week', ago: 1 }) },
      })
      return 'week'
    }
  } catch {
    // offline: asked again at the next start
  }
  return ''
}
