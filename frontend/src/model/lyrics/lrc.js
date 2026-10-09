// The LRC format, read and written, and the ways a time is shown.
//
// Lyrics arrive pasted from anywhere: a file someone made, a site that adds
// its own tags, Windows line endings. Reading is forgiving about all of it;
// writing always produces the one plain form lrclib expects.

import { outText } from '/src/model/lyricsMerge'

const STAMP = /\[(\d{1,3}):(\d{2}(?:\.\d{1,3})?)\]/
const STAMPS = /\[(\d{1,3}):(\d{2}(?:\.\d{1,3})?)\]/g
// [ar:Artist], [ti:Title], [offset:+250]: the file's own details, not words.
// Only the names the format defines: "[Hook: Drake]" is part of the lyrics.
const TAG = /^\[(ar|al|ti|au|by|re|ve|la|lr|id|tool|length|offset|#):([^\]]*)\]$/i
// Word-by-word times (<00:12.34>) from "enhanced" files: the line keeps only
// its own time, so they are noise in the words.
const WORD_STAMP = /<\d{1,3}:\d{2}(?:\.\d{1,3})?>/g

/** What an untimed line shows: clearly "no value", never a plausible 0:00. */
export const BLANK_STAMP = '--:--.--'

/** Whether the text carries any line times at all. */
export function hasStamps(text) {
  return STAMP.test(String(text || ''))
}

/** The lines of a text, trimmed, blank ones left out. */
export function splitWords(text) {
  return String(text || '')
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean)
}

/**
 * Lines of an LRC text, in the order they are written. A line stamped with
 * several times (a repeated chorus written once) becomes one line per time.
 * @returns {{time: number|null, text: string}[]}
 */
export function parseLrc(text) {
  const rows = String(text || '').split(/\r?\n/)
  let shift = 0
  for (const raw of rows) {
    const tag = raw.trim().match(TAG)
    if (tag && tag[1].toLowerCase() === 'offset') {
      // A positive offset makes the words come sooner (milliseconds).
      const ms = Number(tag[2].trim())
      if (Number.isFinite(ms)) shift = ms / 1000
    }
  }
  const out = []
  for (const raw of rows) {
    const line = raw.trim()
    if (TAG.test(line) && !STAMP.test(line)) continue
    const stamps = [...line.matchAll(STAMPS)]
    const body = line.replace(STAMPS, '').replace(WORD_STAMP, '').replace(/\s+/g, ' ').trim()
    if (!stamps.length && !body) continue
    if (!stamps.length) {
      out.push({ time: null, text: body })
      continue
    }
    for (const m of stamps) {
      const time = parseInt(m[1], 10) * 60 + parseFloat(m[2]) - shift
      out.push({ time: Math.max(0, Number(time.toFixed(3))), text: body })
    }
  }
  return out
}

/** 01:05.30, the way LRC writes a time. */
export function formatLrcTime(seconds) {
  if (seconds == null || !Number.isFinite(seconds)) return ''
  // Whole hundredths first: rounding the seconds on their own turned 59.999
  // into "00:60.00".
  const cs = Math.round(Math.max(0, seconds) * 100)
  const m = Math.floor(cs / 6000)
  const s = ((cs % 6000) / 100).toFixed(2).padStart(5, '0')
  return `${String(m).padStart(2, '0')}:${s}`
}

/** 01:05.300, the playhead to the millisecond, for timing by ear. */
export function formatClock(seconds) {
  const ms = Math.round((Number.isFinite(seconds) && seconds > 0 ? seconds : 0) * 1000)
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`
}

/** 1:05, as a lyrics view shows a time. */
export function formatShort(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** The timed lines in time order, as an LRC text. */
export function toSynced(lines) {
  return (lines || [])
    .filter((l) => l.time != null)
    .slice()
    .sort((a, b) => a.time - b.time)
    .map((l) => `[${formatLrcTime(l.time)}]${outText(l.text)}`)
    .join('\n')
}

/**
 * Every line's words, as plain text. A break between verses is one blank
 * line however many there were, and none at either end.
 */
export function toPlain(lines) {
  return (lines || [])
    .map((l) => outText(l.text))
    .filter((text, i, all) => text || all[i - 1])
    .join('\n')
    .trim()
}
