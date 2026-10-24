// Every call the window makes to Dannify's own server, in one place.
import { ref } from 'vue'
import config from '/src/config.js'
import { createClient } from '/src/model/http'
import { pageIsStale } from '/src/model/staleness'

const API = createClient({
  baseURL: `${config.PROTOCOL}//${config.BACKEND}:${config.PORT}${config.BASEURL}`,
})

// Names this window to the live channel. randomUUID is only there on a
// secure page, and a phone on the LAN opens the app over plain http, so the
// same thing is made by hand from random bytes when it is missing.
function makeSessionId() {
  const c = globalThis.crypto
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  const b = c.getRandomValues(new Uint8Array(16))
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}
const sessionID = makeSessionId()

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

// A pasted Spotify link as a page of songs, and those songs on YouTube Music.
function spotifyLink(url) {
  return API.get('/api/links/spotify', { params: { url }, timeout: 60000 })
}
function matchLinkSongs(tracks) {
  return API.post('/api/links/match', { tracks }, { timeout: 90000 })
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

// A saved song's chosen version, written beside it, so it is the one shown
// offline and after a restart. `hints` are what the player knows of the song.
function keepLyricVersion(file, version, hints = {}) {
  return API.post('/api/lyrics/keep', { file, version, ...hints })
}

function saveLyricsOffset(title, artist, offset, version, pick) {
  const body = { title, artist }
  if (offset !== undefined && offset !== null) body.offset = offset
  if (version !== undefined && version !== null) body.version = version
  if (pick !== undefined && pick !== null) body.pick = pick
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

// The albums there are saved songs from, and one of them with its songs.
function getAlbums() {
  return API.get('/api/albums')
}
function getAlbum(artist, name) {
  return API.get('/api/albums/detail', { params: { artist, name } })
}

// Something went wrong in the window: into the app's log (see problems.js).
function reportClientError(payload) {
  return API.post('/api/client-error', payload)
}
// Problem reports, sent from inside the app (see report.py).
function getReportStatus() {
  return API.get('/api/support/report/status')
}
function getReportPreview() {
  return API.get('/api/support/report/preview')
}
function sendReport(payload) {
  return API.post('/api/support/report/send', payload, { timeout: 90000 })
}
function holdReport(email) {
  return API.post('/api/support/report/hold', { email })
}
function heldReports() {
  return API.get('/api/support/report/held')
}
function reportDone(id) {
  return API.post('/api/support/report/done', { id })
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

// What has been listened to: History and Stats (see listens.py).
function recordListen(payload) {
  return API.post('/api/listens', payload)
}
function getListenStats(days = 0, top = 50) {
  return API.get('/api/listens/stats', { params: { days, top } })
}
// Mixes made from the listening, and a year of it (Backend listens.py).
function getMixes() {
  return API.get('/api/listens/mixes')
}
function getRecap(year = 0) {
  return API.get('/api/listens/recap', { params: { year } })
}
// Today, this week, this month or a year, or one before (ago: yesterday, last
// week, last month), told as a story (Backend listens.story). Weeks start on
// weekStart, Monday 0 to Sunday 6.
function getStory(period = 'year', year = 0, ago = 0, weekStart = 0) {
  return API.get('/api/listens/story', { params: { period, year, ago, week_start: weekStart } })
}
// All four at a glance, for Home's "Your music lately".
function getGlance(weekStart = 0) {
  return API.get('/api/listens/glance', { params: { week_start: weekStart } })
}
// A picture the window drew (Your Soundtrack's card), saved in Pictures.
function saveShareImage(name, data) {
  return API.post('/api/share/image', { name, data })
}
function getListenHistory(limit = 100, before = 0) {
  return API.get('/api/listens/history', { params: { limit, before } })
}
function forgetListen(at, key) {
  return API.delete('/api/listens/item', { params: { at, key } })
}
function clearListens() {
  return API.delete('/api/listens')
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
// The account on YouTube Music, beyond likes.
function getFollowing() {
  return API.get('/api/account/following')
}
function setFollowing(channelId, follow) {
  return API.post('/api/account/follow', { channel_id: channelId, follow })
}
function getHistory() {
  return API.get('/api/account/history')
}
function addHistory(videoId) {
  return API.post('/api/account/history/add', { video_id: videoId })
}
function addToYouTubePlaylist(playlistId, videoIds) {
  return API.post('/api/account/playlist/add', { playlist_id: playlistId, video_ids: videoIds })
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
// YouTube Music's history brought into Dannify's (Backend/dannify/ytm_history.py).
function syncYouTubeHistory() {
  return API.post('/api/listens/youtube', null, { timeout: 60000 })
}
function youTubeHistoryStatus() {
  return API.get('/api/listens/youtube')
}
// The country the computer is set to (Windows, macOS or Linux), for special
// days (model/occasions.js).
function region() {
  return API.get('/api/region')
}
function exploreSearch(q, limit = 20) {
  return API.get('/api/explore/search', { params: { q, limit } })
}
// Ways to finish what is being typed in the search box. Quick to give up:
// a suggestion that arrives after the search itself is no use to anyone.
function searchSuggest(q, signal) {
  return API.get('/api/explore/suggest', { params: { q }, timeout: 4000, signal })
}
// Moods and genres (Search before anything is typed).
function getMoods() {
  return API.get('/api/explore/moods')
}
// YouTube Music's charts where the listener is, and its new releases.
function exploreCharts(country) {
  return API.get('/api/explore/charts', { params: { country } })
}
function exploreNew() {
  return API.get('/api/explore/new')
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
// ListenBrainz, for whoever connects it (Backend/dannify/scrobble.py).
function listenBrainzStatus() {
  return API.get('/api/listenbrainz')
}
function connectListenBrainz(token) {
  return API.post('/api/listenbrainz/connect', { token })
}
function disconnectListenBrainz() {
  return API.post('/api/listenbrainz/disconnect')
}

// Saved music that will not open at all: look again ('retry'), or let new
// songs be saved beside the ones that will not ('fresh').
function recoverStorage(action) {
  return API.post('/api/storage/recover', { action })
}
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
  recoverStorage,
  listenBrainzStatus,
  connectListenBrainz,
  disconnectListenBrainz,
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
  keepLyricVersion,
  publishLyrics,
  getLibrary,
  searchLibrary,
  getArtists,
  getArtist,
  getAlbums,
  getAlbum,
  reportClientError,
  getReportStatus,
  getReportPreview,
  spotifyLink,
  matchLinkSongs,
  sendReport,
  holdReport,
  heldReports,
  reportDone,
  getPlaylists,
  getPlaylist,
  createPlaylist,
  updatePlaylist,
  addToPlaylist,
  deletePlaylist,
  recordListen,
  getListenStats,
  getListenHistory,
  getMixes,
  getRecap,
  getStory,
  getGlance,
  saveShareImage,
  forgetListen,
  clearListens,
  getArtistLinks,
  getArtistOnline,
  getStorage,
  clearCaches,
  refreshDetails,
  refreshArtists,
  exploreSearch,
  region,
  syncYouTubeHistory,
  youTubeHistoryStatus,
  searchSuggest,
  exploreArtist,
  getMoods,
  getMoodPlaylists,
  exploreCharts,
  exploreNew,
  exploreAlbum,
  explorePlaylist,
  // account + personalization
  getAccount,
  signOutAccount,
  getHomeFeed,
  getLikedSongs,
  getLibraryPlaylists,
  rateSong,
  getFollowing,
  setFollowing,
  getHistory,
  addHistory,
  addToYouTubePlaylist,
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
