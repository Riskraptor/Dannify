// The moments of a stretch of listening, said: the records, runs of days,
// climbs, comebacks and firsts that Backend listens._insights finds and ranks.
// Home's "Your music lately" and the stories both speak them.

export const PERIODS = ['day', 'week', 'month', 'year']

const ICONS = {
  more: 'ph:trend-up-bold',
  record_day: 'ph:trophy-fill',
  streak: 'ph:flame-fill',
  every_day: 'ph:calendar-check-fill',
  milestone_hours: 'ph:star-fill',
  milestone_plays: 'ph:star-fill',
  new_in_top: 'ph:sparkle-fill',
  climber: 'ph:trend-up-bold',
  comeback: 'ph:clock-counter-clockwise',
  new_artists: 'ph:compass-fill',
  top_song: 'ph:crown',
  repeat: 'ph:repeat-bold',
  loyal: 'ph:heart-fill',
  night: 'ph:moon-stars-fill',
  morning: 'ph:sun-horizon-fill',
  variety: 'ph:music-notes-fill',
}

export function momentIcon(m) {
  return ICONS[m && m.kind] || 'ph:headphones'
}

function todayISO() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/**
 * A moment in words.
 * @param {object} m one of a story's insights
 * @param {string} period day, week, month or year
 * @param {Function} t the app's words
 * @param {{number?: Function, dateText?: Function}} how numbers and dates are written
 */
export function momentText(m, period, t, { number = String, dateText = (iso) => iso } = {}) {
  const title = (m.song && m.song.title) || ''
  switch (m.kind) {
    case 'more':
      return t(`story.moment.more.${period}`, { percent: number(m.percent) })
    case 'record_day':
      return m.date === todayISO()
        ? t('story.moment.recordToday', { minutes: number(m.minutes) })
        : t('story.moment.record', { minutes: number(m.minutes), date: dateText(m.date) })
    case 'streak':
      return t('story.moment.streak', { count: m.days })
    case 'every_day':
      return t('story.moment.everyDay', { count: m.days })
    case 'milestone_hours':
      return t('story.moment.hours', { hours: number(m.hours) })
    case 'milestone_plays':
      return t('story.moment.plays', { plays: number(m.plays) })
    case 'new_in_top':
      return t('story.moment.newInTop', { artist: m.artist, rank: m.rank })
    case 'climber':
      return t('story.moment.climber', { artist: m.artist, from: m.from, rank: m.rank })
    case 'comeback':
      return t('story.moment.comeback', { title, count: m.days })
    case 'new_artists':
      return t('story.moment.newArtists', { count: m.count, artist: m.artist })
    case 'top_song':
      return t('story.moment.topSong', { title, count: m.plays })
    case 'repeat':
      return t('story.moment.repeat', { title, count: m.plays })
    case 'loyal':
      return t('story.moment.loyal', { artist: m.artist, percent: m.percent })
    case 'night':
      return t('story.moment.night', { percent: m.percent })
    case 'morning':
      return t('story.moment.morning', { percent: m.percent })
    case 'variety':
      return t('story.moment.variety', { count: m.songs, artists: number(m.artists) })
    default:
      return t('story.moment.minutes', { count: m.minutes || 0, minutes: number(m.minutes || 0) })
  }
}
