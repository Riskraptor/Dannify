// When each word of a lyric line is sung, so the line can light up word by
// word as the voice reaches it.
//
// Some lyrics carry the time of every word (enhanced LRC, read by the
// Backend's parse_lrc), and those are followed exactly. The rest only say
// when each line starts, and there the words are spread by how long they
// take to sing: syllables, at an unhurried pace, inside the time before the
// next line. Running ahead of the voice looks worse than trailing it, so the
// estimate errs slow.

// Seconds per syllable when guessing: about four a second, a little behind
// most singing.
const SYLLABLE = 0.26
// The shortest and longest a line is taken to be sung over.
const SHORTEST = 0.6
const LONGEST = 9
// A word is never drawn for longer than this: a held note keeps its colour
// without the sweep crawling.
const HOLD = 2.5
// How long the last line runs when nothing follows it.
const LAST_LINE = 5

// Scripts written without spaces between words, where every character is a
// syllable of its own.
const DENSE = /[぀-ヿ㐀-鿿가-힯豈-﫿]/gu
const VOWELS = /[aeiouyàáâãäåæèéêëìíîïòóôõöøœùúûüýÿаеёиоуыэюяіїєαεηιουω]+/giu

/** Roughly how many syllables it takes to sing *word*. At least one. */
export function syllables(word) {
  const text = String(word || '')
  const dense = text.match(DENSE)
  if (dense) return dense.length
  const groups = text.match(VOWELS)
  if (groups) return groups.length
  const letters = text.match(/\p{L}/gu)
  return letters ? Math.max(1, Math.round(letters.length / 3)) : 0
}

/** A line's words as shown, each keeping the space after it. */
export function splitLineWords(text) {
  const out = String(text || '').match(/\S+\s*/g) || []
  // Characters of a script without spaces are sung one by one.
  return out.flatMap((w) => (w.match(DENSE) && !/\s/.test(w.trim()) ? w.match(/./gu) : [w]))
}

/**
 * The words of *line* with when each is sung and for how long.
 *
 * *next* is when the following line starts (or null for the last line).
 * Returns `{ words: [{ time, text, dur }], exact }`, `exact` when the times
 * came with the lyrics, or no words for a line with nothing to sing.
 */
export function lineWords(line, next) {
  if (!line || line.time == null) return { words: [], exact: false }
  const start = Number(line.time)
  const after = Number.isFinite(next) && next > start ? next : start + LAST_LINE

  if (Array.isArray(line.words) && line.words.length) {
    const end = Number.isFinite(line.end) && line.end > start ? Math.min(line.end, after) : after
    const words = line.words.map((w, i) => {
      const to = i + 1 < line.words.length ? line.words[i + 1].time : end
      return { time: w.time, text: w.text, dur: clamp(to - w.time, 0.05, HOLD) }
    })
    return { words, exact: true }
  }

  const pieces = splitLineWords(line.text)
  const weights = pieces.map(syllables)
  const total = weights.reduce((a, b) => a + b, 0)
  if (!total) return { words: [], exact: false }
  const gap = after - start
  // Inside the gap, with a breath before the next line; a line followed
  // quickly by the next is sung in the time there is.
  const span = gap <= SHORTEST + 0.2 ? gap * 0.9 : clamp(total * SYLLABLE, SHORTEST, Math.min(LONGEST, gap - 0.2))
  let at = start
  const words = pieces.map((text, i) => {
    const dur = (span * weights[i]) / total
    const word = { time: Number(at.toFixed(3)), text, dur: clamp(dur, 0.05, HOLD) }
    at += dur
    return word
  })
  return { words, exact: false }
}

/** Which word is being sung at *t*: its index, or -1 before the first. */
export function wordAt(words, t) {
  let idx = -1
  for (let i = 0; i < words.length; i++) {
    if (words[i].time <= t) idx = i
    else break
  }
  return idx
}

function clamp(n, lo, hi) {
  return Math.max(lo, Math.min(hi, n))
}
