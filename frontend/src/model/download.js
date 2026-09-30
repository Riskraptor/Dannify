import { ref, computed } from 'vue'

import API from '/src/model/api'
import { toast } from '/src/model/toast'
import { t } from '/src/i18n'
import { useLibraryIndex } from '/src/model/libraryIndex'

const STATUS = {
  QUEUED: 'In Queue',
  DOWNLOADING: 'Downloading...',
  DOWNLOADED: 'Done',
  ERROR: 'Error',
}

const downloadQueue = ref([])

// Songs taken off the list a moment ago. A progress message the server had
// already sent for one used to arrive after the removal and put the row
// straight back, stuck on "Downloading" for ever, since the server had
// stopped it. Asking for the song again clears it.
const removedIds = new Map()
const REMOVED_FOR = 60000

function wasRemoved(song) {
  const id = song && song.song_id
  if (id === undefined) return false
  const at = removedIds.get(id)
  if (at === undefined) return false
  if (Date.now() - at > REMOVED_FOR) {
    removedIds.delete(id)
    return false
  }
  return true
}

class DownloadItem {
  constructor(song) {
    this.song = song
    this.web_status = STATUS.QUEUED
    this.progress = 0
    this.message = ''
    this.web_download_url = null
    this.filename = null
  }
  setDownloading() {
    this.web_status = STATUS.DOWNLOADING
  }
  setDownloaded() {
    this.web_status = STATUS.DOWNLOADED
    // When it finished. Once the library has been read after this, the
    // library is the authority on whether the song is still there.
    this.completedAt = Date.now()
  }
  setError() {
    this.web_status = STATUS.ERROR
  }
  setWebURL(URL) {
    this.web_download_url = URL
  }
  setFilename(name) {
    this.filename = name
  }
  isQueued() {
    return this.song.song_id !== undefined ? true : false
    // return this.web_status === STATUS.QUEUED
  }
  isDownloading() {
    return this.web_status === STATUS.DOWNLOADING
  }
  isDownloaded() {
    return this.web_status === STATUS.DOWNLOADED
  }
  isErrored() {
    return this.web_status === STATUS.ERROR
  }
  isPending() {
    return this.web_status === STATUS.QUEUED || this.web_status === STATUS.DOWNLOADING
  }
  wsUpdate(message) {
    this.progress = message.progress
    this.message = message.message
  }
}

export function useProgressTracker() {
  function _findIndex(song) {
    return downloadQueue.value.findIndex(
      (downloadItem) => downloadItem.song.song_id === song.song_id
    )
  }
  function appendSong(song) {
    removedIds.delete(song && song.song_id)
    let downloadItem = new DownloadItem(song)
    downloadQueue.value.push(downloadItem)
  }
  function removeSong(song) {
    removedIds.set(song.song_id, Date.now())
    downloadQueue.value = downloadQueue.value.filter(
      (downloadItem) => downloadItem.song.song_id !== song.song_id
    )
  }

  function getBySong(song) {
    const idx = _findIndex(song)
    if (idx === -1) return null
    return downloadQueue.value[_findIndex(song)]
  }

  return {
    appendSong,
    removeSong,
    getBySong,
    downloadQueue,
  }
}

const progressTracker = useProgressTracker()

API.ws_onmessage((event) => {
  let data
  try {
    data = JSON.parse(event.data)
  } catch {
    return
  }
  // The app updater streams its installer download over the same socket.
  if (data && data.type === 'update_progress') {
    window.dispatchEvent(
      new CustomEvent('dannify:update-progress', { detail: data })
    )
    return
  }
  // Tracks being repaired. Their own message, so they never turn up in the
  // download list as if somebody had asked for new music.
  if (data && data.type === 'repair') {
    window.dispatchEvent(new CustomEvent('dannify:repair', { detail: data }))
    return
  }
  // Saved songs having their details fetched again (see details.js).
  if (data && data.type === 'details') {
    window.dispatchEvent(new CustomEvent('dannify:details', { detail: data }))
    return
  }
  // A .dnf was double-clicked in Explorer. The shell worked out how to
  // reach it and sent the finished track down here, so there is nothing to
  // look up: play it.
  if (data && data.type === 'play_file') {
    window.dispatchEvent(
      new CustomEvent('dannify:play-file', { detail: data.track })
    )
    return
  }
  // Server-side cache invalidation: a download finished, or the user
  // picked a new folder. Tell the in-memory library map to refresh so
  // search/explorer instantly mark this song as "downloaded" and the
  // player plays the local file from the next click onward.
  if (data && data.type === 'library_changed') {
    try {
      useLibraryIndex().invalidate()
    } catch {
      // ignore
    }
    window.dispatchEvent(new CustomEvent('dannify:library-changed'))
    // Back after the connection dropped: whatever finished or failed in the
    // gap was said to nobody, and its row would sit at its last percentage.
    if (data.reconnected) _hydrateFromServer(true)
    if (!data.song) return
  }
  if (!data || !data.song) return
  let item = progressTracker.getBySong(data.song)
  if (!item) {
    if (wasRemoved(data.song)) return
    progressTracker.appendSong(data.song)
    item = progressTracker.getBySong(data.song)
    if (!item) return
  }
  if (data.status === 'done') {
    item.progress = 100
    if (data.filename) {
      item.setWebURL(API.downloadFileURL(data.filename))
      item.setFilename(data.filename)
    }
    item.setDownloaded()
  } else if (data.status === 'error') {
    item.wsUpdate(data)
    item.setError()
  } else if (data.status === 'queued') {
    item.message = data.message || ''
  } else {
    item.wsUpdate(data)
    if (!item.isDownloading()) item.setDownloading()
  }
})
API.ws_onerror((event) => {
  console.log('websocket error:', event)
})

// Read the server's list of jobs. With `update`, rows already shown are
// brought up to date too: that is the catch-up after a dropped connection.
async function _hydrateFromServer(update = false) {
  try {
    const res = await API.getQueue()
    const jobs = res.data || []
    if (update) {
      // Waiting or downloading here, and gone from the server (it restarted
      // while the connection was down): nothing is coming for it. Said so,
      // with the retry every failed download has, rather than left on its
      // last percentage, which also stopped it being asked for again.
      const live = new Set(jobs.filter((j) => j && j.song).map((j) => j.song.song_id))
      for (const item of downloadQueue.value) {
        if (item.isPending() && !live.has(item.song.song_id)) {
          item.message = ''
          item.setError()
        }
      }
    }
    for (const job of jobs) {
      if (!job || !job.song) continue
      const shown = downloadQueue.value.find((i) => i.song.song_id === job.song.song_id)
      if (shown) {
        if (update) _applyJob(shown, job)
        continue
      }
      if (wasRemoved(job.song)) continue
      const item = new DownloadItem(job.song)
      if (job.status === 'done') {
        item.setDownloaded()
        item.completedAt = 0 // finished in an earlier session
        if (job.filename) {
          item.setWebURL(API.downloadFileURL(job.filename))
          item.setFilename(job.filename)
        }
        item.progress = 100
      } else if (job.status === 'error') {
        item.setError()
        item.message = job.message || ''
      } else if (job.status === 'downloading') {
        item.setDownloading()
        item.progress = job.progress || 0
        item.message = job.message || ''
      } else {
        item.message = job.message || ''
      }
      downloadQueue.value.push(item)
    }
  } catch (e) {
    console.log('Failed to load queue from server:', e)
  }
}

function _applyJob(item, job) {
  if (job.status === 'done') {
    item.progress = 100
    if (job.filename) {
      item.setWebURL(API.downloadFileURL(job.filename))
      item.setFilename(job.filename)
    }
    if (!item.isDownloaded()) item.setDownloaded()
  } else if (job.status === 'error') {
    item.message = job.message || ''
    item.setError()
  } else if (job.status === 'downloading') {
    item.progress = job.progress || 0
    item.message = job.message || ''
    if (!item.isDownloading()) item.setDownloading()
  }
}

_hydrateFromServer()

export function useDownloadManager() {
  const loading = ref(false)
  function fromURL(url) {
    const isPlaylistURL = (url || '').includes('://open.spotify.com/playlist/')
    loading.value = true
    return API.open(url)
      .then((res) => {
        console.log('Received Response:', res)
        if (res.status !== 200) {
          console.log('Error:', res)
          return
        }
        const songs = res.data
        if (Array.isArray(songs)) {
          for (const song of songs) {
            if (!progressTracker.getBySong(song)) {
              progressTracker.appendSong(song)
            }
          }
          return API.downloadBatch({
            songs,
            playlist_url: isPlaylistURL ? url : '',
          }).catch((err) => {
            console.log('Batch submit failed:', err.message)
            markFailed(songs)
          })
        } else {
          console.log('Opened Song:', songs)
          queue(songs)
        }
      })
      .catch((err) => {
        console.log('Other Error:', err.message)
      })
      .finally(() => {
        loading.value = false
      })
  }

  // The batch never reached the backend. Those songs used to sit on "In
  // Queue" for ever, waiting for news of a job nobody had started; marked
  // failed, each gets the retry button every failed download has.
  function markFailed(songs) {
    for (const song of songs) {
      const item = progressTracker.getBySong(song)
      if (item && !item.isDownloaded()) {
        item.message = ''
        item.setError()
      }
    }
  }

  // Download an explicit list of songs (e.g. a user-picked subset of a
  // playlist/album from a collection page).
  function downloadSongs(songs, playlistUrl = '') {
    const list = Array.isArray(songs) ? songs : [songs]
    if (list.length === 0) return Promise.resolve()
    for (const song of list) {
      if (!progressTracker.getBySong(song)) {
        progressTracker.appendSong(song)
      }
    }
    const isPlaylistURL = (playlistUrl || '').includes(
      '://open.spotify.com/playlist/'
    )
    return API.downloadBatch({
      songs: list,
      playlist_url: isPlaylistURL ? playlistUrl : '',
    }).catch((err) => {
      console.log('Batch submit failed:', err.message)
      markFailed(list)
    })
  }

  function download(song) {
    console.log('Downloading', song)
    progressTracker.getBySong(song).setDownloading()
    return API.download(song)
      .then((res) => {
        console.log('Received Response:', res)
        if (res.status === 200) {
          let filename = res.data
          console.log('Download Complete:', filename)
          progressTracker
            .getBySong(song)
            .setWebURL(API.downloadFileURL(filename))
          progressTracker.getBySong(song).setFilename(filename)
          progressTracker.getBySong(song).setDownloaded()
          return { song, filename }
        } else {
          console.log('Error:', res)
          progressTracker.getBySong(song).setError()
          return { song, filename: null }
        }
      })
      .catch((err) => {
        console.log('Other Error:', err.message)
        progressTracker.getBySong(song).setError()
        return { song, filename: null }
      })
  }

  function queue(song, beginDownload = true) {
    progressTracker.appendSong(song)
    if (beginDownload) return download(song)
    return Promise.resolve({ song, filename: null })
  }

  function retryWithAudio(song, youtubeVideoId) {
    const overriddenSong = { ...song, youtube_id: youtubeVideoId }
    const item = progressTracker.getBySong(song)
    if (item) {
      item.song.youtube_id = youtubeVideoId
      item.setDownloading()
      item.progress = 0
      item.message = ''
    }
    return API.download(overriddenSong)
      .then((res) => {
        const it = progressTracker.getBySong(overriddenSong)
        if (res.status === 200) {
          const filename = res.data
          if (it) {
            it.setWebURL(API.downloadFileURL(filename))
            it.setFilename(filename)
            it.setDownloaded()
          }
          return { song: overriddenSong, filename }
        }
        if (it) it.setError()
        return { song: overriddenSong, filename: null }
      })
      .catch((err) => {
        console.error('retryWithAudio error:', err.message)
        const it = progressTracker.getBySong(overriddenSong)
        if (it) it.setError()
        return { song: overriddenSong, filename: null }
      })
  }

  function remove(song) {
    const songId = String(song.song_id || song.url || '')
    progressTracker.removeSong(song)
    if (songId) {
      API.removeQueueItem(songId).catch(() => {})
    }
  }

  async function clearAll() {
    try {
      await API.clearQueue()
      const now = Date.now()
      for (const item of downloadQueue.value) removedIds.set(item.song.song_id, now)
      downloadQueue.value = []
      return true
    } catch {
      // The list stays as it was, and says so, rather than a click that
      // silently did nothing.
      toast(t('queue.clearFailed'), { tone: 'error' })
      return false
    }
  }

  return {
    fromURL,
    downloadSongs,
    download,
    queue,
    retryWithAudio,
    remove,
    clearAll,
    loading,
  }
}
