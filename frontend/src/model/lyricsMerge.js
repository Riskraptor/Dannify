// Words edited after they were timed keep the timing they had.
//
// Someone fixing a typo in line 12 of lyrics that are already in time should
// not have to time the whole song again. Every line that is still the same
// keeps its time; a line changed in place (as many lines between two kept
// ones as there were before) keeps the time of the line it replaced. Only a
// line that is really new comes back untimed.

/** Instrumental breaks are written as this in the words. */
export const BREAK = '♪'

function norm(text) {
  return String(text || '')
    .normalize('NFKC')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
}

/**
 * @param {string[]} texts the lines as they are now
 * @param {{text: string, time: number|null}[]} timed the lines as they were
 * @returns {{text: string, time: number|null}[]}
 */
export function mergeTimes(texts, timed) {
  const old = (timed || []).filter((l) => l && l.time != null)
  const out = texts.map((text) => ({ text, time: null, from: -1 }))

  // Lines that did not change, in order.
  let next = 0
  for (const line of out) {
    const key = norm(line.text)
    for (let x = next; x < old.length; x++) {
      if (norm(old[x].text) === key) {
        line.time = old[x].time
        line.from = x
        next = x + 1
        break
      }
    }
  }

  // Lines changed in place: between two kept lines, as many now as before.
  let before = -1
  let gap = []
  const settle = (after) => {
    const replaced = []
    for (let x = before + 1; x < after; x++) replaced.push(x)
    if (gap.length && gap.length === replaced.length) {
      gap.forEach((line, i) => {
        line.time = old[replaced[i]].time
      })
    }
    gap = []
  }
  for (const line of out) {
    if (line.from >= 0) {
      settle(line.from)
      before = line.from
    } else {
      gap.push(line)
    }
  }
  settle(old.length)

  return out.map(({ text, time }) => ({ text, time }))
}

/** The words of a list of lines, a break as ♪, for editing as text. */
export function wordsOf(lines) {
  return (lines || []).map((l) => (String(l.text || '').trim() ? l.text : BREAK)).join('\n')
}

/** A line's words as they go out: a break is an empty line. */
export function outText(text) {
  const s = String(text || '').trim()
  return s === BREAK ? '' : s
}
