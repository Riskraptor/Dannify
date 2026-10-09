"""Now Playing: how macOS sees a media player.

What is set here is what Control Center, the menu bar's Now Playing item and
the lock screen show, and registering for the remote commands is what makes
the keyboard's play, next and previous keys (and AirPods, and the Touch Bar)
reach Dannify. Commands go to the page exactly like the tray's
(window.__dannifyMedia).
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from loguru import logger

from .cocoa import AppKit, Foundation

# MPRemoteCommandHandlerStatus / MPNowPlayingPlaybackState
_SUCCESS, _NO_SUCH_CONTENT = 0, 100
_PLAYING, _PAUSED, _STOPPED = 1, 2, 3


class NowPlaying:
    def __init__(self, on_command: Callable[[str], None]) -> None:
        self._on_command = on_command
        self._mp = None
        self._targets: list[tuple[object, object]] = []
        self._artwork = None
        self.state = {'playing': False, 'has_track': False, 'title': '', 'artist': '',
                      'album': '', 'duration': 0.0, 'position': 0.0, 'key': ''}
        self._position_at = time.monotonic()

    def start(self) -> None:
        """Main thread."""

        try:
            import MediaPlayer
        except ImportError:
            logger.info('Now Playing is not available (no MediaPlayer bindings)')
            return
        self._mp = MediaPlayer
        center = MediaPlayer.MPRemoteCommandCenter.sharedCommandCenter()
        pairs = (
            (center.togglePlayPauseCommand(), 'toggle'),
            (center.playCommand(), 'play'),
            (center.pauseCommand(), 'pause'),
            (center.stopCommand(), 'pause'),
            (center.nextTrackCommand(), 'next'),
            (center.previousTrackCommand(), 'prev'),
        )
        for command, name in pairs:
            command.setEnabled_(True)
            self._targets.append((command, command.addTargetWithHandler_(self._handler(name))))
        seek = center.changePlaybackPositionCommand()
        seek.setEnabled_(True)
        self._targets.append((seek, seek.addTargetWithHandler_(self._seek)))
        # Skipping by fifteen seconds is for podcasts; music players show
        # next and previous instead.
        for unused in (center.skipForwardCommand(), center.skipBackwardCommand()):
            unused.setEnabled_(False)

    def _handler(self, name: str):
        def handle(_event) -> int:  # noqa: ANN001
            if not self.state['has_track'] and name not in ('play', 'toggle'):
                return _NO_SUCH_CONTENT
            self._on_command(name)
            return _SUCCESS
        return handle

    def _seek(self, event) -> int:  # noqa: ANN001
        try:
            seconds = max(0.0, float(event.positionTime()))
        except Exception:
            return _NO_SUCH_CONTENT
        self._on_command(f'seek:{seconds:.3f}')
        self.update(position=seconds)
        return _SUCCESS

    def update(self, **changes) -> None:
        """Main thread. Anything that changed: the panel follows."""

        if self._mp is None:
            return
        old = dict(self.state)
        if 'position' not in changes:
            if changes.get('key', old['key']) != old['key']:
                changes['position'] = 0.0
            elif old['playing']:
                changes['position'] = old['position'] + (time.monotonic() - self._position_at)
        self.state.update(changes)
        if 'position' in changes:
            self._position_at = time.monotonic()
        if self.state['key'] != old['key']:
            self._artwork = None
        self._publish()

    def set_art(self, key: str, data: Optional[bytes]) -> None:
        """Main thread. The cover, once it has been fetched."""

        if self._mp is None or key != self.state['key'] or not data:
            return
        try:
            image = AppKit.NSImage.alloc().initWithData_(
                Foundation.NSData.dataWithBytes_length_(data, len(data)))
            if image is None:
                return
            self._artwork = self._mp.MPMediaItemArtwork.alloc().initWithBoundsSize_requestHandler_(
                image.size(), lambda _size: image)
        except Exception:
            logger.opt(exception=True).debug('no cover for Now Playing')
            return
        self._publish()

    def _publish(self) -> None:
        mp, s = self._mp, self.state
        center = mp.MPNowPlayingInfoCenter.defaultCenter()
        if not s['has_track']:
            center.setNowPlayingInfo_(None)
            center.setPlaybackState_(_STOPPED)
            return
        info = {
            mp.MPMediaItemPropertyTitle: s['title'],
            mp.MPMediaItemPropertyArtist: s['artist'],
            mp.MPMediaItemPropertyAlbumTitle: s['album'],
            mp.MPNowPlayingInfoPropertyElapsedPlaybackTime: float(s['position']),
            mp.MPNowPlayingInfoPropertyPlaybackRate: 1.0 if s['playing'] else 0.0,
            mp.MPNowPlayingInfoPropertyMediaType: 1,  # MPNowPlayingInfoMediaTypeAudio
        }
        if s['duration'] > 0:
            info[mp.MPMediaItemPropertyPlaybackDuration] = float(s['duration'])
        if self._artwork is not None:
            info[mp.MPMediaItemPropertyArtwork] = self._artwork
        center.setNowPlayingInfo_(info)
        center.setPlaybackState_(_PLAYING if s['playing'] else _PAUSED)

    def stop(self) -> None:
        if self._mp is None:
            return
        for command, token in self._targets:
            try:
                command.removeTarget_(token)
            except Exception:
                pass
        self._targets = []
        try:
            center = self._mp.MPNowPlayingInfoCenter.defaultCenter()
            center.setNowPlayingInfo_(None)
            center.setPlaybackState_(_STOPPED)
        except Exception:
            pass
