import { watch } from 'vue'
import API from '/src/model/api'
import { useLibrary } from '/src/model/library'
import { rememberPlayed } from '/src/model/recent'
import {
  reportNetworkFailure,
  useConnectivity,
  whenOnline,
} from '/src/model/connectivity'
import { toast } from '/src/model/toast'
import { repairFiles } from '/src/model/repair'
import { t } from '/src/i18n'
import { audio } from '/src/model/player/decks'
import { loadLyricsForCurrent } from '/src/model/player/lyrics'
import { syncMediaSession } from '/src/model/player/mediaSession'
import { hasNextInOrder } from '/src/model/player/order'
import { removeFromQueue } from '/src/model/player/queue'
import { scheduleSessionSave } from '/src/model/player/session'
import { musicLink } from '/src/model/player/sessionFormat'
import {
  YT_ID,
  currentIndex,
  currentTime,
  currentTrack,
  duration,
  isBuffering,
  isPlaying,
  playGen,
  playlist,
  videoIdOf,
} from '/src/model/player/state'
import { next, playAt, seek } from '/src/model/player/transport'

// When a track will not play: a saved file that has gone or broken, a stream
// that failed, a run of either. And the details a track came without (an
// online copy, an entry an older version saved thinly), asked for as it
// comes up.

const connectivity = useConnectivity()

// The button on a "would not play" message for a saved track in the library.
// *force* is for a file the backend thinks is fine: it failed here all the
// same, and a fresh copy is still the fix.
export function repairAction(file, force = false) {
  if (!file) return {}
  return {
    timeout: 9000,
    action: { label: t('repair.action'), run: () => repairFiles([file], { force }) },
  }
}

// Consecutive saved files that would not play, reset by the first that
// does. Stops one click walking a whole queue of dead tracks.
let deadRun = 0
// Streams already retried once after failing, so a second failure moves on.
const streamRetried = new WeakSet()
const DEAD_RUN_LIMIT = 3

// ---------------------------------------------------------------------------
// Saved songs that are not saved any more
// ---------------------------------------------------------------------------
// A song deleted from this computer (here, or in Explorer) is usually still
// on YouTube Music. The queue used to find out by trying: the song failed,
// a message said it "may have been moved or deleted", and it was skipped,
// though it would have played perfectly well online.

const _library = useLibrary()

/** The YouTube Music copy of a saved song, or null when it has none. */
function onlineCopyOf(track) {
  const vid = track && track.video_id
  if (!vid || !YT_ID.test(vid)) return null
  return {
    type: 'stream',
    file: null,
    song_id: vid,
    video_id: vid,
    spotify_url: '',
    url: API.streamURL(vid),
    // Its picture was in the file. YouTube Music's is asked for when the
    // song comes up (one request, not one per song in a long queue).
    cover: '',
    title: track.title || '',
    artist: track.artist || '',
    album: track.album || '',
    duration: track.duration || 0,
    savedCopyGone: true,
  }
}

// A YouTube or Spotify track without what the views show: the online copy of
// a saved song (its picture was in the file), or an entry a version before
// this one wrote down thinly. Asked for once per run, as each one comes up,
// rather than for a whole long queue at once.
export function needsDetails(track) {
  if (!track || track.type !== 'stream') return false
  if (!videoIdOf(track) && !track.spotify_url) return false
  return !track.title || !track.artist || !track.cover
}

const detailsAsked = new Set()
export function fillMissingDetails(track) {
  const vid = videoIdOf(track)
  const key = vid || track.spotify_url
  if (!key || detailsAsked.has(key)) return
  detailsAsked.add(key)
  API.resolveStream(vid ? musicLink(vid) : track.spotify_url)
    .then((res) => {
      const song = (res && res.data) || {}
      const names = Array.isArray(song.artists) ? song.artists : []
      const hadNames = !!track.title && !!track.artist
      // Only what is missing: what the track already says was right.
      if (!track.title && song.name) track.title = song.name
      if (!track.artist && names.length) track.artist = names.join(', ')
      if (!track.album && song.album_name) track.album = song.album_name
      if (!track.cover && song.cover_url) track.cover = song.cover_url
      if (!track.duration && song.duration > 0) track.duration = song.duration
      if (!track._song) {
        track._song = {
          ...song,
          song_id: track.song_id || song.song_id || vid,
          video_id: vid || song.video_id || '',
          name: track.title,
          artists: names.length ? names : track.artist ? track.artist.split(', ') : [],
          album_name: track.album,
          cover_url: track.cover,
          duration: track.duration,
        }
        delete track._song.stream_url
        delete track._song.stream_mime
      }
      scheduleSessionSave()
      if (currentTrack.value !== track) return
      if (!duration.value && track.duration) duration.value = track.duration
      syncMediaSession()
      // The lookup that ran without a title found nothing to look up.
      if (!hadNames) loadLyricsForCurrent()
      // Its tile on Home now has the picture and the names.
      rememberPlayed(track)
    })
    .catch(() => {
      // Offline, or YouTube said no: asked again the next time it comes up.
      detailsAsked.delete(key)
    })
}

/** Put the online copy in a saved song's place and play it from *at*. */
function useOnlineCopy(index, copy, at = 0) {
  if (index < 0 || index >= playlist.value.length) return
  const list = [...playlist.value]
  list[index] = copy
  playlist.value = list
  playAt(index, { again: true })
  if (at > 1) setTimeout(() => seek(at), 600)
}

// The playing element failed. A saved file is asked why before anything is
// said; a stream is retried, waited on while offline, or skipped.
export function onPlaybackError() {
  const track = currentTrack.value
  if (!track) return
  isBuffering.value = false
  if (track.type !== 'stream') {
    // A saved file that will not play. This used to return here and do
    // nothing at all: no message, no skip, just a track sitting there that
    // was never going to start.
    //
    // Then it said so and skipped, which is right for one bad file and
    // wrong for a folder of them: skipping raises the next error, which
    // skips again, so one click walked the whole queue and stacked a toast
    // for every track in it. What looked like three failures was one, three
    // deep. So it stops after a few in a row, and says that instead.
    const err = audio.error
    console.error('[player] audio error', {
      code: err && err.code,
      message: err && err.message,
      networkState: audio.networkState,
      readyState: audio.readyState,
      src: audio.currentSrc,
    })
    // Why, first: the audio element cannot say (a 404 and a 409 both reach
    // it as MEDIA_ERR_SRC_NOT_SUPPORTED), so the server is asked. A file
    // that is simply not there any more is not a failure at all when the
    // song is on YouTube Music: it goes on from there, where it was.
    const src = audio.currentSrc
    const gen = playGen
    const at = currentTime.value
    fetch(src, { method: 'HEAD' })
      .then(
        (probe) => probe.status,
        () => 0
      )
      .then((status) => {
        if (gen !== playGen || currentTrack.value !== track) return
        const copy = status === 404 ? onlineCopyOf(track) : null
        if (copy) useOnlineCopy(currentIndex.value, copy, at)
        else savedTrackFailed(track, err, src, status)
      })
    return
  }
  const gen = playGen
  const at = currentTime.value
  // Wait for the verdict: the old code read "online" before the check
  // had run, so the first failure of a real outage never armed the
  // resume, and a failure while online just left the player sitting
  // there "playing" with no sound and a frozen bar.
  reportNetworkFailure().then((isOnline) => {
    if (gen !== playGen || currentTrack.value !== track) return
    if (!isOnline && track.savedCopyGone && hasNextInOrder()) {
      // Its saved copy has gone and there is no connection to play it
      // from. Waiting here would hold up every saved song after it.
      toast(t('player.notSavedOffline', { title: track.title || t('common.unknownTrack') }), {
        key: 'not-saved-offline',
      })
      next()
      return
    }
    if (!isOnline) {
      // Died because the network did: carry on when it is back.
      whenOnline(() => {
        if (gen !== playGen || currentTrack.value !== track) return
        playAt(currentIndex.value)
        if (at > 1) setTimeout(() => seek(at), 600)
      })
      return
    }
    // Online, so the stream itself failed. Once is often an expired
    // address that a fresh request replaces, so try again quietly.
    if (!streamRetried.has(track)) {
      streamRetried.add(track)
      playAt(currentIndex.value, { again: true })
      if (at > 1) setTimeout(() => seek(at), 600)
      return
    }
    isPlaying.value = false
    deadRun += 1
    if (deadRun >= DEAD_RUN_LIMIT) {
      toast(t('player.manyStreamsFailed'), { tone: 'error' })
      deadRun = 0
      return
    }
    toast(t('player.streamFailed'), { tone: 'error' })
    if (hasNextInOrder()) next()
  })
}

// The first track to start after a run of ones that would not.
export function noteStarted() {
  deadRun = 0
}

// A saved song that would not play, and has no online copy to go to.
function savedTrackFailed(track, err, src, status) {
  // Skipping raises the next error, which skips again, so one click on a
  // folder of bad files walked the whole queue and stacked a toast for each.
  // It stops after a few in a row, and says that instead.
  deadRun += 1
  if (deadRun >= DEAD_RUN_LIMIT) {
    toast(t('player.manyUnplayable'), { tone: 'error' })
    isPlaying.value = false
    deadRun = 0
    return
  }
  const title = track.title || t('common.unknownTrack')
  const index = currentIndex.value
  if (status === 404) {
    // Not there any more, and nowhere else to play it from: said once, and
    // out of the queue so it does not come round again.
    toast(t('player.fileGone', { title }), { key: `gone:${track.file}` })
    if (hasNextInOrder()) next()
    else isPlaying.value = false
    if (playlist.value[index] === track) removeFromQueue(index)
    return
  }
  // A 409 is the backend's answer for a container this installation has no
  // key for: the file is right there, so it is offered a repair rather than
  // a hint that it was moved. Named, so two broken songs are two messages,
  // each with its own Repair button.
  const kind = status === 409 || (err && err.code === 3) ? 'fileUnreadable' : 'fileUnplayable'
  const file = track.file && /\/downloads\//.test(src) ? track.file : ''
  toast(t(`player.${kind}`, { title }), {
    tone: 'error',
    ...(kind === 'fileUnreadable' ? repairAction(file, status !== 409) : {}),
  })
  if (hasNextInOrder()) next()
  else isPlaying.value = false
}

// Put the queue right whenever the library is read again (a download, a
// delete here, a file moved in Explorer, coming back to the window): a saved
// song whose file has gone plays from its new place if it was only moved,
// from YouTube Music if it is there, and otherwise leaves the queue, before
// it ever comes up. The playing song is left to finish what it has.
function settleMissingSaved() {
  if (!_library.loaded.value || _library.error.value) return
  const list = playlist.value
  if (!list.length) return
  const saved = new Set()
  const byVideo = new Map()
  for (const tr of _library.tracks.value) {
    if (!tr || !tr.file) continue
    saved.add(tr.file)
    if (tr.video_id && !tr.problem) byVideo.set(tr.video_id, tr.file)
  }
  let swapped = null
  const gone = []
  list.forEach((tr, i) => {
    if (!tr || tr.type !== 'local' || !tr.file || saved.has(tr.file)) return
    if (i === currentIndex.value) return
    const moved = tr.video_id && byVideo.get(tr.video_id)
    const replacement = moved
      ? { ...tr, file: moved, url: API.downloadFileURL(moved), cover: API.coverFileURL(moved) }
      : onlineCopyOf(tr)
    if (replacement) (swapped || (swapped = [...list]))[i] = replacement
    else gone.push(i)
  })
  if (swapped) playlist.value = swapped
  for (const i of gone.reverse()) removeFromQueue(i)
}
watch([() => _library.tracks.value, () => _library.loaded.value], settleMissingSaved)
