// small file used as placeholder/settings for API calls via axios to server-side
import axios from 'axios' // used to connect to server backend in ./server folder
import { ref } from 'vue'
import config from '/src/config.js'

import { v4 as uuidv4 } from 'uuid'

console.log('using env:', process.env)
console.log('using config: ', config)

const API = axios.create({
  baseURL: `${config.PROTOCOL}//${config.BACKEND}:${config.PORT}${config.BASEURL}`,
})

const sessionID = uuidv4()
console.log('session ID: ', sessionID)

getVersion()

const wsConnection = new WebSocket(
  `${config.WS_PROTOCOL}//${config.BACKEND}${
    config.PORT !== '' ? ':' + config.PORT : ''
  }${config.BASEURL}/api/ws?client_id=${sessionID}`
)

wsConnection.onopen = (event) => {
  console.log('websocket connection opened', event)
}

// The version, live. It used to be read out of storage once when Settings was
// set up, so a check that failed at startup wrote "0.0.0" there and About
// went on showing it for the rest of the session, however many times the
// request would have succeeded since.
export const appVersion = ref(localStorage.getItem('version') || '')

function getVersion(attempt = 0) {
  API.get('/api/version')
    .then((res) => {
      const prevItem = localStorage.getItem('version')
      localStorage.setItem('version', res.data)
      appVersion.value = res.data
      // Reload only after an upgrade (stale cached assets). A first run has
      // nothing stale: reloading would just flash the window.
      if (prevItem && prevItem !== '0.0.0' && prevItem != res.data) {
        location.reload()
      }
    })
    .catch(() => {
      // Try again rather than settling on a number that is not true. The
      // server is usually just not listening yet.
      if (attempt < 5) {
        setTimeout(() => getVersion(attempt + 1), 1000 * (attempt + 1))
        return
      }
      localStorage.setItem('version', '0.0.0')
      appVersion.value = ''
    })
}

function search(query) {
  return API.get('/api/songs/search', { params: { query } })
}

function open(songURL) {
  return API.get('/api/song/url', { params: { url: songURL } })
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
function checkForUpdate(force = false) {
  return API.get('/api/update/check', { params: { force: force ? 1 : 0 } })
}
function downloadUpdate(url) {
  return API.post('/api/update/download', url ? { url } : {}, { timeout: 0 })
}

// --- Online explorer (Spotify-style discovery) ---
function exploreSearch(q, limit = 20) {
  return API.get('/api/explore/search', { params: { q, limit } })
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

function writePlaylistM3u(payload) {
  return API.post('/api/playlist/m3u', payload)
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
  return (wsConnection.onmessage = fn)
}
function ws_onerror(fn) {
  return (wsConnection.onerror = fn)
}

export default {
  search,
  open,
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
  writePlaylistM3u,
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
  exploreSearch,
  exploreArtist,
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
  downloadUpdate,
}
