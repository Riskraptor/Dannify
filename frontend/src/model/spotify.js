import { computed, shallowRef } from 'vue'
import API from '/src/model/api'
import { desktop } from '/src/desktop/bridge'
import { playRows } from '/src/model/tracks'
import { usePlaylists } from '/src/model/playlists'
import { toast } from '/src/model/toast'
import { t } from '/src/i18n'

// Spotify, for whoever signs in. The backend does the signing in and the
// asking (Backend/dannify/spotify_account.py); this keeps what the window
// shows about it, opens Spotify's page in the browser, and notices when the
// person comes back signed in.

const EMPTY = { configured: false, own_app: false, connected: false, signing_in: false, user: {}, error: '' }
const status = shallowRef(EMPTY)
let watching = 0
let asked = null

export async function refreshSpotify() {
  try {
    status.value = { ...EMPTY, ...(await API.spotifyStatus()).data }
  } catch {
    // The backend is starting or gone: what was known stays.
  }
  return status.value
}

function changed() {
  window.dispatchEvent(new CustomEvent('dannify:spotify-changed'))
}

// While Spotify's page is open in the browser, look now and then for the
// answer, and at once when the window comes back to the front.
function watchSignIn() {
  stopWatching()
  const until = Date.now() + 10 * 60 * 1000
  const look = async () => {
    const now = await refreshSpotify()
    if (now.connected) {
      stopWatching()
      toast(t('spotify.connectedToast', { name: now.user.name || '' }), { icon: 'ph:spotify-logo-fill', tone: 'success' })
      changed()
    } else if (!now.signing_in || Date.now() > until) {
      stopWatching()
      if (now.error && now.error !== 'denied') toast(t(errorKey(now.error)), { tone: 'error', timeout: 9000 })
    }
  }
  watching = setInterval(look, 1500)
  window.addEventListener('focus', look)
  asked = look
}
function stopWatching() {
  if (watching) clearInterval(watching)
  watching = 0
  if (asked) window.removeEventListener('focus', asked)
  asked = null
}

/** What a reason the backend gave means, as a string key. */
export function errorKey(reason) {
  return (
    {
      not_configured: 'spotify.errorNotConfigured',
      not_allowed: 'spotify.errorNotAllowed',
      expired: 'spotify.errorExpired',
      denied: 'spotify.errorDenied',
      unreachable: 'spotify.errorUnreachable',
    }[reason] || 'spotify.errorFailed'
  )
}

/** Why a request failed, from its answer. */
export function reasonOf(err) {
  const detail = err && err.response && err.response.data && err.response.data.detail
  if (typeof detail === 'string') return detail
  return err && err.response ? 'failed' : 'unreachable'
}

export async function connectSpotify() {
  try {
    const { data } = await API.spotifyConnect()
    await desktop.openExternal(data.url)
    await refreshSpotify()
    watchSignIn()
    return true
  } catch (err) {
    toast(t(errorKey(reasonOf(err))), { tone: 'error', timeout: 9000 })
    return false
  }
}

export async function disconnectSpotify() {
  stopWatching()
  try {
    status.value = { ...EMPTY, ...(await API.spotifyDisconnect()).data }
    changed()
    toast(t('spotify.disconnectedToast'), { icon: 'ph:spotify-logo' })
  } catch {
    toast(t('spotify.errorFailed'), { tone: 'error' })
  }
}

/** Use one's own Spotify app (an empty value goes back to Dannify's). */
export async function setSpotifyApp(clientId) {
  const { data } = await API.spotifySetApp(clientId)
  status.value = { ...EMPTY, ...data }
  changed()
  return status.value
}

/** Play a Spotify list now: its songs play through YouTube Music. */
export function playSpotify(rows, index = 0) {
  if (rows && rows.length) playRows(rows, index)
}

/**
 * Copy a Spotify list into a new Dannify playlist. Each song is matched on
 * YouTube Music, in the background; this follows it to the end and says
 * what came of it. Resolves to the new playlist's id, or ''.
 */
export async function importSpotify(kind, id = '', name = '', onProgress = null) {
  let job
  try {
    job = (await API.spotifyImport(kind, id, name)).data.job
  } catch (err) {
    toast(t(errorKey(reasonOf(err))), { tone: 'error' })
    return ''
  }
  for (;;) {
    await new Promise((r) => setTimeout(r, 700))
    let now
    try {
      now = (await API.spotifyImportStatus(job)).data
    } catch {
      continue
    }
    if (onProgress) onProgress(now)
    if (!now.finished) continue
    if (now.playlist) {
      // The new playlist shows in the sidebar at once.
      await usePlaylists().load()
      toast(
        now.matched < now.total
          ? t('spotify.importedSome', { name: now.name, matched: now.matched, total: now.total })
          : t('spotify.imported', { name: now.name, count: now.matched }),
        { icon: 'ph:playlist', tone: 'success', timeout: 7000 }
      )
      return now.playlist
    }
    toast(t(now.error === 'nothing_matched' ? 'spotify.importNothing' : 'spotify.errorFailed'), { tone: 'error' })
    return ''
  }
}

// The person's Spotify playlists, shared by the sidebar, Home and Your
// Spotify: asked once, and again when the sign-in changes.
export const spotifyPlaylists = shallowRef([])
let playlistsAsked = null
export function loadSpotifyPlaylists(force = false) {
  if (!status.value.connected) {
    spotifyPlaylists.value = []
    return Promise.resolve([])
  }
  if (playlistsAsked && !force) return playlistsAsked
  playlistsAsked = API.spotifyPlaylists()
    .then((res) => (spotifyPlaylists.value = res.data.playlists || []))
    .catch(() => spotifyPlaylists.value)
    .finally(() => {
      setTimeout(() => (playlistsAsked = null), 60 * 1000)
    })
  return playlistsAsked
}
if (typeof window !== 'undefined') {
  window.addEventListener('dannify:spotify-changed', () => loadSpotifyPlaylists(true))
}

export function useSpotify() {
  return {
    status,
    connected: computed(() => !!status.value.connected),
    configured: computed(() => !!status.value.configured),
    user: computed(() => status.value.user || {}),
    refresh: refreshSpotify,
    connect: connectSpotify,
    disconnect: disconnectSpotify,
    setApp: setSpotifyApp,
  }
}

// Asked once the window is up: whether there is a Spotify to show.
if (typeof window !== 'undefined') setTimeout(() => refreshSpotify().then(() => loadSpotifyPlaylists()), 2500)
