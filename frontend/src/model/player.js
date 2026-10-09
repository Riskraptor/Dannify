import { engine, ensureAudio } from '/src/model/player/decks'
import { installKeyboardShortcuts } from '/src/model/player/keyboard'
import {
  activeLyricIndex,
  adjustLyricsOffset,
  lyricVersionCount,
  lyricVersionIndex,
  lyricsLines,
  lyricsLoading,
  lyricsOffset,
  lyricsPlain,
  refreshLyrics,
  resetLyricsOffset,
  saveLyricsOffset,
  seekToLyric,
  switchLyricVersion,
} from '/src/model/player/lyrics'
import { trackFromFile, trackFromSong } from '/src/model/player/makeTrack'
import { mediaCommand } from '/src/model/player/mediaSession'
import {
  balance,
  crossfade,
  deleteEqPreset,
  eq,
  eqCurve,
  eqUserPresets,
  gapless,
  keepPitch,
  mono,
  restoreSpeed,
  saveEqPreset,
  setBalance,
  setCrossfade,
  setEqBand,
  setEqEnabled,
  setEqPreamp,
  setEqPreset,
  setGapless,
  setKeepPitch,
  setMono,
  setSpeed,
  spectrum,
  spectrumInfo,
  speed,
} from '/src/model/player/mixer'
import {
  cycleRepeat,
  setRepeat,
  setShuffle,
  toggleShuffle,
  upcoming,
} from '/src/model/player/order'
import {
  clearUpcoming,
  downloadTrack,
  enqueue,
  enqueueNext,
  moveInQueue,
  moveUpcoming,
  playStreamSongs,
  removeFromQueue,
  setPlaylist,
} from '/src/model/player/queue'
import { autoplayRadio, setAutoplayRadio, startRadio } from '/src/model/player/radio'
import { restoreSession } from '/src/model/player/session'
import {
  cancelSleep,
  setSleepAfterTrack,
  setSleepTimer,
  sleepEndsAt,
  sleepMode,
} from '/src/model/player/sleep'
import {
  normalizeLoudness,
  setNormalizeLoudness,
  setVolumeLevel,
  volumeLevel,
} from '/src/model/player/sound'
import {
  clipLoopEnd,
  clipLoopStart,
  currentIndex,
  currentTime,
  currentTrack,
  duration,
  isBuffering,
  isMuted,
  isPlaying,
  noAutoAdvance,
  playbackRate,
  playlist,
  progressPct,
  repeatMode,
  shuffle,
  volume,
} from '/src/model/player/state'
import {
  clipLoop,
  clipUnloop,
  next,
  pause,
  play,
  playAt,
  prev,
  seek,
  seekRatio,
  setPlaybackRate,
  setVolume,
  toggle,
  toggleMute,
} from '/src/model/player/transport'
// The music player: one queue and one transport for the whole app.
//
// This is its public face; the parts live in ./player/:
//   state         the queue, the playing track, the transport's state
//   makeTrack     songs, rows and file paths as queue tracks
//   queue         queue edits (replace, play next, add, remove, move)
//   order         shuffle and repeat: what plays next and what came before
//   transport     play, pause, seek, next, previous, and a change of track
//   decks         the audio elements, crossfade and gapless changes
//   sound/mixer   levelled loudness, volume level; equalizer, speed, balance
//   recovery      tracks that will not play, and details a track came without
//   lyrics        synced lyrics for the track in the player
//   mediaSession  the system's media controls
//   session       the queue kept between runs (format in sessionFormat)
//   radio, sleep, keyboard


// Installed as soon as the player is first used in the browser.
installKeyboardShortcuts()

export { VOLUME_LEVELS } from '/src/model/player/sound'

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
    upcoming,
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
    moveUpcoming,
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
    normalizeLoudness,
    eqUserPresets,
    saveEqPreset,
    deleteEqPreset,
    setEqPreamp,
    speed,
    setSpeed,
    keepPitch,
    setKeepPitch,
    restoreSpeed,
    spectrum,
    spectrumInfo,
    volumeLevel,
    setVolumeLevel,
    balance,
    setBalance,
    mono,
    setMono,
    eqCurve,
    setNormalizeLoudness,
    startRadio,
    // the sound engine
    hasEngine: () => !!(ensureAudio() && engine),
    crossfade,
    setCrossfade,
    gapless,
    setGapless,
    eq,
    setEqEnabled,
    setEqPreset,
    setEqBand,
    // sleep timer
    sleepMode,
    sleepEndsAt,
    setSleepTimer,
    setSleepAfterTrack,
    cancelSleep,
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
