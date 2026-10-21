// "Your listening personality" in Your year in music: what a year of
// listening says about the listener, read from the recap (Backend
// listens.recap). The first that fits, in this order: the strongest signals
// first, a warm default last.

const share = (hours, from, to) => {
  let sum = 0
  for (let h = from; h !== to; h = (h + 1) % 24) sum += hours[h] || 0
  return sum
}

export const PERSONAS = {
  nightOwl: { icon: 'ph:moon-stars-fill' },
  earlyBird: { icon: 'ph:sun-horizon-fill' },
  devoted: { icon: 'ph:heart-fill' },
  repeater: { icon: 'ph:repeat-bold' },
  explorer: { icon: 'ph:compass-fill' },
  daily: { icon: 'ph:calendar-check-fill' },
  lover: { icon: 'ph:music-notes-fill' },
}

/**
 * @param {object} d the recap
 * @param {object[]} songRows its top songs as rows (for the top song's title)
 * @returns {{id: string, icon: string, params: object}}
 */
export function personaOf(d, songRows = []) {
  const pick = (id, params = {}) => ({ id, icon: PERSONAS[id].icon, params })
  if (!d || !d.seconds) return pick('lover', { count: 0, artists: 0 })
  const total = d.seconds
  const hours = d.hours || []
  const top = (d.top_artists || [])[0]
  const topSong = (d.top_songs || [])[0]

  if (share(hours, 22, 4) / total >= 0.3) return pick('nightOwl')
  if (share(hours, 5, 10) / total >= 0.3) return pick('earlyBird')
  if (top && top.seconds / total >= 0.35) {
    return pick('devoted', { artist: top.name, percent: Math.round((top.seconds / total) * 100) })
  }
  if (topSong && topSong.plays >= 25) {
    return pick('repeater', { title: (songRows[0] && songRows[0].title) || topSong.title || '', count: topSong.plays })
  }
  if ((d.new_artists || 0) >= 15) return pick('explorer', { count: d.new_artists })
  if ((d.longest_streak || 0) >= 14) return pick('daily', { count: d.longest_streak })
  return pick('lover', { count: d.songs || 0, artists: d.artists || 0 })
}
