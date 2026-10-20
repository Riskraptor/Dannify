// Sending finished lyrics to the shared catalogue, through the backend.
//
// The backend answers 200 either way, with `{published, reason}`; the
// connection failing is a different thing again. Both come back here as one
// shape, so the editor has a single place to decide what to say. The
// catalogue's own words never reach the screen: only the kind of failure,
// said in the person's language.

import API from '/src/model/api'
import { failedForNetwork } from '/src/model/connectivity'

/**
 * @param {{track: string, artist: string, album: string, duration: number,
 *          plain: string, synced: string}} payload
 * @returns {Promise<{ok: true} | {ok: false, reason: 'busy'|'refused'|'slow'|'invalid'|'offline'|'timeout'|'failed'}>}
 */
export async function sendLyrics(payload) {
  let res
  try {
    res = await API.publishLyrics(payload)
  } catch (err) {
    if (err && (err.code === 'ECONNABORTED' || err.code === 'ETIMEDOUT')) return { ok: false, reason: 'timeout' }
    if (await failedForNetwork(err)) return { ok: false, reason: 'offline' }
    return { ok: false, reason: 'failed' }
  }
  const data = (res && res.data) || {}
  if (data.published) return { ok: true }
  return { ok: false, reason: REASONS.has(data.reason) ? data.reason : 'failed' }
}

const REASONS = new Set(['busy', 'refused', 'slow', 'invalid', 'offline'])

/** Tell the rest of the app, so the player pulls the new words in. */
export function announcePublished(track, artist) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent('dannify:lyrics-published', { detail: { track, artist } }))
}

/** Every way into the editor goes through App.vue's one instance of it. */
export function openLyricsEditor() {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent('dannify:open-lyrics-submit'))
}
