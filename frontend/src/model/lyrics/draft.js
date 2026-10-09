// Unfinished lyrics, kept on this machine until they are published.
//
// A draft belongs to the song the editor was opened on, not to the title
// typed into it: a corrected title used to file the draft under a name it
// was never looked up by again, and the work was gone the next time.

const PREFIX = 'dannify-lyric-draft|'

/** The storage key of a song's draft. Same shape as the drafts already saved. */
export function draftKey(track, artist) {
  return `${PREFIX}${String(track || '').toLowerCase()}|${String(artist || '').toLowerCase()}`
}

function store() {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null
  } catch {
    return null
  }
}

/**
 * The draft saved under `key`, or null when there is none or it is not one
 * this editor can read.
 * @returns {{form: object, lines: {text: string, time: number|null}[],
 *            phase: number, seed: object[], from: string|null}|null}
 */
export function loadDraft(key) {
  try {
    const raw = store()?.getItem(key)
    if (!raw) return null
    const data = JSON.parse(raw)
    const form = data && data.form
    if (!form || typeof form !== 'object' || typeof form.raw !== 'string') return null
    return {
      form: {
        track: String(form.track || ''),
        artist: String(form.artist || ''),
        album: String(form.album || ''),
        duration: Number(form.duration) || 0,
        raw: form.raw,
      },
      lines: Array.isArray(data.lines)
        ? data.lines.map((l) => ({
            text: String(l?.text || ''),
            time: Number.isFinite(l?.time) ? l.time : null,
          }))
        : [],
      phase: Math.max(0, Math.min(2, Number(data.phase) || 0)),
      seed: Array.isArray(data.seed) ? data.seed : [],
      // What the line list was built from; older drafts did not say.
      from: typeof data.from === 'string' ? data.from : form.raw,
    }
  } catch {
    return null
  }
}

export function saveDraft(key, draft) {
  try {
    store()?.setItem(key, JSON.stringify(draft))
    return true
  } catch {
    // Full or blocked storage: the editor still works, it just forgets.
    return false
  }
}

export function clearDraft(key) {
  try {
    store()?.removeItem(key)
  } catch {
    // Nothing to do: there was nothing it could have kept either.
  }
}
