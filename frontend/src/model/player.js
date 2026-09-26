import { ref, computed } from 'vue'
import API from '/src/model/api'
import { useLibraryIndex } from '/src/model/libraryIndex'
import { useUi } from '/src/model/ui'
import { rememberPlayed } from '/src/model/recent'
import {
  reportNetworkFailure,
  useConnectivity,
  whenOnline,
} from '/src/model/connectivity'
import { toast } from '/src/model/toast'
import { repairFiles } from '/src/model/repair'
import { t } from '/src/i18n'

const connectivity = useConnectivity()

// The button on a "would not play" message for a saved track in the library.
// *force* is for a file the backend thinks is fine: it failed here all the
// same, and a fresh copy is still the fix.
function repairAction(file, force = false) {
  if (!file) return {}
  return {
    timeout: 9000,
    action: { label: t('repair.action'), run: () => repairFiles([file], { force }) },
  }
}

const _libraryIndex = useLibraryIndex()
const _ui = useUi()
// One-shot guard for the auto-open-lyrics-on-first-play affordance.
let _lyricsAutoOpened = false
// Prime the index on app boot: the data is small (one /api/library call)
// and being already loaded means the first time the user clicks a search
// result trackFromSong() returns a local file synchronously.
_libraryIndex.load()

const VOLUME_KEY = 'dannify-player-volume'

const playlist = ref([])
const currentIndex = ref(-1)
const isPlaying = ref(false)
const isBuffering = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const volume = ref(parseFloat(localStorage.getItem(VOLUME_KEY) || '0.85'))

// --- Per-track loudness normalization ---
//
// A YouTube mix puts a loud modern single next to a quiet album cut and the
// difference is jarring. YouTube publishes how far above its own target each
// track was mastered, so the fix is to turn the loud ones down.
//
// Attenuate only. Boosting a quiet track means clipping its peaks, and a
// limiter to catch them is not worth the complexity here, so anything at or
// below the target is left exactly as it is. In practice that is most
// tracks: the filter is the exception, not the rule.
const TARGET_LUFS = -7 // YouTube Music's target, not the video site's -14
const MAX_ATTENUATION_DB = -24
const trackGain = ref(1)

function gainFor(loudnessDb) {
  if (typeof loudnessDb !== 'number' || !Number.isFinite(loudnessDb)) return 1
  const db = TARGET_LUFS - (loudnessDb - 14)
  if (db >= -0.05) return 1 // at or under target: leave it alone
  return Math.pow(10, Math.max(db, MAX_ATTENUATION_DB) / 20)
}

// Everything that sets the element's volume goes through here, so the user's
// setting and the per-track gain can never get out of step.
function applyVolume() {
  if (!audio) return
  audio.volume = Math.max(0, Math.min(1, volume.value * trackGain.value))
}
const isMuted = ref(false)
// Shuffle and repeat are a listening preference, not a per-session accident:
// someone who listens on shuffle expects to still be on shuffle tomorrow.
const REPEAT_KEY = 'dannify-repeat'
const SHUFFLE_KEY = 'dannify-shuffle'

function remembered(key, allowed, fallback) {
  try {
    const value = localStorage.getItem(key)
    if (value !== null && allowed.includes(value)) return value
  } catch {
    // Blocked storage: the default is fine.
  }
  return fallback
}

const repeatMode = ref(remembered(REPEAT_KEY, ['off', 'all', 'one'], 'off'))
const shuffle = ref(remembered(SHUFFLE_KEY, ['0', '1'], '0') === '1')
const playbackRate = ref(1.0)
// Autoplay: when the queue runs dry, keep going with YouTube Music's endless
// mix for the last track: the behaviour every streaming app has.
const AUTOPLAY_KEY = 'dannify-autoplay-radio'
const autoplayRadio = ref(localStorage.getItem(AUTOPLAY_KEY) !== '0')
let radioSeed = ''

// Consecutive saved files that would not play, reset by the first that
// does. Stops one click walking a whole queue of dead tracks.
let deadRun = 0
const DEAD_RUN_LIMIT = 3

// --- Session restore ---
//
// Closing a music player and reopening it to silence and an empty queue is
// the difference between an app and a web page. The queue, which track was
// playing and how far into it are kept, and the next launch comes back to
// exactly that, paused. Deliberately paused: starting audio on its own
// before the window has even finished drawing is startling, and there is a
// play button right there.
const SESSION_KEY = 'dannify.session.v1'
// Past this the queue is someone else's afternoon. Coming back to it would
// be surprising rather than helpful.
const SESSION_TTL_MS = 14 * 24 * 60 * 60 * 1000
// A queue longer than this is a whole playlist; storing all of it every few
// seconds is not worth the quota.
const SESSION_MAX_TRACKS = 200
let sessionTimer = null
let sessionRestored = false

function saveSession() {
  try {
    const list = playlist.value
    if (!list.length || currentIndex.value < 0) {
      localStorage.removeItem(SESSION_KEY)
      return
    }
    localStorage.setItem(
      SESSION_KEY,
      JSON.stringify({
        // A saved track keeps its path, not its URL. The URL names a file
        // that can be renamed between one run and the next, and converting
        // the library to containers renames all of them, so a queue written
        // before that came back pointing at files that no longer existed.
        // The path survives it; the URL is rebuilt on the way back in.
        tracks: list.slice(0, SESSION_MAX_TRACKS).map((t) =>
          t && t.type === 'local' && t.file ? { ...t, url: '', cover: '' } : t
        ),
        index: Math.min(currentIndex.value, SESSION_MAX_TRACKS - 1),
        time: Math.max(0, Math.floor(currentTime.value || 0)),
        ts: Date.now(),
      }),
    )
  } catch {
    // Quota or blocked storage: the session just will not come back.
  }
}

// Called from the time update, so it has to be cheap. Writes at most once
// every few seconds rather than four times a second.
function scheduleSessionSave() {
  if (sessionTimer) return
  sessionTimer = setTimeout(() => {
    sessionTimer = null
    saveSession()
  }, 4000)
}

function readSession() {
  try {
    const blob = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null')
    if (!blob || !Array.isArray(blob.tracks) || !blob.tracks.length) return null
    if (Date.now() - (blob.ts || 0) > SESSION_TTL_MS) return null
    const index = Number(blob.index)
    if (!Number.isInteger(index) || index < 0 || index >= blob.tracks.length) return null
    // Every url we store is relative, so a new port on the next launch does
    // not invalidate them. Anything absolute is from an older build.
    if (blob.tracks.some((t) => !t || typeof t.url !== 'string' || /^https?:/i.test(t.url))) {
      return null
    }
    // Rebuild the URL of every saved track from its path. Entries written by
    // an older build still carry the url the file had then, and that is the
    // one thing here that is allowed to be out of date.
    blob.tracks = blob.tracks.map((t) =>
      t && t.type === 'local' && t.file
        ? { ...t, url: API.downloadFileURL(t.file), cover: API.coverFileURL(t.file) }
        : t
    )
    return blob
  } catch {
    return null
  }
}

// Load the track the user left off on, cued to where they left it, without
// starting it.
function restoreSession() {
  if (sessionRestored) return false
  sessionRestored = true
  const blob = readSession()
  if (!blob) return false
  playlist.value = blob.tracks
  currentIndex.value = blob.index
  if (shuffle.value) buildShuffleOrder()
  const track = blob.tracks[blob.index]
  const at = Math.max(0, Number(blob.time) || 0)
  duration.value = track.duration || 0
  currentTime.value = at
  const a = ensureAudio()
  try {
    a.src = track.url
    // The element has no idea how long the track is until it has read the
    // headers, and seeking before that silently does nothing.
    const seek = () => {
      try {
        if (at > 0 && at < (a.duration || Infinity)) a.currentTime = at
      } catch {
        // A stream that refuses to seek still plays from the start.
      }
      a.removeEventListener('loadedmetadata', seek)
    }
    a.addEventListener('loadedmetadata', seek)
    a.load()
  } catch {
    return false
  }
  syncMediaSession()
  if (track.type === 'stream') ensureStreamDuration(track)
  // Lyrics are fetched when a track starts playing, and a restored one has
  // not started: without this the panel said "No lyrics found" for the track
  // in the player on every launch, until something else was played.
  loadLyricsForCurrent()
  return true
}

if (typeof window !== 'undefined') {
  // The window can vanish without a clean shutdown (tray quit, a crash), so
  // the throttled save is backed up by one on the way out.
  window.addEventListener('beforeunload', saveSession)
  window.addEventListener('pagehide', saveSession)
}

// --- Clip-loop (used by the sync editor) ---
// When set, the audio loops between [clipLoopStart, clipLoopEnd]. Lets the
// editor focus on a single lyric line so the user can re-stamp it without
// rewinding the whole song.
const clipLoopStart = ref(null)
const clipLoopEnd = ref(null)
// When true, audio ``ended`` does NOT auto-advance to the next track.
// Used by the lyrics sync editor: when the user is mid-edit and the song
// reaches the end, just stop: don't load a new track and reset the
// editor's context.
const noAutoAdvance = ref(false)

// --- Synced lyrics state ---
const lyricsLines = ref([]) // [{ time, text }]
const lyricsPlain = ref(null)
const lyricsLoading = ref(false)
const activeLyricIndex = ref(-1)
const lyricsOffset = ref(0) // seconds; positive = lyrics appear later
const lyricsMeta = ref({ title: '', artist: '' }) // for saving offsets
const lyricVersions = ref([]) // all synced versions [{synced, plain}]
const lyricVersionIndex = ref(0) // which version is showing
const lyricVersionCount = ref(0) // how many versions exist
let lyricsToken = 0

let audio = null
let shuffleOrder = []
let shufflePos = 0
// Monotonic token bumped on every track change; async work checks it so stale
// callbacks from a previous track are discarded (prevents wrong-song audio).
let playGen = 0
// For length-less remux streams: server starts output at this offset, so the
// element's currentTime is relative to it: we add it back for the UI clock.
let streamBaseOffset = 0

function ensureAudio() {
  if (audio) return audio
  audio = new Audio()
  audio.preload = 'metadata'
  applyVolume()
  audio.addEventListener('timeupdate', () => {
    const track = currentTrack.value
    // With the byte-range proxy the browser knows the real currentTime
    // for streams too: no need for the virtual clock anymore. The
    // ``streamBaseOffset`` shim is only kept for the legacy ``?t=`` /
    // ffmpeg fallback path; it's 0 on the happy path.
    if (track && track.type === 'stream' && streamBaseOffset > 0) {
      currentTime.value = streamBaseOffset + audio.currentTime
    } else {
      currentTime.value = audio.currentTime
    }
    scheduleSessionSave()
    // Clip-loop wrap-around: if a region is active and the playhead has
    // crossed the end, jump back to the start. Used by the sync editor
    // so the user can re-stamp a single line without rewinding the song.
    const ls = clipLoopStart.value
    const le = clipLoopEnd.value
    if (ls != null && le != null && audio && currentTime.value >= le) {
      try {
        audio.currentTime = ls
      } catch {
        // ignore: some streams reject assignment briefly post-seek
      }
    }
    updateActiveLyric()
  })
  audio.addEventListener('loadedmetadata', () => {
    const track = currentTrack.value
    // Byte-range proxy streams now expose a real numeric duration via
    // Content-Length: use it directly. Only fall back to /api/stream/info
    // if for some reason the browser still reports Infinity/NaN (e.g.
    // the legacy ffmpeg path is in effect).
    if (track && track.type === 'stream') {
      if (isFinite(audio.duration) && audio.duration > 0) {
        duration.value = audio.duration
      } else if (!duration.value) {
        ensureStreamDuration(track)
      }
      return
    }
    if (isFinite(audio.duration) && audio.duration > 0) {
      duration.value = audio.duration
    } else {
      const track = currentTrack.value
      if (track && track.type === 'stream' && !duration.value) {
        ensureStreamDuration(track)
      }
    }
  })
  audio.addEventListener('durationchange', () => {
    const track = currentTrack.value
    if (track && track.type === 'stream') return // length-less remux
    if (isFinite(audio.duration) && audio.duration > 0) {
      duration.value = audio.duration
    }
  })
  audio.addEventListener('waiting', () => {
    isBuffering.value = true
  })
  audio.addEventListener('playing', () => {
    isBuffering.value = false
    deadRun = 0
  })
  audio.addEventListener('canplay', () => {
    isBuffering.value = false
  })
  audio.addEventListener('ended', onEnded)
  audio.addEventListener('error', () => {
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
      deadRun += 1
      if (deadRun >= DEAD_RUN_LIMIT) {
        toast(t('player.manyUnplayable'), { tone: 'error' })
        isPlaying.value = false
        deadRun = 0
        return
      }
      // Which message depends on why, and the audio element cannot say why:
      // a 404 and a 409 both reach it as MEDIA_ERR_SRC_NOT_SUPPORTED. So ask
      // the server. A 409 is the backend's answer for a container this
      // installation has no key for, and telling that person their file may
      // have been moved or deleted sends them looking in the wrong place for
      // a file that is sitting right there.
      const src = audio.currentSrc
      const fallback = err && err.code === 3 ? 'fileUnreadable' : 'fileUnplayable'
      // A file that is there and will not play can be repaired. One that is
      // not there cannot: that is somebody having moved or deleted it.
      const file = track.file && /\/downloads\//.test(src) ? track.file : ''
      const say = (kind, status) =>
        toast(t(`player.${kind}`), {
          tone: 'error',
          ...(kind === 'fileUnreadable' ? repairAction(file, status !== 409) : {}),
        })
      fetch(src, { method: 'HEAD' })
        .then((probe) => {
          if (probe.status === 409) say('fileUnreadable', 409)
          else if (probe.status === 404) say('fileUnplayable', 404)
          else say(fallback, probe.status)
        })
        .catch(() => say(fallback, 0))
      if (currentIndex.value < playlist.value.length - 1) next()
      else isPlaying.value = false
      return
    }
    const gen = playGen
    const at = currentTime.value
    reportNetworkFailure()
    // Only resume automatically for a track that died because the network
    // did. Retrying a stream that is simply unplayable would loop forever,
    // so when we are demonstrably online this just stops.
    if (connectivity.online.value) return
    whenOnline(() => {
      if (gen !== playGen || currentTrack.value !== track) return
      playAt(currentIndex.value)
      if (at > 1) setTimeout(() => seek(at), 600)
    })
  })
  audio.addEventListener('play', () => {
    isPlaying.value = true
    syncMediaSession()
  })
  audio.addEventListener('pause', () => {
    isPlaying.value = false
    syncMediaSession()
  })
  return audio
}

// One implementation of the path encoding, in api.js. There were three, and
// this one encoded the whole path with encodeURIComponent, so the separators
// came out as %2F and a track in a subfolder asked for a file that was not
// there.
const fileUrl = (file) => API.downloadFileURL(file)
const coverUrl = (file) => API.coverFileURL(file)

function trackFromFile(file) {
  const noExt = file.replace(/\.[^.]+$/, '')
  let artist = ''
  let title = noExt
  const dash = noExt.indexOf(' - ')
  if (dash > 0) {
    artist = noExt.slice(0, dash).trim()
    title = noExt.slice(dash + 3).trim()
  }
  return {
    type: 'local',
    file,
    url: fileUrl(file),
    cover: coverUrl(file),
    title,
    artist,
  }
}

// Build a streaming track from a resolved/preview song dict.
//
// Two kinds of song dicts arrive here:
//  * YouTube-sourced (search / explorer): ``song_id`` is a real 11-char
//    YouTube videoId: we can stream it directly.
//  * Spotify-sourced (preview of a pasted link): ``song_id`` is a 22-char
//    Spotify track id with no YouTube match yet: we must stream by URL so
//    the backend resolves the matching YouTube video first.
function trackFromSong(song) {
  const artists = song.artists || []
  const spotifyUrl =
    song.url && song.url.includes('spotify') ? song.url : ''

  // A YouTube videoId is exactly 11 url-safe chars. Anything else (e.g. a
  // Spotify 22-char id) is NOT a playable video id.
  const isYtId = (v) =>
    typeof v === 'string' && /^[A-Za-z0-9_-]{11}$/.test(v)

  let videoId = ''
  if (isYtId(song.video_id)) videoId = song.video_id
  else if (song.source === 'youtube' && isYtId(song.song_id))
    videoId = song.song_id
  else if (!spotifyUrl && isYtId(song.song_id)) videoId = song.song_id

  // ---------------------------------------------------------------------
  // Local-first: if this song is already downloaded, ALWAYS play the
  // on-disk file. Zero ffmpeg, zero network, instant start, lyrics from
  // the local .lrc. The library index is pre-loaded on app boot and
  // refreshed whenever a download finishes (WS library_changed event).
  // ---------------------------------------------------------------------
  try {
    const localFile = _libraryIndex && _libraryIndex.localFileFor(song)
    if (localFile) {
      const stem = localFile.replace(/\.[^.]+$/, '')
      const slash = stem.lastIndexOf('/')
      const tail = slash >= 0 ? stem.slice(slash + 1) : stem
      const dash = tail.indexOf(' - ')
      const guessedArtist = dash > 0 ? tail.slice(0, dash) : ''
      const guessedTitle = dash > 0 ? tail.slice(dash + 3) : tail
      return {
        type: 'local',
        file: localFile,
        url: API.downloadFileURL(localFile),
        cover: API.coverFileURL(localFile),
        title: song.name || guessedTitle,
        artist:
          (Array.isArray(artists) ? artists.join(', ') : String(artists || '')) ||
          guessedArtist,
        album: song.album_name || '',
        duration: song.duration || 0,
        video_id: videoId,
        song_id: song.song_id || videoId,
        _song: song,
      }
    }
  } catch {
    // libraryIndex not yet imported: fall through to stream track.
  }

  // Stream URL: prefer a real videoId; otherwise hand the Spotify URL to the
  // backend (/api/stream?url=) which resolves + matches it to YouTube.
  let url
  if (videoId) url = API.streamURL(videoId)
  else if (spotifyUrl) url = API.streamURLFromLink(spotifyUrl)
  else url = API.streamURL(song.song_id || '') // last-ditch

  return {
    type: 'stream',
    file: null,
    song_id: song.song_id || videoId,
    video_id: videoId, // '' until resolved (Spotify case)
    spotify_url: spotifyUrl,
    url,
    cover: song.cover_url || '',
    title: song.name || '',
    artist: Array.isArray(artists) ? artists.join(', ') : String(artists || ''),
    album: song.album_name || '',
    duration: song.duration || 0,
    _song: song,
  }
}

// --- Synced lyrics ---
function _lyricsParams(track) {
  if (track.type === 'local' && track.file) {
    // Send the file AND what we know about the track. The backend used to
    // get only the filename, so an online lookup could only go on whatever
    // tags the download happened to write. When those are thin (a missing
    // artist is enough) the lookup was skipped entirely, which is why
    // lyrics published for a downloaded song never came back.
    return {
      file: track.file,
      title: track.title || '',
      artist: track.artist || '',
      album: track.album || '',
      duration: Math.round(track.duration || duration.value || 0),
    }
  }
  if (track.spotify_url) return { url: track.spotify_url }
  return {
    title: track.title,
    artist: track.artist,
    album: track.album || '',
    duration: Math.round(track.duration || duration.value || 0),
  }
}

async function loadLyricsForCurrent(forceRefresh = false) {
  const track = currentTrack.value
  lyricsLines.value = []
  lyricsPlain.value = null
  activeLyricIndex.value = -1
  lyricVersions.value = []
  lyricVersionIndex.value = 0
  lyricVersionCount.value = 0
  if (!track) return
  const token = ++lyricsToken
  lyricsLoading.value = true
  try {
    const params = _lyricsParams(track)
    if (forceRefresh) params.refresh = 1
    const res = await API.getLyrics(params)
    if (token !== lyricsToken) return // a newer track took over
    const data = res.data || {}
    lyricsLines.value = data.synced || []
    lyricsPlain.value = data.plain || null
    lyricsOffset.value = typeof data.offset === 'number' ? data.offset : 0
    lyricVersionIndex.value =
      typeof data.version === 'number' ? data.version : 0
    lyricVersionCount.value =
      typeof data.version_count === 'number' ? data.version_count : 0
    lyricsMeta.value = {
      title: data.title || track.title || '',
      artist:
        data.artist ||
        (Array.isArray(track.artists) && track.artists[0]) ||
        (track.artist || '').split(',')[0].trim() ||
        '',
    }
    updateActiveLyric()
  } catch {
    if (token === lyricsToken) {
      lyricsLines.value = []
      lyricsPlain.value = null
      lyricsOffset.value = 0
    }
  } finally {
    if (token === lyricsToken) lyricsLoading.value = false
  }
}

function updateActiveLyric() {
  const lines = lyricsLines.value
  if (!lines || lines.length === 0) {
    activeLyricIndex.value = -1
    return
  }
  // Apply the per-song offset: positive = lyrics appear later, so we compare
  // against (currentTime - offset).
  const tNow = currentTime.value - lyricsOffset.value
  let idx = -1
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].time <= tNow + 0.25) idx = i
    else break
  }
  if (idx !== activeLyricIndex.value) activeLyricIndex.value = idx
}

function seekToLyric(index) {
  const lines = lyricsLines.value
  if (index < 0 || index >= lines.length) return
  // Honour the offset so clicking a line jumps to where it actually plays.
  seek(lines[index].time + lyricsOffset.value)
  if (!isPlaying.value) play()
}

// Manually re-fetch lyrics for the current track, bypassing all caches.
function refreshLyrics() {
  return loadLyricsForCurrent(true)
}

function sameSong(a, b) {
  const norm = (s) =>
    String(s || '')
      .toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, '')
  return !!norm(a) && norm(a) === norm(b)
}

// Someone just published lyrics for a song. If it's the one on screen, pull
// them in: indexing needs a beat, so give it a couple of tries
// rather than leaving the panel stubbornly empty.
async function onLyricsPublished(detail) {
  const track = currentTrack.value
  if (!track || !detail) return
  const title = track.title || ''
  const artist = (track.artist || '').split(',')[0].trim()
  if (!sameSong(detail.track, title)) return
  if (detail.artist && artist && !sameSong(detail.artist, artist)) return
  for (const wait of [0, 1500, 4000]) {
    if (wait) await new Promise((r) => setTimeout(r, wait))
    if (currentTrack.value !== track) return
    await loadLyricsForCurrent(true)
    if (lyricsLines.value.length || lyricsPlain.value) return
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('dannify:lyrics-published', (e) => onLyricsPublished(e.detail))
}

// Nudge the lyric sync live (seconds). Updates the active line immediately.
function adjustLyricsOffset(delta) {
  const next = Math.max(-30, Math.min(30, lyricsOffset.value + delta))
  lyricsOffset.value = Math.round(next * 10) / 10
  updateActiveLyric()
}

function resetLyricsOffset() {
  lyricsOffset.value = 0
  updateActiveLyric()
}

// Persist the current offset for this song so it's shared with future users.
function saveLyricsOffset() {
  const { title, artist } = lyricsMeta.value
  if (!title || !artist) return Promise.resolve()
  return API.saveLyricsOffset(
    title,
    artist,
    lyricsOffset.value,
    lyricVersionCount.value > 1 ? lyricVersionIndex.value : undefined
  ).catch(() => {})
}

// Cycle to the next synced lyric version (when there are several). Lazily
// fetches the full version list the first time it's needed.
async function switchLyricVersion(dir = 1) {
  const track = currentTrack.value
  if (!track) return
  if (lyricVersions.value.length === 0) {
    // Load all versions on demand.
    try {
      const res = await API.getLyricVersions(_lyricsParams(track))
      lyricVersions.value = (res.data && res.data.versions) || []
    } catch {
      lyricVersions.value = []
    }
    if (lyricVersions.value.length === 0) return
  }
  const n = lyricVersions.value.length
  if (n <= 1) return
  lyricVersionIndex.value = (lyricVersionIndex.value + dir + n) % n
  const v = lyricVersions.value[lyricVersionIndex.value]
  lyricsLines.value = v.synced || []
  lyricsPlain.value = v.plain || null
  lyricVersionCount.value = n
  updateActiveLyric()
}

// --- Stream duration + prefetch (speed) ---
async function ensureStreamDuration(track) {
  if (!track || track.type !== 'stream' || !track.video_id) return
  const haveDuration = track.duration > 0
  if (haveDuration) duration.value = track.duration
  // The gain is worth one more call even when the duration is known: the
  // backend answers this from the same cache entry it resolved the stream
  // from, so a warm track costs about a millisecond.
  if (haveDuration && track.gain !== undefined) return
  try {
    const res = await API.getStreamInfo(track.video_id)
    const d = (res.data && res.data.duration) || 0
    if (d > 0) {
      track.duration = d
      // Only apply if this is still the current track.
      if (currentTrack.value === track) duration.value = d
    }
    track.gain = gainFor(res.data && res.data.loudness_db)
    if (currentTrack.value === track) {
      trackGain.value = track.gain
      applyVolume()
    }
  } catch {
    // ignore: duration stays 0 (live/unknown) and the volume stays untouched
  }
}

// Warm the next stream's cache file (and lyrics) so advancing the queue is
// instant and lyrics are ready before the next track even starts.
let prefetchTimer = null
function prefetchNext(index) {
  clearTimeout(prefetchTimer)
  prefetchTimer = setTimeout(() => {
    const ni = index + 1
    const nxt = playlist.value[ni]
    if (!nxt) return
    if (nxt.type === 'stream' && nxt.video_id) {
      // prefetch=1 → server transcodes the next track to cache in background.
      API.getStreamInfo(nxt.video_id, 1).catch(() => {})
    }
    prefetchLyrics(nxt)
  }, 500)
}

function prefetchLyrics(track) {
  if (!track) return
  let params
  if (track.type === 'local' && track.file) params = { file: track.file }
  else if (track.spotify_url) params = { url: track.spotify_url }
  else if (track.title) {
    params = {
      title: track.title,
      artist: track.artist || '',
      album: track.album || '',
      duration: Math.round(track.duration || 0),
    }
  }
  if (params) API.getLyrics(params).catch(() => {})
}

// --- Media Session (OS / lock-screen controls) ---
function syncMediaSession() {
  if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) {
    return
  }
  const track = currentTrack.value
  if (!track) return
  try {
    navigator.mediaSession.metadata = new window.MediaMetadata({
      title: track.title || '',
      artist: track.artist || '',
      album: track.album || '',
      // Windows needs an absolute url for the artwork; a relative one
      // resolves to nothing and the flyout shows an empty square.
      artwork: track.cover
        ? [
            {
              src: new URL(track.cover, window.location.href).href,
              sizes: '512x512',
              type: 'image/jpeg',
            },
          ]
        : [],
    })
    navigator.mediaSession.playbackState = isPlaying.value
      ? 'playing'
      : 'paused'
    navigator.mediaSession.setActionHandler('play', () => mediaCommand('play'))
    navigator.mediaSession.setActionHandler('pause', () => mediaCommand('pause'))
    navigator.mediaSession.setActionHandler('previoustrack', () =>
      mediaCommand('prev')
    )
    navigator.mediaSession.setActionHandler('nexttrack', () =>
      mediaCommand('next')
    )
    navigator.mediaSession.setActionHandler('seekto', (d) => {
      if (d.seekTime != null) seek(d.seekTime)
    })
  } catch {
    // MediaSession not fully supported: ignore.
  }
}

function buildShuffleOrder() {
  const indices = playlist.value.map((_, i) => i)
  for (let i = indices.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[indices[i], indices[j]] = [indices[j], indices[i]]
  }
  shuffleOrder = indices
  shufflePos =
    currentIndex.value >= 0
      ? Math.max(0, shuffleOrder.indexOf(currentIndex.value))
      : 0
}

function setPlaylist(files, options = {}) {
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
  if (shuffle.value) buildShuffleOrder()
  if (typeof options.startIndex === 'number') {
    playAt(options.startIndex)
  } else if (options.autoplay && tracks.length > 0 && currentIndex.value < 0) {
    playAt(0)
  }
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
function playStreamSongs(songs, startIndex = 0) {
  setPlaylist(songs.map(trackFromSong), { startIndex })
}

// Trigger a real download for a streamed track (so the user can keep it).
function downloadTrack(track) {
  const song = (track && track._song) || null
  if (!song) return Promise.resolve()
  return API.download(song).catch(() => {})
}

function toTrack(item) {
  if (typeof item === 'string') return trackFromFile(item)
  if (item && item.url && (item.type === 'local' || item.type === 'stream')) {
    return item
  }
  return trackFromSong(item)
}

// Insert tracks right after the current one ("Play next") or at the end of
// the queue ("Add to queue"). Accepts track objects, song dicts or file
// paths. Starts playback when nothing is loaded yet.
function enqueue(items, { next: asNext = false } = {}) {
  const tracks = (Array.isArray(items) ? items : [items])
    .filter(Boolean)
    .map(toTrack)
  if (!tracks.length) return
  const list = [...playlist.value]
  const at =
    asNext && currentIndex.value >= 0 ? currentIndex.value + 1 : list.length
  list.splice(at, 0, ...tracks)
  playlist.value = list
  if (shuffle.value) buildShuffleOrder()
  if (currentIndex.value < 0) playAt(at)
}

function enqueueNext(song) {
  enqueue([song], { next: true })
}

// Remove one entry from the queue without interrupting playback.
function removeFromQueue(index) {
  if (index < 0 || index >= playlist.value.length) return
  if (index === currentIndex.value) {
    // Removing the playing track: skip ahead first, then drop it.
    const list = [...playlist.value]
    list.splice(index, 1)
    playlist.value = list
    if (list.length === 0) {
      currentIndex.value = -1
      pause()
      return
    }
    playAt(Math.min(index, list.length - 1))
    return
  }
  const list = [...playlist.value]
  list.splice(index, 1)
  playlist.value = list
  if (index < currentIndex.value) currentIndex.value -= 1
  if (shuffle.value) buildShuffleOrder()
}

// Drop everything after the playing track.
function clearUpcoming() {
  if (currentIndex.value < 0) {
    playlist.value = []
    return
  }
  playlist.value = playlist.value.slice(0, currentIndex.value + 1)
  if (shuffle.value) buildShuffleOrder()
}

function moveInQueue(from, to) {
  const list = [...playlist.value]
  if (from < 0 || from >= list.length || to < 0 || to >= list.length) return
  const [item] = list.splice(from, 1)
  list.splice(to, 0, item)
  const cur = currentIndex.value
  if (from === cur) currentIndex.value = to
  else if (from < cur && to >= cur) currentIndex.value = cur - 1
  else if (from > cur && to <= cur) currentIndex.value = cur + 1
  playlist.value = list
  if (shuffle.value) buildShuffleOrder()
}

// Media keys can reach us twice (OS media session + keydown while focused).
// Collapse identical commands that land within a few hundred milliseconds.
let _lastMedia = { cmd: '', at: 0 }
function mediaCommand(cmd) {
  const now = performance.now()
  if (_lastMedia.cmd === cmd && now - _lastMedia.at < 350) return
  _lastMedia = { cmd, at: now }
  if (cmd === 'play') play()
  else if (cmd === 'pause') pause()
  else if (cmd === 'toggle') toggle()
  else if (cmd === 'next') next()
  else if (cmd === 'prev') prev()
}

function playAt(index) {
  if (index < 0 || index >= playlist.value.length) return
  const a = ensureAudio()
  currentIndex.value = index
  if (shuffle.value) {
    if (shuffleOrder.length !== playlist.value.length) buildShuffleOrder()
    const pos = shuffleOrder.indexOf(index)
    if (pos >= 0) shufflePos = pos
  }
  const track = playlist.value[index]
  // Bump the generation token so any in-flight async work (duration/lyrics
  // fetches, the previous stream's media events) from the prior track is
  // ignored: this prevents "wrong audio / wrong metadata" races when the
  // user switches tracks quickly.
  playGen += 1
  isBuffering.value = track.type === 'stream'
  streamBaseOffset = 0
  // Point the element at the new track and let it do the rest. This used to
  // clear the src and call load() first, on the theory that the old buffer
  // needed flushing. Assigning a new src already discards it, and the
  // teardown had a cost: with no source the browser drops its media session,
  // so Windows tore the now-playing flyout down and rebuilt it on every
  // skip. That is the blink.
  try {
    a.pause()
  } catch {
    // ignore
  }
  a.src = track.url
  a.currentTime = 0
  // Re-apply playback rate: browsers reset it to 1.0 on src change.
  try {
    a.playbackRate = playbackRate.value
  } catch {
    // ignore
  }
  currentTime.value = 0
  duration.value = track.duration || 0
  // Reset lyrics immediately so the old song's lyrics don't linger.
  lyricsLines.value = []
  lyricsPlain.value = null
  activeLyricIndex.value = -1
  a.play().catch(() => {})
  loadLyricsForCurrent()
  syncMediaSession()
  rememberPlayed(track)
  saveSession()
  // First-play affordance: surface the lyrics panel the very first time
  // the user plays something this session, so they see the headline
  // feature immediately. After that, respect whatever panel state they
  // chose: closing the panel mid-session won't be undone by the next
  // track change. Never pop it over the content on small windows.
  if (
    !_lyricsAutoOpened &&
    _ui.autoOpenLyrics.value &&
    _ui.panel.value == null &&
    !_ui.panelFloating.value
  ) {
    _ui.openPanel('lyrics')
  }
  _lyricsAutoOpened = true
  // A new track starts at unity gain. Carrying the previous track's
  // attenuation over would make the next one quiet for no reason; the real
  // value lands a moment later, before the first chorus.
  trackGain.value = typeof track.gain === 'number' ? track.gain : 1
  applyVolume()
  // For streams, the transcoded body has no length header: fetch the real
  // duration so the progress bar + end time work.
  if (track.type === 'stream') {
    ensureStreamDuration(track)
  }
  // Warm the next track (stream cache + lyrics) regardless of type.
  prefetchNext(index)
}

function play() {
  if (playlist.value.length === 0) return
  const a = ensureAudio()
  if (currentIndex.value < 0) {
    playAt(0)
    return
  }
  if (!a.src) {
    a.src = playlist.value[currentIndex.value].url
  }
  a.play().catch(() => {})
}

function pause() {
  if (audio) audio.pause()
}

function toggle() {
  if (isPlaying.value) pause()
  else play()
}

function seek(seconds) {
  const a = ensureAudio()
  const max = duration.value || 0
  const clamped = Math.max(0, Math.min(max, seconds))
  // For BOTH local files AND streams: just move the playhead.
  // The byte-range proxy lets the browser request the right offset
  // natively (``Range: bytes=N-``) so streams seek just like local files.
  try {
    a.currentTime = clamped
  } catch {
    // Some browsers reject the assignment on a length-less <audio>
    // element. As a last resort, fall through to the legacy server-side
    // seek path that re-spawns ffmpeg with -ss.
    const track = currentTrack.value
    if (track && track.type === 'stream') {
      streamBaseOffset = clamped
      const base =
        track.video_id && /^[A-Za-z0-9_-]{11}$/.test(track.video_id)
          ? API.streamURL(track.video_id)
          : track.url.split('&t=')[0]
      a.src = `${base}${base.includes('?') ? '&' : '?'}t=${Math.floor(clamped)}&force_mp3=1`
      isBuffering.value = true
      a.play().catch(() => {})
    }
  }
  currentTime.value = clamped
}

function seekRatio(ratio) {
  if (!duration.value) return
  seek(duration.value * Math.max(0, Math.min(1, ratio)))
}

// ─── Playback rate (used by the sync editor for slow-mo syncing) ───
function setPlaybackRate(rate) {
  const clamped = Math.max(0.25, Math.min(2.5, Number(rate) || 1.0))
  playbackRate.value = clamped
  if (audio) {
    try {
      audio.playbackRate = clamped
    } catch {
      // ignore: some browsers refuse rates outside [0.5, 2.0]
    }
  }
}

// ─── Clip-loop helpers ───
// Loop the audio between [start, end]. The sync editor wraps a single
// lyric line so the user can re-stamp it without rewinding. Pass null
// to either bound (or call clipUnloop) to disable.
function clipLoop(start, end) {
  const s = Math.max(0, Number(start) || 0)
  const e = Math.max(s + 0.2, Number(end) || s + 0.2)
  clipLoopStart.value = s
  clipLoopEnd.value = e
  // Jump the playhead in immediately so the user hears the loop start.
  seek(s)
  if (!isPlaying.value) play()
}

function clipUnloop() {
  clipLoopStart.value = null
  clipLoopEnd.value = null
}

function setVolume(v) {
  const clamped = Math.max(0, Math.min(1, v))
  volume.value = clamped
  applyVolume()
  try {
    localStorage.setItem(VOLUME_KEY, String(clamped))
  } catch {
    // ignore
  }
  if (clamped > 0 && isMuted.value) {
    isMuted.value = false
    if (audio) audio.muted = false
  }
}

function toggleMute() {
  isMuted.value = !isMuted.value
  if (audio) audio.muted = isMuted.value
}

function nextIndex() {
  if (playlist.value.length === 0) return -1
  if (shuffle.value) {
    if (shuffleOrder.length !== playlist.value.length) buildShuffleOrder()
    const nextPos = (shufflePos + 1) % shuffleOrder.length
    return shuffleOrder[nextPos]
  }
  const i = currentIndex.value + 1
  if (i >= playlist.value.length) {
    return repeatMode.value === 'all' ? 0 : -1
  }
  return i
}

function prevIndex() {
  if (playlist.value.length === 0) return -1
  if (shuffle.value) {
    if (shuffleOrder.length !== playlist.value.length) buildShuffleOrder()
    const prevPos = (shufflePos - 1 + shuffleOrder.length) % shuffleOrder.length
    return shuffleOrder[prevPos]
  }
  const i = currentIndex.value - 1
  if (i < 0) {
    return repeatMode.value === 'all' ? playlist.value.length - 1 : 0
  }
  return i
}

const YT_ID = /^[A-Za-z0-9_-]{11}$/

function videoIdOf(track) {
  const id = track && (track.video_id || track.song_id)
  return typeof id === 'string' && YT_ID.test(id) ? id : ''
}

function setAutoplayRadio(on) {
  autoplayRadio.value = !!on
  try {
    localStorage.setItem(AUTOPLAY_KEY, on ? '1' : '0')
  } catch {
    // ignore
  }
}

// Append the endless mix for `seed` and keep playing. Returns false when
// there is nothing to extend with (offline, no videoId, already tried).
// Fetching a station is a real round trip, and the user keeps clicking while
// it runs. Every one of these captures playGen first and drops its result if
// the queue moved on, so a late answer can never hijack what is playing now.
async function extendWithRadio() {
  if (!autoplayRadio.value) return false
  const id = videoIdOf(currentTrack.value)
  if (!id || radioSeed === id) return false
  radioSeed = id
  const gen = playGen
  try {
    const res = await API.getRadio(id)
    const songs = (res.data && res.data.songs) || []
    if (!songs.length || gen !== playGen) return gen !== playGen
    const at = playlist.value.length
    playlist.value = [...playlist.value, ...songs.map(trackFromSong)]
    if (shuffle.value) buildShuffleOrder()
    playAt(at)
    return true
  } catch {
    return false
  }
}

/** Replace the queue with a station built around one song. */
async function startRadio(song) {
  const seed = song && (song.video_id || song.song_id)
  if (!seed || !YT_ID.test(seed)) return false
  radioSeed = seed
  setPlaylist([trackFromSong(song)], { startIndex: 0 })
  const gen = playGen
  try {
    const res = await API.getRadio(seed)
    const songs = (res.data && res.data.songs) || []
    if (gen !== playGen) return false // the user started something else
    if (songs.length) playlist.value = [...playlist.value, ...songs.map(trackFromSong)]
    if (shuffle.value) buildShuffleOrder()
    return songs.length > 0
  } catch {
    return false
  }
}

function next() {
  const i = nextIndex()
  if (i < 0) {
    const gen = playGen
    extendWithRadio().then((extended) => {
      // Only stop if nothing else took over while the station loaded.
      if (!extended && gen === playGen) pause()
    })
    return
  }
  playAt(i)
}

function prev() {
  const a = ensureAudio()
  if (a.currentTime > 3) {
    seek(0)
    return
  }
  const i = prevIndex()
  if (i < 0) return
  playAt(i)
}

function onEnded() {
  if (repeatMode.value === 'one') {
    seek(0)
    if (audio) audio.play().catch(() => {})
    return
  }
  // The lyrics sync editor sets this flag: when on, just stop at the
  // end instead of yanking the user to the next song mid-sync.
  if (noAutoAdvance.value) {
    return
  }
  next()
}

function setRepeat(mode) {
  if (!['off', 'all', 'one'].includes(mode)) return
  repeatMode.value = mode
  try {
    localStorage.setItem(REPEAT_KEY, mode)
  } catch {
    // The choice just will not survive a restart.
  }
}

function cycleRepeat() {
  const order = ['off', 'all', 'one']
  const i = order.indexOf(repeatMode.value)
  setRepeat(order[(i + 1) % order.length])
}

function setShuffle(v) {
  shuffle.value = !!v
  if (shuffle.value) buildShuffleOrder()
  try {
    localStorage.setItem(SHUFFLE_KEY, shuffle.value ? '1' : '0')
  } catch {
    // As above.
  }
}

function toggleShuffle() {
  setShuffle(!shuffle.value)
}

const currentTrack = computed(() =>
  currentIndex.value >= 0 && currentIndex.value < playlist.value.length
    ? playlist.value[currentIndex.value]
    : null
)

const progressPct = computed(() =>
  duration.value > 0 ? (currentTime.value / duration.value) * 100 : 0
)

// --- Global keyboard shortcuts (installed once) ---
let keyboardInstalled = false
function isTypingTarget(el) {
  if (!el) return false
  const tag = el.tagName
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    el.isContentEditable
  )
}

function installKeyboardShortcuts() {
  if (keyboardInstalled || typeof window === 'undefined') return
  keyboardInstalled = true
  window.addEventListener('keydown', (e) => {
    // A focused widget (track list, menu, dialog, slider) already handled it.
    if (e.defaultPrevented) return
    // Never hijack typing in inputs/textareas or with modifier combos.
    if (isTypingTarget(e.target) || e.metaKey || e.ctrlKey || e.altKey) return
    // While the lyrics-sync editor is open the global Space/Arrow
    // shortcuts compete with the editor's own keyboard contract
    // (Space = stamp, ↑/↓ = move active line). The noAutoAdvance flag
    // is a perfectly good proxy for "editor is open" so we use that
    // here to defer to the editor.
    if (noAutoAdvance.value) return
    if (playlist.value.length === 0 && e.code !== 'Space') return

    switch (e.code) {
      case 'Space':
        if (playlist.value.length === 0) return
        e.preventDefault()
        toggle()
        break
      case 'ArrowRight':
        // Shift = next track, plain = seek +10s
        if (e.shiftKey) {
          e.preventDefault()
          next()
        } else {
          e.preventDefault()
          seek((currentTime.value || 0) + 10)
        }
        break
      case 'ArrowLeft':
        if (e.shiftKey) {
          e.preventDefault()
          prev()
        } else {
          e.preventDefault()
          seek((currentTime.value || 0) - 10)
        }
        break
      case 'MediaTrackNext':
        e.preventDefault()
        mediaCommand('next')
        break
      case 'MediaTrackPrevious':
        e.preventDefault()
        mediaCommand('prev')
        break
      case 'MediaPlayPause':
        e.preventDefault()
        mediaCommand('toggle')
        break
      case 'ArrowUp':
        e.preventDefault()
        setVolume(Math.min(1, volume.value + 0.05))
        break
      case 'ArrowDown':
        e.preventDefault()
        setVolume(Math.max(0, volume.value - 0.05))
        break
      case 'KeyM':
        e.preventDefault()
        toggleMute()
        break
      case 'KeyN':
        e.preventDefault()
        next()
        break
      case 'KeyP':
        e.preventDefault()
        prev()
        break
      case 'KeyS':
        e.preventDefault()
        toggleShuffle()
        break
      case 'KeyR':
        e.preventDefault()
        cycleRepeat()
        break
      default:
        break
    }
  })
}

// Install immediately when this module is first used in the browser.
installKeyboardShortcuts()

export function formatTime(seconds) {
  if (!isFinite(seconds) || seconds < 0) return '0:00'
  const total = Math.floor(seconds)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function trackInfoFromFile(file) {
  return trackFromFile(file)
}

export function songToTrack(song) {
  return trackFromSong(song)
}

export function usePlayer() {
  return {
    playlist,
    currentIndex,
    currentTrack,
    isPlaying,
    isBuffering,
    currentTime,
    duration,
    progressPct,
    volume,
    isMuted,
    repeatMode,
    shuffle,
    // lyrics
    lyricsLines,
    lyricsPlain,
    lyricsLoading,
    activeLyricIndex,
    lyricsOffset,
    lyricVersionIndex,
    lyricVersionCount,
    seekToLyric,
    refreshLyrics,
    adjustLyricsOffset,
    resetLyricsOffset,
    saveLyricsOffset,
    switchLyricVersion,
    // playback
    setPlaylist,
    restoreSession,
    playStreamSongs,
    downloadTrack,
    enqueue,
    enqueueNext,
    removeFromQueue,
    clearUpcoming,
    moveInQueue,
    mediaCommand,
    playAt,
    play,
    pause,
    toggle,
    seek,
    seekRatio,
    setVolume,
    toggleMute,
    next,
    prev,
    setRepeat,
    cycleRepeat,
    setShuffle,
    toggleShuffle,
    // autoplay / radio
    autoplayRadio,
    setAutoplayRadio,
    startRadio,
    // sync-editor extras
    playbackRate,
    setPlaybackRate,
    clipLoopStart,
    clipLoopEnd,
    clipLoop,
    clipUnloop,
    noAutoAdvance,
  }
}
