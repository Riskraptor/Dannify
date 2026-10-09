import API from '/src/model/api'
import { useUi } from '/src/model/ui'
import { rememberPlayed } from '/src/model/recent'
import { notePlayed } from '/src/model/support'
import {
  GAPLESS_OVERLAP,
  MANUAL_FADE,
  audio,
  cancelTransition,
  deck,
  elementTime,
  engine,
  ensureAudio,
  otherDeck,
  retire,
  silenceRetiring,
  takeDeck,
} from '/src/model/player/decks'
import {
  activeLyricIndex,
  loadLyricsForCurrent,
  lyricsLines,
  lyricsPlain,
  prefetchLyrics,
} from '/src/model/player/lyrics'
import { syncMediaSession, syncPositionState } from '/src/model/player/mediaSession'
import { keepPitch } from '/src/model/player/mixer'
import { ensureShuffleOrder, nextIndex, prevIndex } from '/src/model/player/order'
import { extendWithRadio } from '/src/model/player/radio'
import { fillMissingDetails, needsDetails } from '/src/model/player/recovery'
import { saveSession } from '/src/model/player/session'
import { cancelSleep, sleepFading, sleepMode } from '/src/model/player/sleep'
import {
  applyVolume,
  ensureLocalGain,
  ensureStreamDuration,
  gainOfTrack,
  loudnessOf,
  loudnessReady,
  normalizeLoudness,
  noteLoudness,
  trackGain,
} from '/src/model/player/sound'
import {
  VOLUME_KEY,
  bumpPlayGen,
  clipLoopEnd,
  clipLoopStart,
  currentIndex,
  currentTime,
  currentTrack,
  duration,
  frameTime,
  isBuffering,
  isMuted,
  isPlaying,
  noAutoAdvance,
  playGen,
  playbackRate,
  playlist,
  repeatMode,
  setStreamBaseOffset,
  shuffle,
  videoIdOf,
  volume,
} from '/src/model/player/state'

// Playing, pausing, seeking and moving from one track to the next: the
// controls on the play bar and everything a change of track sets going.

const _ui = useUi()
// One-shot guard for the auto-open-lyrics-on-first-play affordance.
let _lyricsAutoOpened = false

// Warm the next stream's cache file (and lyrics) so advancing the queue is
// instant and lyrics are ready before the next track even starts.
let prefetchTimer = null
function prefetchNext() {
  clearTimeout(prefetchTimer)
  prefetchTimer = setTimeout(() => {
    // The track that plays next, which under shuffle is not the next row.
    const nxt = playlist.value[nextIndex()]
    if (!nxt || nxt === currentTrack.value) return
    // What "Up next" shows of it, before it plays.
    if (needsDetails(nxt)) fillMissingDetails(nxt)
    if (nxt.type === 'stream' && nxt.video_id) {
      // prefetch=1 → server transcodes the next track to cache in background.
      // Its loudness comes with it, so it starts at the right level.
      API.getStreamInfo(nxt.video_id, 1)
        .then((res) => {
          const data = (res && res.data) || {}
          if (data.duration > 0 && !(nxt.duration > 0)) nxt.duration = data.duration
          noteLoudness(nxt, data.loudness_db)
        })
        .catch(() => {})
    } else if (nxt.type === 'local') {
      ensureLocalGain(nxt)
    }
    prefetchLyrics(nxt)
  }, 500)
}

// *autoplay* false loads the track and leaves it paused, for a change of
// track the listener did not ask to hear (removing the playing one while
// paused).
// *again*: the same song started over (a retry, its online copy taking over
// from a saved file that went), which is not another listen to record.
export function playAt(index, { autoplay = true, fade = null, again = false } = {}) {
  if (index < 0 || index >= playlist.value.length) return
  ensureAudio()
  cancelTransition()
  const track = playlist.value[index]
  // With the engine, the next song goes on the other deck: the one that was
  // playing fades out by itself (briefly when picked by hand, over the
  // crossfade when it ran out), so a change never cuts or clicks.
  let preloaded = false
  if (engine && deck) {
    const incoming = otherDeck()
    if (incoming) {
      const outgoing = deck
      const playing = !!(outgoing.el.src && !outgoing.el.paused)
      retire(outgoing, fade != null ? fade : playing ? MANUAL_FADE : 0)
      preloaded = incoming.preloaded === track && !!incoming.el.src
      incoming.preloaded = null
      takeDeck(incoming)
      deck.setFade(fade != null && fade > GAPLESS_OVERLAP ? 0 : 1)
    }
  }
  const a = audio
  currentIndex.value = index
  if (shuffle.value) ensureShuffleOrder()
  // Bump the generation token so any in-flight async work (duration/lyrics
  // fetches, the previous stream's media events) from the prior track is
  // ignored: this prevents "wrong audio / wrong metadata" races when the
  // user switches tracks quickly.
  bumpPlayGen()
  // Nothing buffers until it is asked to play.
  isBuffering.value = autoplay && track.type === 'stream'
  setStreamBaseOffset(0)
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
  if (!preloaded) {
    a.src = track.url
    a.currentTime = 0
  }
  // Re-apply playback rate: browsers reset it to 1.0 on src change.
  try {
    a.playbackRate = playbackRate.value
    a.preservesPitch = keepPitch.value
  } catch {
    // ignore
  }
  currentTime.value = 0
  frameTime.value = 0
  duration.value = track.duration || 0
  // Reset lyrics immediately so the old song's lyrics don't linger.
  lyricsLines.value = []
  lyricsPlain.value = null
  activeLyricIndex.value = -1
  // The song's level before its first note (see loudnessCache).
  trackGain.value = gainOfTrack(track)
  track.gain = trackGain.value
  applyVolume(true)
  const info = track.type === 'stream' ? ensureStreamDuration(track) : ensureLocalGain(track)
  if (autoplay) {
    const gen = playGen
    const d = deck
    const begin = () => {
      if (gen !== playGen) return
      trackGain.value = gainOfTrack(track)
      applyVolume(true)
      if (engine) engine.resume()
      a.play().catch(() => {})
      if (d && fade != null && fade > GAPLESS_OVERLAP) d.fadeTo(1, fade)
    }
    // Waiting on the measurement only when it changes something: levelling
    // on, a song YouTube measures, and nothing known about it yet.
    if (normalizeLoudness.value && videoIdOf(track) && loudnessOf(track) === undefined) {
      loudnessReady(track, info, 700).then(begin)
    } else {
      begin()
    }
  }
  loadLyricsForCurrent()
  syncMediaSession()
  if (needsDetails(track)) fillMissingDetails(track)
  if (!again) {
    rememberPlayed(track)
    notePlayed()
    // For whoever keeps a history of listens (the YouTube Music account).
    if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      window.dispatchEvent(new CustomEvent('dannify:played', { detail: track }))
    }
  }
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
  // Warm the next track (stream cache + lyrics) regardless of type.
  prefetchNext()
}

export function play() {
  if (playlist.value.length === 0) return
  const a = ensureAudio()
  if (currentIndex.value < 0) {
    // The head of the play order: the first row, or under shuffle the first
    // of the shuffled order, which is what "Up next" shows.
    playAt(Math.max(0, nextIndex()))
    return
  }
  if (!a.src) {
    a.src = playlist.value[currentIndex.value].url
  }
  // Playing again while the sleep timer fades out means "not yet".
  if (sleepFading) cancelSleep()
  if (engine) engine.resume()
  a.play().catch(() => {})
}

export function pause() {
  if (audio) audio.pause()
  cancelTransition()
  silenceRetiring()
}

export function toggle() {
  if (isPlaying.value) pause()
  else play()
}

export function seek(seconds) {
  const a = ensureAudio()
  // Clamp to the end only once the end is known. A stream still waiting on
  // its length reports 0, and clamping to that sent every seek (+10 s
  // included) back to the start of the song.
  const d = duration.value
  const max = Number.isFinite(d) && d > 0 ? d : Infinity
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
      setStreamBaseOffset(clamped)
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
  frameTime.value = clamped
  // A change near the end was planned from the old position.
  cancelTransition()
  syncPositionState()
}

export function seekRatio(ratio) {
  if (!duration.value) return
  seek(duration.value * Math.max(0, Math.min(1, ratio)))
}

// ─── Playback rate (used by the sync editor for slow-mo syncing) ───
export function setPlaybackRate(rate) {
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
export function clipLoop(start, end) {
  const s = Math.max(0, Number(start) || 0)
  const e = Math.max(s + 0.2, Number(end) || s + 0.2)
  clipLoopStart.value = s
  clipLoopEnd.value = e
  // Jump the playhead in immediately so the user hears the loop start.
  seek(s)
  if (!isPlaying.value) play()
}

export function clipUnloop() {
  clipLoopStart.value = null
  clipLoopEnd.value = null
}

export function setVolume(v) {
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
    if (audio && !engine) audio.muted = false
    applyVolume()
  }
}

export function toggleMute() {
  isMuted.value = !isMuted.value
  if (engine) applyVolume()
  else if (audio) audio.muted = isMuted.value
}

export function next() {
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

export function prev() {
  ensureAudio()
  // Where the song really is: on the fallback stream the element counts from
  // where that stream started, not from the top of the song.
  if (elementTime() > 3) {
    seek(0)
    return
  }
  const i = prevIndex()
  if (i < 0) return
  playAt(i)
}

export function onEnded() {
  // "Stop after this song": it has ended, so stop here.
  if (sleepMode.value === 'track') {
    cancelSleep()
    isPlaying.value = false
    return
  }
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
