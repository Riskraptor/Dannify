// Timing rules for the sync editor: what counts as a mistake, which line the
// song has reached, and how much has to be timed before it can go out.
//
// Everything here is plain arithmetic over `{text, time}` lines (time in
// seconds, or null while untimed), so it is the same in the editor and in
// the tests.

/** A line timed closer than this to the one before it flashes past unread. */
export const WARN_GAP = 0.2
/** The line to tap next lights up this much before the one above it ends. */
export const LOOK_AHEAD = 0.25
/** How far one nudge moves a line. */
export const NUDGE_STEP = 0.1

/** A time as the editor stores it: never negative, to the millisecond. */
export function roundTime(seconds) {
  return Math.max(0, Number((Number(seconds) || 0).toFixed(3)))
}

export function nudgeTime(seconds, delta) {
  return roundTime(seconds + delta)
}

/**
 * Each timed line that is wrong or doubtful, by index.
 *   error: timed before a line above it, so it would show out of order
 *   warn:  within WARN_GAP of the line above, too quick to read
 * @returns {Object<number, {error?: true, warn?: true}>}
 */
export function stampQuality(lines) {
  const out = {}
  let prev = -Infinity
  ;(lines || []).forEach((line, i) => {
    const t = line.time
    if (t == null) return
    if (t < prev) out[i] = { error: true }
    else if (t - prev < WARN_GAP) out[i] = { warn: true }
    prev = t
  })
  return out
}

/** The indexes of the lines that are out of order, top to bottom. */
export function issueIndexes(quality) {
  return Object.entries(quality || {})
    .filter(([, q]) => q.error)
    .map(([i]) => Number(i))
    .sort((a, b) => a - b)
}

/** The first issue below `current`, or the first one of all after the last. */
export function nextIssue(issues, current) {
  if (!issues || !issues.length) return -1
  return issues.find((i) => i > current) ?? issues[0]
}

export function countTimed(lines) {
  return (lines || []).filter((l) => l.time != null).length
}

/**
 * How many lines must be timed for the timing to be worth publishing: half
 * the song, and at least two. A song of one line needs just that line.
 */
export function minTimed(total) {
  if (!total) return 0
  return Math.min(total, Math.max(2, Math.ceil(total * 0.5)))
}

export function enoughTimed(lines) {
  const total = (lines || []).length
  return total > 0 && countTimed(lines) >= minTimed(total)
}

/**
 * The line the song has reached, for the editor to follow: the one after the
 * latest line whose time has come, because that is the one about to be
 * tapped. -1 when nothing is timed yet.
 */
export function predictLine(lines, now) {
  let best = -1
  let bestTime = -Infinity
  ;(lines || []).forEach((line, i) => {
    const t = line.time
    if (t != null && t <= now + LOOK_AHEAD && t > bestTime) {
      bestTime = t
      best = i
    }
  })
  if (best >= 0 && best < lines.length - 1) return best + 1
  return best
}

/**
 * The stretch of song to repeat while a line is worked on: a moment before
 * it starts and a little after. An untimed line is placed between its timed
 * neighbours, or failing those, at the playhead.
 * @returns {{start: number, end: number}}
 */
export function loopWindow(lines, idx, now = 0, duration = 0) {
  const line = lines[idx]
  let t = line ? line.time : null
  if (t == null) {
    const prev = lines.slice(0, idx).reverse().find((l) => l.time != null)
    const next = lines.slice(idx + 1).find((l) => l.time != null)
    if (prev && next) t = (prev.time + next.time) / 2
    else if (prev) t = prev.time + 1.5
    else if (next) t = Math.max(0, next.time - 1.5)
    else t = now || 0
  }
  return {
    start: Math.max(0, t - 1.5),
    end: Math.min(duration || t + 2, t + 2),
  }
}

/** Where each timed line sits along the song, for the marks on the rail. */
export function stampTicks(lines, duration, quality = {}) {
  const d = duration || 1
  const out = []
  ;(lines || []).forEach((line, i) => {
    if (line.time == null) return
    out.push({
      index: i,
      time: line.time,
      text: line.text,
      left: Math.min(100, Math.max(0, (line.time / d) * 100)),
      error: !!quality[i]?.error,
    })
  })
  return out
}
