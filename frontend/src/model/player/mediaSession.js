import { audio, elementTime } from '/src/model/player/decks'
import { currentTrack, duration, isPlaying } from '/src/model/player/state'
import { next, pause, play, prev, seek, toggle } from '/src/model/player/transport'

// The system's own media controls (the Windows flyout, media keys, a lock
// screen): what they show, and the commands that come back from them.

export function syncMediaSession() {
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
    navigator.mediaSession.setActionHandler('seekbackward', (d) => seek(elementTime() - ((d && d.seekOffset) || 10)))
    navigator.mediaSession.setActionHandler('seekforward', (d) => seek(elementTime() + ((d && d.seekOffset) || 10)))
    navigator.mediaSession.setActionHandler('stop', () => pause())
  } catch {
    // MediaSession not fully supported: ignore.
  }
  syncPositionState()
}

// Where the song is and how long it is, for the timeline in Windows' media
// flyout. It had none: the flyout showed the title with no progress at all.
export function syncPositionState() {
  try {
    const d = duration.value
    if (typeof navigator === 'undefined' || !navigator.mediaSession) return
    if (typeof navigator.mediaSession.setPositionState !== 'function') return
    if (!(d > 0) || !Number.isFinite(d)) return
    navigator.mediaSession.setPositionState({
      duration: d,
      playbackRate: (audio && audio.playbackRate) || 1,
      position: Math.max(0, Math.min(d, elementTime())),
    })
  } catch {
    // a position the browser will not take: the flyout just has no timeline
  }
}

// Media keys can reach us twice (OS media session + keydown while focused).
// Collapse identical commands that land within a few hundred milliseconds.
let _lastMedia = { cmd: '', at: 0 }
export function mediaCommand(cmd) {
  const now = performance.now()
  if (_lastMedia.cmd === cmd && now - _lastMedia.at < 350) return
  _lastMedia = { cmd, at: now }
  if (cmd === 'play') play()
  else if (cmd === 'pause') pause()
  else if (cmd === 'toggle') toggle()
  else if (cmd === 'next') next()
  else if (cmd === 'prev') prev()
}
