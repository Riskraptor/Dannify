// Repeating a part of the lyrics: a chorus sung four times is typed once.
//
// Everything works on whole lines of the words box: a selection that starts
// or ends inside a line takes all of it, and a cursor with nothing selected
// is the line it is on.

/** The whole lines a selection touches, as offsets: `[start, end)`. */
export function lineSpan(text, from, to = from) {
  const a = Math.max(0, Math.min(from, to))
  let b = Math.max(from, to)
  // Selected down to the start of the next line: that line is not in it.
  if (b > a && text[b - 1] === '\n') b -= 1
  const start = text.lastIndexOf('\n', a - 1) + 1
  let end = text.indexOf('\n', b)
  if (end < 0) end = text.length
  return { start, end: Math.max(start, end) }
}

/**
 * The lines touched by the selection, again, right below them.
 * @returns {{text: string, part: string, selStart: number, selEnd: number} | null}
 *   the new text, the part repeated, and where its copy is (to select it, so
 *   a second press repeats it once more); null when there is nothing to repeat.
 */
export function repeatLines(text, from, to = from) {
  const { start, end } = lineSpan(text, from, to)
  const part = text.slice(start, end)
  if (!part.trim()) return null
  return {
    text: `${text.slice(0, end)}\n${part}${text.slice(end)}`,
    part,
    selStart: end + 1,
    selEnd: end + 1 + part.length,
  }
}

/**
 * `part` as lines of their own at the cursor: in place of the line it is on
 * when that line is empty, below it otherwise.
 * @returns {{text: string, selStart: number, selEnd: number} | null}
 */
export function insertPart(text, at, part) {
  if (!part || !part.trim()) return null
  const { start, end } = lineSpan(text, at, at)
  if (!text.slice(start, end).trim()) {
    return { text: text.slice(0, start) + part + text.slice(end), selStart: start, selEnd: start + part.length }
  }
  return {
    text: `${text.slice(0, end)}\n${part}${text.slice(end)}`,
    selStart: end + 1,
    selEnd: end + 1 + part.length,
  }
}

/** How a remembered part is named on its button: its first words. */
export function partLabel(part, max = 26) {
  const first = String(part || '').split('\n').find((l) => l.trim()) || ''
  const line = first.trim()
  return line.length > max ? `${line.slice(0, max - 1).trimEnd()}…` : line
}
