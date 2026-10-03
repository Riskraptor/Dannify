// small file used as placeholder/settings for API calls via axios to server-side
import axios from 'axios' // used to connect to server backend in ./server folder
import { ref } from 'vue'
import config from '/src/config.js'
import { pageIsStale } from '/src/model/staleness'

import { v4 as uuidv4 } from 'uuid'

console.log('using env:', process.env)
console.log('using config: ', config)

const API = axios.create({
  baseURL: `${config.PROTOCOL}//${config.BACKEND}:${config.PORT}${config.BASEURL}`,
})

const sessionID = uuidv4()
console.log('session ID: ', sessionID)

getVersion()

// The live channel: download progress, library changes, files opened from
// Explorer. It used to be opened once and never again, so a single drop
// (the PC sleeping, a network change) silently stopped all of that for the
// rest of the session. Now it comes back on its own, waiting a little longer
// after each failed attempt, and tells the library to catch up on whatever
// it missed while it was away.
const WS_URL = `${config.WS_PROTOCOL}//${config.BACKEND}${
  config.PORT !== '' ? ':' + config.PORT : ''
}${config.BASEURL}/api/ws?client_id=${sessionID}`
let wsConnection = null
let wsOnMessage = null
let wsOnError = null
let wsAttempts = 0
let wsOpenedOnce = false
let wsClosing = false

if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    wsClosing = true
  })
}

function connectWs() {
  let ws
  try {
    ws = new WebSocket(WS_URL)
  } catch {
    scheduleReconnect()
    return
  }
  wsConnection = ws
  ws.onopen = () => {
    wsAttempts = 0
    if (wsOpenedOnce && wsOnMessage) {
      // Anything that changed while the channel was down.
      wsOnMessage({ data: JSON.stringify({ type: 'library_changed', reconnected: true }) })
    }
    wsOpenedOnce = true
  }
  ws.onmessage = (event) => wsOnMessage && wsOnMessage(event)
  ws.onerror = (event) => wsOnError && wsOnError(event)
  ws.onclose = () => {
    if (wsConnection === ws) scheduleReconnect()
  }
}

function scheduleReconnect() {
  if (wsClosing) return
  const wait = Math.min(15000, 1000 * 2 ** Math.min(wsAttempts, 4))
  wsAttempts += 1
  setTimeout(connectWs, wait)
}

connectWs()

function readStored(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStored(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Blocked storage: the value just does not outlive the session.
  }
}

// The version, live. It used to be read out of storage once when Settings was
// set up, so a check that failed at startup wrote "0.0.0" there and About
// went on showing it for the rest of the session, however many times the
// request would have succeeded since.
export const appVersion = ref(readStored('version') || '')

function getVersion(attempt = 0) {
  API.get('/api/version')
    .then((res) => {
      const prevItem = readStored('version')
      writeStored('version', res.data)
      appVersion.value = res.data
      if (pageIsStale(prevItem, res.data)) location.reload()
    })
    .catch(() => {
      // Try again rather than settling on a number that is not true. The
      // server is usually just not listening yet.
      if (attempt < 5) {
        setTimeout(() => getVersion(attempt + 1), 1000 * (attempt + 1))
        return
      }
      writeStored('version', '0.0.0')
      appVersion.value = ''
    })
}

function search(query) {
  return API.get('/api/songs/search', { params: { query } })
}

function download(songURL) {
  const url = typeof songURL === 'string' ? songURL : songURL.url
  const hints = typeof songURL === 'string' ? undefined : songURL
  return API.post('/api/download/url', hints, {
    params: { url, client_id: sessionID },
  })
}

function downloadBatch(payload) {
  return API.post('/api/download/batch', payload)
}

function check_for_update() {
  return API.get('/api/check_update')
}

// --- Dannify enhanced: preview, streaming, lyrics, library ---

function preview(url) {
  return API.get('/api/preview', { params: { url } })
}

function resolveStream(url) {
  return API.get('/api/resolve', { params: { url } })
}

function streamURL(videoId) {
  return `${config.BASEURL}/api/stream?video_id=${encodeURIComponent(videoId)}`
}

function getStreamInfo(videoId, prefetch = 0) {
  return API.get('/api/stream/info', {
    params: { video_id: videoId, prefetch },
  })
}

function prefetchStream(videoId) {
  return API.get('/api/stream/prefetch', { params: { video_id: videoId } })
}

// Ask the backend whether *song* is already on disk; returns the relative
// file path on hit, '' otherwise. Used so that playing a search result for
// a song you've already downloaded streams the local file instead of going
// back through ffmpeg/youtube. Pre-compute is encouraged (call once per
// list of results) so user clicks are zero-latency.
function locateLocal({ video_id = '', title = '', artist = '' }) {
  return API.get('/api/library/locate', {
    params: { video_id, title, artist },
  })
}

function pickFolder() {
  return API.post('/api/settings/pick-folder')
}

function streamURLFromLink(url) {
  return `${config.BASEURL}/api/stream?url=${encodeURIComponent(url)}`
}

function getLyrics(params) {
  // params: { file } | { url } | { title, artist, album, duration }
  return API.get('/api/lyrics', { params })
}

function getLyricVersions(params) {
  return API.get('/api/lyrics/versions', { params })
}

function saveLyricsOffset(title, artist, offset, version) {
  const body = { title, artist }
  if (offset !== undefined && offset !== null) body.offset = offset
  if (version !== undefined && version !== null) body.version = version
  return API.post('/api/lyrics/offset', body)
}

function publishLyrics(payload) {
  // payload: { track, artist, album, duration, plain?, synced? }
  // Resolves to { published: bool, error?: str }. Note the call can
  // take 15-30 s server-side while it clears the publish challenge,
  // so set a generous timeout.
  return API.post('/api/lyrics/publish', payload, { timeout: 120_000 })
}

function getLibrary() {
  return API.get('/api/library')
}

function searchLibrary(q, limit = 50) {
  return API.get('/api/library/search', { params: { q, limit } })
}

function getArtists() {
  return API.get('/api/artists')
}

function getArtist(name) {
  return API.get(`/api/artists/${encodeURIComponent(name)}`)
}

// Something went wrong in the window: into the app's log (see problems.js).
function reportClientError(payload) {
  return API.post('/api/client-error', payload)
}
// Problem reports, sent from inside the app (see report.py).
function getReportStatus() {
  return API.get('/api/support/report/status')
}
function sendReport(payload) {
  return API.post('/api/support/report/send', payload, { timeout: 90000 })
}

// Playlists made in the app (kept on this PC).
function getPlaylists() {
  return API.get('/api/playlists')
}
function getPlaylist(id) {
  return API.get(`/api/playlists/${encodeURIComponent(id)}`)
}
function createPlaylist(name, tracks = []) {
  return API.post('/api/playlists', { name, tracks })
}
function updatePlaylist(id, changes) {
  return API.patch(`/api/playlists/${encodeURIComponent(id)}`, changes)
}
function addToPlaylist(id, tracks, position = null) {
  return API.post(`/api/playlists/${encodeURIComponent(id)}/tracks`, { tracks, position })
}
function deletePlaylist(id) {
  return API.delete(`/api/playlists/${encodeURIComponent(id)}`)
}

// Who the saved artists are online (page id and picture), and one artist's
// whole online page, for the rest of their page in the library.
// What the library takes up, and the caches that can be let go.
function getStorage() {
  return API.get('/api/storage')
}
function clearCaches() {
  return API.post('/api/storage/clear-caches')
}

// Fetch saved songs' details again, around the same audio (see details.py).
function refreshDetails(files) {
  return API.post('/api/library/details', { files })
}
// Look artists up again: their picture and their online page.
function refreshArtists(names) {
  return API.post('/api/artists-online/refresh', { names })
}

function getArtistLinks() {
  return API.get('/api/artists-online/links')
}
function getArtistOnline(name) {
  return API.get('/api/artists-online/page', { params: { name } })
}

// --- Account (YouTube Music sign-in), personalized feeds, likes ---
function getAccount() {
  return API.get('/api/account')
}
function signOutAccount() {
  return API.post('/api/account/signout')
}
function getHomeFeed(limit = 6) {
  return API.get('/api/home', { params: { limit } })
}
function getLikedSongs(limit = 250) {
  return API.get('/api/liked', { params: { limit } })
}
function getLibraryPlaylists(limit = 50) {
  return API.get('/api/library/playlists', { params: { limit } })
}
function rateSong(videoId, liked) {
  return API.post('/api/rate', { video_id: videoId, liked })
}
function getRadio(videoId, limit = 30) {
  return API.get('/api/radio', { params: { video_id: videoId, limit } })
}

// --- Support the app + in-app updates ---
function getSupportConfig() {
  return API.get('/api/support')
}
// Whether YouTube Music can be reached, asked fresh (never cached).
function netCheck() {
  return API.get('/api/net', { timeout: 8000 })
}
function checkForUpdate(force = false) {
  return API.get('/api/update/check', { params: { force: force ? 1 : 0 } })
}
function downloadUpdate(url) {
  return API.post('/api/update/download', url ? { url } : {}, { timeout: 0 })
}
function updateStatus() {
  return API.get('/api/update/status')
}
function acknowledgeUpdate() {
  return API.post('/api/update/acknowledge')
}
function discardUpdate() {
  return API.post('/api/update/discard')
}

// --- Online explorer (Spotify-style discovery) ---
function exploreSearch(q, limit = 20) {
  return API.get('/api/explore/search', { params: { q, limit } })
}
// Moods and genres (Search before anything is typed).
function getMoods() {
  return API.get('/api/explore/moods')
}
function getMoodPlaylists(params) {
  return API.get('/api/explore/moods/playlists', { params: { params } })
}
function exploreArtist(id) {
  return API.get('/api/explore/artist', { params: { id } })
}
function exploreAlbum(id) {
  return API.get('/api/explore/album', { params: { id } })
}
function explorePlaylist(id, limit = 200) {
  return API.get('/api/explore/playlist', { params: { id, limit } })
}

function encodePath(fileName) {
  // Encode each path segment individually so '/' separators survive
  // playlist downloads land under '<playlist>/<song>.mp3' and we need
  // the URL to hit '/downloads/<playlist>/<song>.mp3' literally.
  return String(fileName || '')
    .split('/')
    .map(encodeURIComponent)
    .join('/')
}

function downloadFileURL(fileName) {
  return `/downloads/${encodePath(fileName)}`
}

// *version* changes whenever the file does (its date). A repaired song is a
// new file at the same path, and without it the old picture, or the failure
// to get one, was what the window went on showing.
function coverFileURL(fileName, version) {
  const v = version ? `&v=${encodeURIComponent(version)}` : ''
  return `/cover?file=${encodeURIComponent(fileName)}${v}`
}

function health() {
  return API.get('/api/health')
}

// Saved tracks that will not play, downloaded again in place.
function repairStatus() {
  return API.get('/api/library/repair')
}
function repairTracks(payload) {
  return API.post('/api/library/repair', payload)
}
function repairStop() {
  return API.post('/api/library/repair/stop')
}

function listDownloads() {
  return API.get('/list')
}

function deleteDownload(file) {
  return API.delete('/delete', { params: { file } })
}

function getQueue() {
  return API.get('/api/queue')
}

function removeQueueItem(songId) {
  return API.delete('/api/queue/item', { params: { song_id: songId } })
}

function clearQueue() {
  return API.delete('/api/queue')
}

function getSettings() {
  return API.get('/api/settings', { params: { client_id: sessionID } })
}
function setSettings(settings) {
  return API.post('/api/settings/update', settings, {
    params: { client_id: sessionID },
  })
}

function ws_onmessage(fn) {
  wsOnMessage = fn
  return fn
}
function ws_onerror(fn) {
  wsOnError = fn
  return fn
}

export default {
  search,
  download,
  downloadBatch,
  health,
  repairStatus,
  repairTracks,
  repairStop,
  downloadFileURL,
  coverFileURL,
  listDownloads,
  deleteDownload,
  getQueue,
  removeQueueItem,
  clearQueue,
  getSettings,
  setSettings,
  check_for_update,
  ws_onmessage,
  ws_onerror,
  getVersion,
  // Dannify enhanced
  preview,
  resolveStream,
  streamURL,
  getStreamInfo,
  prefetchStream,
  locateLocal,
  pickFolder,
  streamURLFromLink,
  getLyrics,
  getLyricVersions,
  saveLyricsOffset,
  publishLyrics,
  getLibrary,
  searchLibrary,
  getArtists,
  getArtist,
  reportClientError,
  getReportStatus,
  sendReport,
  getPlaylists,
  getPlaylist,
  createPlaylist,
  updatePlaylist,
  addToPlaylist,
  deletePlaylist,
  getArtistLinks,
  getArtistOnline,
  getStorage,
  clearCaches,
  refreshDetails,
  refreshArtists,
  exploreSearch,
  exploreArtist,
  getMoods,
  getMoodPlaylists,
  exploreAlbum,
  explorePlaylist,
  // account + personalization
  getAccount,
  signOutAccount,
  getHomeFeed,
  getLikedSongs,
  getLibraryPlaylists,
  rateSong,
  getRadio,
  // support + updates
  getSupportConfig,
  checkForUpdate,
  netCheck,
  downloadUpdate,
  updateStatus,
  acknowledgeUpdate,
  discardUpdate,
}
