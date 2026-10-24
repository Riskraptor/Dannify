// What the mixes are, and how Recently Added is chosen: kept apart from
// mixes.js, which needs the player, so they can be tested on their own.

// How each one is named and drawn. Written out in full: the icons are found
// in the source by name (vite.config.js).
export const MIXES = {
  on_repeat: { title: 'mixes.onRepeat', text: 'mixes.onRepeatText', icon: 'ph:repeat', tone: 'mix-repeat' },
  top_month: { title: 'mixes.topMonth', text: 'mixes.topMonthText', icon: 'ph:crown-simple', tone: 'mix-top' },
  forgotten: { title: 'mixes.forgotten', text: 'mixes.forgottenText', icon: 'ph:heart', tone: 'mix-forgotten' },
  recent: { title: 'mixes.recent', text: 'mixes.recentText', icon: 'ph:sparkle', tone: 'mix-recent' },
  right_now: { title: 'mixes.rightNow', text: 'mixes.rightNowText', icon: 'ph:clock-countdown', tone: 'mix-now' },
}
export const MIX_ORDER = ['right_now', 'on_repeat', 'top_month', 'recent', 'forgotten']

const RECENT = 40

/** The newest saved songs, newest first. */
export function recentlyAdded(tracks, limit = RECENT) {
  return [...(tracks || [])]
    .filter((tr) => tr && tr.file && !tr.problem)
    .sort((a, b) => (b.added || 0) - (a.added || 0))
    .slice(0, limit)
}

/**
 * The covers for a mix's picture: one per album, so four songs from the same
 * record do not make a picture of one cover four times.
 */
export function mixCovers(rows, count = 4) {
  const seen = new Set()
  const out = []
  for (const row of rows || []) {
    if (!row || !row.cover) continue
    const album = String(row.album || '').trim().toLowerCase()
    const artist = String(row.primaryArtist || row.artistText || '').trim().toLowerCase()
    const key = album ? `${artist}|${album}` : row.cover
    if (seen.has(key) || seen.has(row.cover)) continue
    seen.add(key)
    seen.add(row.cover)
    out.push(row.cover)
    if (out.length >= count) break
  }
  return out
}
