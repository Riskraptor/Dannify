import API from '/src/model/api'
import { toast } from '/src/model/toast'
import { t } from '/src/i18n'
import { toTrack, trackFromFile, trackFromSong } from '/src/model/player/makeTrack'
import {
  addToShuffleOrder,
  buildShuffleOrder,
  dropFromShuffleOrder,
  ensureShuffleOrder,
  nextIndex,
  shufflePosition,
  upcoming,
} from '/src/model/player/order'
import { repairAction } from '/src/model/player/recovery'
import { currentIndex, isPlaying, playlist, shuffle, shuffleOrder } from '/src/model/player/state'
import { pause, playAt } from '/src/model/player/transport'

// Editing the queue: replacing it, adding to it (next, or at the end),
// taking out, clearing what is to come and moving tracks about, without
// interrupting what plays.

export function setPlaylist(files, options = {}) {
  const tracks = (files || []).map((f) => {
    if (typeof f === 'string') return trackFromFile(f)
    if (f && (f.song_id || f.video_id) && !f.url) return trackFromSong(f)
    if (f && f.name && (f.artists || f.album_name) && !f.title) {
      return trackFromSong(f)
    }
    return f
  })
  playlist.value = tracks
  if (currentIndex.value >= tracks.length) currentIndex.value = -1
  let start = null
  if (typeof options.startIndex === 'number') {
    start = options.startIndex
  } else if (options.autoplay && tracks.length > 0 && currentIndex.value < 0) {
    start = 0
  }
  // The track it starts on leads the new shuffle.
  if (shuffle.value) buildShuffleOrder(start != null ? start : currentIndex.value)
  if (start != null) playAt(start)
}

// A saved track opened from outside the app: double-clicked in Explorer, or
// passed on the command line. The shell has already worked out how to reach
// it, so this is a finished track and there is nothing to look up.
window.addEventListener('dannify:play-file', (e) => {
  const track = e && e.detail
  if (!track) return
  if (track.error) {
    toast(t('player.fileCantPlay', { name: track.name || '' }), {
      tone: 'error',
      // Only a track in the library can be repaired: it is put back where it
      // was, and a file from anywhere else has no place in it to go back to.
      ...repairAction(track.file || ''),
    })
    return
  }
  if (!track.url) return
  setPlaylist([track], { startIndex: 0 })
})

// Queue a list of streamable songs (from preview/search) and start playing.
export function playStreamSongs(songs, startIndex = 0) {
  setPlaylist(songs.map(trackFromSong), { startIndex })
}

// Trigger a real download for a streamed track (so the user can keep it).
export function downloadTrack(track) {
  const song = (track && track._song) || null
  if (!song) return Promise.resolve()
  return API.download(song).catch(() => {})
}

// Insert tracks right after the current one ("Play next") or at the end of
// the queue ("Add to queue"). Accepts track objects, song dicts or file
// paths. Starts playback when nothing is loaded yet.
export function enqueue(items, { next: asNext = false } = {}) {
  const tracks = (Array.isArray(items) ? items : [items])
    .filter(Boolean)
    .map(toTrack)
  if (!tracks.length) return
  const before = playlist.value
  const afterCurrent = asNext && currentIndex.value >= 0
  const at = afterCurrent ? currentIndex.value + 1 : before.length
  if (shuffle.value) addToShuffleOrder(at, tracks.length, { next: afterCurrent })
  playlist.value = [...before.slice(0, at), ...tracks, ...before.slice(at)]
  if (currentIndex.value < 0) playAt(at)
}

export function enqueueNext(song) {
  enqueue([song], { next: true })
}

// Remove one entry from the queue without interrupting playback.
export function removeFromQueue(index) {
  if (index < 0 || index >= playlist.value.length) return
  if (index === currentIndex.value) {
    // Removing the playing track: whatever Next would have played takes its
    // place, in the play order, so under shuffle too. It used to be the next
    // row, always started, even on a paused player; and removing the last
    // track went back to the one before it and started that.
    let succ = nextIndex()
    if (succ === index) succ = -1 // a queue of one, under repeat all
    const wasPlaying = isPlaying.value
    const list = [...playlist.value]
    list.splice(index, 1)
    if (shuffle.value) dropFromShuffleOrder(index)
    playlist.value = list
    if (succ < 0) {
      // Nothing after it: the queue is over, as it would be at the end.
      currentIndex.value = -1
      pause()
      return
    }
    playAt(succ > index ? succ - 1 : succ, { autoplay: wasPlaying })
    return
  }
  const list = [...playlist.value]
  list.splice(index, 1)
  if (shuffle.value) dropFromShuffleOrder(index)
  playlist.value = list
  if (index < currentIndex.value) currentIndex.value -= 1
}

// Drop everything that would play after the playing track. Under shuffle
// that is the rest of the shuffled order, not the rows below it: clearing by
// row kept tracks that were still to come, and they played anyway.
export function clearUpcoming() {
  if (currentIndex.value < 0) {
    playlist.value = []
    shuffleOrder.value = []
    return
  }
  if (!shuffle.value) {
    playlist.value = playlist.value.slice(0, currentIndex.value + 1)
    return
  }
  ensureShuffleOrder()
  // What has played, and the playing track, in the order they played.
  const kept = shuffleOrder.value.slice(0, shufflePosition() + 1)
  const rows = [...kept].sort((a, b) => a - b)
  const moved = new Map(rows.map((old, i) => [old, i]))
  const list = playlist.value
  playlist.value = rows.map((i) => list[i])
  shuffleOrder.value = kept.map((i) => moved.get(i))
  currentIndex.value = moved.get(currentIndex.value)
}

// Where the row at *i* ends up once the row at *from* moves to *to*.
function movedIndex(i, from, to) {
  if (i === from) return to
  if (from < i && i <= to) return i - 1
  if (to <= i && i < from) return i + 1
  return i
}

export function moveInQueue(from, to) {
  const list = [...playlist.value]
  if (from < 0 || from >= list.length || to < 0 || to >= list.length) return
  const [item] = list.splice(from, 1)
  list.splice(to, 0, item)
  // Under shuffle, moving a row does not change when the track plays.
  if (shuffle.value) {
    ensureShuffleOrder()
    shuffleOrder.value = shuffleOrder.value.map((i) => movedIndex(i, from, to))
  }
  currentIndex.value = movedIndex(currentIndex.value, from, to)
  playlist.value = list
}

/**
 * Move a song in "Up next" (dragged in the queue). `from` and `to` are places
 * in the order the songs will play, which under shuffle is not the list's.
 */
export function moveUpcoming(from, to) {
  const up = upcoming.value
  if (from === to || from < 0 || to < 0 || from >= up.length || to >= up.length) return
  if (shuffle.value && shuffleOrder.value.length === playlist.value.length) {
    const order = [...shuffleOrder.value]
    const base = order.indexOf(currentIndex.value) + 1
    const [item] = order.splice(base + from, 1)
    order.splice(base + to, 0, item)
    shuffleOrder.value = order
    return
  }
  moveInQueue(up[from], up[to])
}
