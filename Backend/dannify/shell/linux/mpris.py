"""MPRIS: how Linux desktops see a media player.

Registering on the session bus is what puts Dannify in GNOME's and KDE's
media panels and on the lock screen, and what makes the keyboard's media
keys reach it: the desktop sends them to whichever MPRIS player is active.
Commands are handed to the page exactly like the tray's (window.__dannifyMedia).
"""

from __future__ import annotations

import re
import time
from typing import Callable, Optional

from loguru import logger

from .gtk import Gio, GLib

_PATH = '/org/mpris/MediaPlayer2'
_ROOT = 'org.mpris.MediaPlayer2'
_PLAYER = 'org.mpris.MediaPlayer2.Player'

_XML = """
<node>
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/>
    <method name="Quit"/>
    <property name="CanQuit" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Next"/>
    <method name="Previous"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <method name="Play"/>
    <method name="Seek"><arg direction="in" name="Offset" type="x"/></method>
    <method name="SetPosition">
      <arg direction="in" name="TrackId" type="o"/>
      <arg direction="in" name="Position" type="x"/>
    </method>
    <method name="OpenUri"><arg direction="in" name="Uri" type="s"/></method>
    <signal name="Seeked"><arg name="Position" type="x"/></signal>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="Rate" type="d" access="read"/>
    <property name="Metadata" type="a{sv}" access="read"/>
    <property name="Volume" type="d" access="read"/>
    <property name="Position" type="x" access="read"/>
    <property name="MinimumRate" type="d" access="read"/>
    <property name="MaximumRate" type="d" access="read"/>
    <property name="CanGoNext" type="b" access="read"/>
    <property name="CanGoPrevious" type="b" access="read"/>
    <property name="CanPlay" type="b" access="read"/>
    <property name="CanPause" type="b" access="read"/>
    <property name="CanSeek" type="b" access="read"/>
    <property name="CanControl" type="b" access="read"/>
  </interface>
</node>
"""


class Mpris:
    def __init__(self, on_command: Callable[[str], None], on_raise: Callable[[], None],
                 on_quit: Callable[[], None], name_suffix: str = '') -> None:
        self._on_command = on_command
        self._on_raise = on_raise
        self._on_quit = on_quit
        self._suffix = re.sub(r'[^A-Za-z0-9_]', '', name_suffix)
        self._conn: Optional[Gio.DBusConnection] = None
        self._owner = 0
        self._ids: list[int] = []
        self.state = {'playing': False, 'has_track': False, 'title': '', 'artist': '',
                      'album': '', 'art': '', 'duration': 0.0, 'position': 0.0, 'key': ''}
        self._position_at = time.monotonic()

    # --- the bus -------------------------------------------------------------
    def start(self) -> None:
        """GTK thread. Quietly does nothing without a session bus."""

        name = 'org.mpris.MediaPlayer2.dannify' + (f'.instance{self._suffix}' if self._suffix else '')
        try:
            self._owner = Gio.bus_own_name(
                Gio.BusType.SESSION, name, Gio.BusNameOwnerFlags.NONE,
                self._on_bus, None, None,
            )
        except Exception:
            logger.opt(exception=True).info('no session bus: media keys will not reach Dannify')

    def _on_bus(self, conn, _name) -> None:  # noqa: ANN001
        self._conn = conn
        info = Gio.DBusNodeInfo.new_for_xml(_XML)
        for iface in info.interfaces:
            self._ids.append(conn.register_object(_PATH, iface, self._call, self._get, None))

    def stop(self) -> None:
        if self._conn is not None:
            for reg in self._ids:
                try:
                    self._conn.unregister_object(reg)
                except Exception:
                    pass
        if self._owner:
            Gio.bus_unown_name(self._owner)
        self._owner, self._ids, self._conn = 0, [], None

    # --- incoming ------------------------------------------------------------
    def _call(self, conn, sender, path, iface, method, params, invocation) -> None:  # noqa: ANN001
        args = params.unpack() if params is not None else ()
        simple = {'Next': 'next', 'Previous': 'prev', 'Pause': 'pause', 'Play': 'play',
                  'PlayPause': 'toggle', 'Stop': 'pause'}
        if method in simple:
            self._on_command(simple[method])
        elif method == 'Raise':
            self._on_raise()
        elif method == 'Quit':
            self._on_quit()
        elif method == 'Seek' and args:
            self._seek_to(self.position() + args[0] / 1e6)
        elif method == 'SetPosition' and len(args) == 2 and args[0] == self._track_id():
            self._seek_to(args[1] / 1e6)
        invocation.return_value(None)

    def _seek_to(self, seconds: float) -> None:
        duration = self.state['duration'] or 0
        seconds = max(0.0, min(seconds, duration)) if duration else max(0.0, seconds)
        self._on_command(f'seek:{seconds:.2f}')
        self.state['position'] = seconds
        self._position_at = time.monotonic()
        if self._conn is not None:
            self._conn.emit_signal(None, _PATH, _PLAYER, 'Seeked', GLib.Variant('(x)', (int(seconds * 1e6),)))

    def _get(self, conn, sender, path, iface, prop):  # noqa: ANN001
        values = self._root() if iface == _ROOT else self._player()
        return values.get(prop)

    # --- what it reports -----------------------------------------------------
    def _root(self) -> dict:
        return {
            'CanQuit': GLib.Variant('b', True),
            'CanRaise': GLib.Variant('b', True),
            'HasTrackList': GLib.Variant('b', False),
            'Identity': GLib.Variant('s', 'Dannify'),
            'DesktopEntry': GLib.Variant('s', 'dannify'),
            'SupportedUriSchemes': GLib.Variant('as', []),
            'SupportedMimeTypes': GLib.Variant('as', []),
        }

    def position(self) -> float:
        pos = self.state['position']
        if self.state['playing']:
            pos += time.monotonic() - self._position_at
        duration = self.state['duration']
        return min(pos, duration) if duration else pos

    def _track_id(self) -> str:
        key = re.sub(r'[^A-Za-z0-9_]', '_', self.state['key'] or 'none')[:120]
        return f'/org/dannify/track/t{key}'

    def _metadata(self) -> GLib.Variant:
        s = self.state
        if not s['has_track']:
            return GLib.Variant('a{sv}', {'mpris:trackid': GLib.Variant('o', '/org/mpris/MediaPlayer2/TrackList/NoTrack')})
        meta = {
            'mpris:trackid': GLib.Variant('o', self._track_id()),
            'xesam:title': GLib.Variant('s', s['title']),
            'xesam:artist': GLib.Variant('as', [s['artist']] if s['artist'] else []),
            'xesam:album': GLib.Variant('s', s['album']),
        }
        if s['duration']:
            meta['mpris:length'] = GLib.Variant('x', int(s['duration'] * 1e6))
        if s['art']:
            meta['mpris:artUrl'] = GLib.Variant('s', s['art'])
        return GLib.Variant('a{sv}', meta)

    def _player(self) -> dict:
        s = self.state
        has = s['has_track']
        return {
            'PlaybackStatus': GLib.Variant('s', 'Playing' if s['playing'] else 'Paused' if has else 'Stopped'),
            'Rate': GLib.Variant('d', 1.0),
            'MinimumRate': GLib.Variant('d', 1.0),
            'MaximumRate': GLib.Variant('d', 1.0),
            'Metadata': self._metadata(),
            'Volume': GLib.Variant('d', 1.0),
            'Position': GLib.Variant('x', int(self.position() * 1e6)),
            'CanGoNext': GLib.Variant('b', has),
            'CanGoPrevious': GLib.Variant('b', has),
            'CanPlay': GLib.Variant('b', has),
            'CanPause': GLib.Variant('b', has),
            'CanSeek': GLib.Variant('b', has and bool(s['duration'])),
            'CanControl': GLib.Variant('b', True),
        }

    def update(self, **changes) -> None:
        """GTK thread. New playback state; tells the desktop what changed."""

        before = self._player()
        if 'position' in changes:
            self._position_at = time.monotonic()
        self.state.update(changes)
        after = self._player()
        changed = {k: v for k, v in after.items() if k != 'Position' and before.get(k) != v}
        if not changed or self._conn is None:
            return
        try:
            self._conn.emit_signal(
                None, _PATH, 'org.freedesktop.DBus.Properties', 'PropertiesChanged',
                GLib.Variant('(sa{sv}as)', (_PLAYER, changed, [])),
            )
        except Exception:
            logger.opt(exception=True).debug('could not tell the desktop what is playing')
