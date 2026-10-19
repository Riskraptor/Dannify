"""Showing what is playing on Discord, for whoever turns it on.

Discord's desktop app takes a "Rich Presence" from programs on the same
computer, over a local pipe (Windows) or socket (Linux, macOS): nothing goes
over the network from here. Dannify tells it the song playing, who it is by,
the album, its artwork and how far in it is, and Discord shows that on the
person's profile as "Listening to Dannify", with a progress bar and a button
for friends to play the song too.

It is off until it is turned on in Settings: it tells other people what you
are listening to. With Discord not running nothing happens, and it is looked
for again now and then, so opening Discord later picks the song up. A pause
takes the song off after a few seconds. Closing Dannify closes the pipe, and
Discord takes it off at once.
"""

from __future__ import annotations

import json
import os
import re
import socket
import struct
import sys
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

# The Dannify application on Discord's developer portal: it is what makes the
# profile say "Dannify". Not a secret; every copy carries it.
CLIENT_ID = '1561608466261483562'
# The picture for a song without artwork Discord can reach, and the small
# badge on the artwork otherwise. Discord fetches it itself: it must be public.
LOGO = 'https://raw.githubusercontent.com/Riskraptor/Dannify/main/frontend/public/android-chrome-512x512.png'

_FILE = 'discord.json'

# The kinds of frame in Discord's local protocol.
HANDSHAKE, FRAME, CLOSE, PING, PONG = 0, 1, 2, 3, 4
# "Listening to", rather than "Playing".
LISTENING = 2

# Discord takes five updates in twenty seconds; one every four stays clear of
# that however fast songs are skipped. The last one asked for always goes.
MIN_GAP = 4.0
# How often to look for Discord while it is not running.
RETRY = 15.0
# A pause this long takes the song off the profile; a shorter one does not
# make it flicker.
PAUSE_GRACE = 10.0
# Reading from Discord's socket (Linux, macOS).
_TIMEOUT = 10.0
# What Discord takes: texts of 2 to 128 characters, buttons up to 32.
TEXT_MOST = 128
LABEL_MOST = 32
IMAGE_URL_MOST = 256
_FRAME_MOST = 1 << 20
_YT_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
# A Google picture's size, at the end of its address ("=w120-h120-l90-rj").
_GOOGLE_SIZE = re.compile(r'=(?:w\d+-h\d+|s\d+)[^/?#=]*$')
_COVERS_MOST = 500


class Closed(OSError):
    """Discord closed the connection, or went away."""


class Refused(Closed):
    """Discord turned the connection down (an unknown application, say)."""


# ---------------------------------------------------------------------------
# Talking to Discord
# ---------------------------------------------------------------------------


def encode(op: int, payload: dict[str, Any]) -> bytes:
    """One frame: its kind and length, little-endian, then the JSON."""

    data = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return struct.pack('<II', op, len(data)) + data


class _Pipe:
    """Discord's named pipe on Windows."""

    def __init__(self, path: str) -> None:
        self._file = open(path, 'r+b', buffering=0)  # noqa: SIM115

    def send(self, data: bytes) -> None:
        view = memoryview(data)
        while view:
            done = self._file.write(view)
            if not done:
                raise Closed('Discord stopped reading')
            view = view[done:]

    def recv(self, size: int) -> bytes:
        return self._file.read(size) or b''

    def close(self) -> None:
        self._file.close()


class _Socket:
    """Discord's socket on Linux and macOS."""

    def __init__(self, path: str) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined]
        sock.settimeout(_TIMEOUT)
        try:
            sock.connect(path)
        except OSError:
            sock.close()
            raise
        self._sock = sock

    def send(self, data: bytes) -> None:
        self._sock.sendall(data)

    def recv(self, size: int) -> bytes:
        return self._sock.recv(size)

    def close(self) -> None:
        self._sock.close()


class Channel:
    """An open connection to Discord: frames out, frames in."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def send(self, op: int, payload: dict[str, Any]) -> None:
        self._raw.send(encode(op, payload))

    def recv(self) -> tuple[int, dict[str, Any]]:
        op, size = struct.unpack('<II', self._exactly(8))
        if size > _FRAME_MOST:
            raise Closed('a frame too large to be from Discord')
        body = self._exactly(size)
        try:
            data = json.loads(body.decode('utf-8')) if body else {}
        except ValueError as exc:
            raise Closed('not what Discord sends') from exc
        return op, data if isinstance(data, dict) else {}

    def _exactly(self, size: int) -> bytes:
        got = b''
        while len(got) < size:
            part = self._raw.recv(size - len(got))
            if not part:
                raise Closed('Discord went away')
            got += part
        return got

    def close(self) -> None:
        try:
            self._raw.close()
        except OSError:
            pass


def candidates() -> list[str]:
    """Where a running Discord listens, most likely first.

    Windows has one place. Elsewhere the socket is in the runtime or temporary
    folder, or inside the sandbox of a Flatpak or Snap Discord.
    """

    if sys.platform == 'win32':
        return [rf'\\.\pipe\discord-ipc-{i}' for i in range(10)]
    bases: list[str] = []
    for var in ('XDG_RUNTIME_DIR', 'TMPDIR', 'TMP', 'TEMP'):
        value = os.environ.get(var)
        if value and value not in bases:
            bases.append(value)
    if '/tmp' not in bases:
        bases.append('/tmp')
    folders: list[str] = []
    for base in bases:
        for sub in (
            '', 'app/com.discordapp.Discord', 'app/com.discordapp.DiscordCanary',
            'snap.discord', 'snap.discord-canary', '.flatpak/dev.vencord.Vesktop/xdg-run',
        ):
            folder = os.path.join(base, sub) if sub else base
            if folder not in folders:
                folders.append(folder)
    return [os.path.join(folder, f'discord-ipc-{i}') for i in range(10) for folder in folders]


def open_channel() -> Optional[Channel]:
    """A connection to the Discord running here, or None when there is none."""

    windows = sys.platform == 'win32'
    for path in candidates():
        if not windows and not os.path.exists(path):
            continue
        try:
            raw = _Pipe(path) if windows else _Socket(path)
        except OSError:
            continue
        return Channel(raw)
    return None


def handshake(channel: Channel) -> None:
    """Say which application this is; Discord answers READY, or closes."""

    channel.send(HANDSHAKE, {'v': 1, 'client_id': CLIENT_ID})
    op, data = channel.recv()
    if op == CLOSE:
        raise Refused(f"Discord said no: {data.get('code')} {data.get('message')}")
    if op != FRAME or data.get('evt') != 'READY':
        raise Closed('Discord did not say it was ready')


def set_activity(channel: Channel, activity: Optional[dict[str, Any]]) -> str:
    """Show *activity* on the profile, or nothing when it is None.

    Returns Discord's complaint when it would not take it, '' when it did.
    """

    nonce = uuid.uuid4().hex
    args: dict[str, Any] = {'pid': os.getpid()}
    if activity:
        args['activity'] = activity
    channel.send(FRAME, {'cmd': 'SET_ACTIVITY', 'args': args, 'nonce': nonce})
    while True:
        op, data = channel.recv()
        if op == PING:
            channel.send(PONG, data)
            continue
        if op == CLOSE:
            raise Closed(f"Discord closed: {data.get('code')} {data.get('message')}")
        if op == FRAME and data.get('nonce') == nonce:
            if data.get('evt') == 'ERROR':
                return str((data.get('data') or {}).get('message') or 'refused')
            return ''


# ---------------------------------------------------------------------------
# What the profile shows
# ---------------------------------------------------------------------------


def _text(value: Any, most: int = TEXT_MOST) -> str:
    text = ' '.join(str(value or '').split())
    if len(text) > most:
        text = text[: most - 1].rstrip() + '…'
    # Discord turns down a text of one character.
    if len(text) == 1:
        text += '\u200b'
    return text


def picture(url: Any) -> str:
    """*url* as artwork Discord can fetch, at a size worth showing, or ''."""

    url = str(url or '').strip()
    if not url.startswith('https://'):
        return ''
    if 'googleusercontent.com' in url or 'ggpht.com' in url:
        url = _GOOGLE_SIZE.sub('=w544-h544-l90-rj', url)
    return url if len(url) <= IMAGE_URL_MOST else ''


def activity_for(song: Optional[dict[str, Any]], cover: str = '') -> Optional[dict[str, Any]]:
    """What the profile shows while *song* plays; None when nothing is.

    *song* is what the window said (see clean), *cover* artwork found for it
    here when the window had none Discord can reach.
    """

    if not song or not song.get('playing'):
        return None
    title = _text(song.get('title'))
    if not title:
        return None
    activity: dict[str, Any] = {'type': LISTENING, 'details': title}
    artist = _text(song.get('artist'))
    if artist:
        activity['state'] = artist
    art = picture(song.get('cover')) or picture(cover)
    album = _text(song.get('album'))
    assets: dict[str, Any] = {'large_image': art or LOGO, 'large_text': album or title}
    if art:
        assets['small_image'] = LOGO
        assets['small_text'] = 'Dannify'
    activity['assets'] = assets
    # The progress bar: when the song started and when it ends, as Discord's
    # clock would have it, from where the playhead was when the window said.
    length = max(0.0, float(song.get('duration') or 0))
    position = max(0.0, float(song.get('position') or 0))
    if length:
        position = min(position, length)
    start = int((float(song.get('at') or time.time()) - position) * 1000)
    activity['timestamps'] = {'start': start}
    if length:
        activity['timestamps']['end'] = start + int(length * 1000)
    video_id = str(song.get('video_id') or '')
    if _YT_ID.match(video_id):
        label = _text(song.get('button') or 'Play on YouTube Music', LABEL_MOST)
        activity['buttons'] = [{'label': label, 'url': f'https://music.youtube.com/watch?v={video_id}'}]
    return activity


def plain(activity: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """*activity* as any Discord takes it: an older one knows neither the kind
    of activity nor buttons."""

    if not activity:
        return activity
    return {k: v for k, v in activity.items() if k not in ('type', 'buttons')}


def clean(info: Any, now: Optional[float] = None) -> Optional[dict[str, Any]]:
    """What the window sent, kept to what is needed: None for nothing playing."""

    if not isinstance(info, dict):
        return None

    def field(key: str, most: int = 300) -> str:
        return str(info.get(key) or '')[:most]

    def number(key: str) -> float:
        try:
            value = float(info.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0
        return value if 0 <= value <= 86400 else 0.0

    title = field('title').strip()
    if not title:
        return None
    return {
        'title': title,
        'artist': field('artist'),
        'album': field('album'),
        'cover': field('cover', 1000),
        'video_id': field('video_id', 20),
        'duration': number('duration'),
        'position': number('position'),
        'playing': bool(info.get('playing')),
        'button': field('button', 64),
        'at': time.time() if now is None else now,
    }


def find_cover(video_id: str) -> str:
    """Artwork for a saved song, from YouTube Music (the window only has the
    copy on disk, which Discord cannot reach). '' when there is none."""

    from . import providers  # noqa: PLC0415  (imports ytmusicapi)

    try:
        track = providers.watch_track(video_id) or {}
    except Exception:
        logger.opt(exception=True).debug('no artwork for {} on Discord', video_id)
        return ''
    pictures = [p for p in track.get('thumbnails') or [] if isinstance(p, dict) and p.get('url')]
    return picture(pictures[-1]['url']) if pictures else ''


# ---------------------------------------------------------------------------
# Keeping Discord up to date
# ---------------------------------------------------------------------------


class Presence:
    """What Discord has been told, and what it should be told next.

    The window says what is playing (heard) and whether this is on
    (enabled); step() does what that calls for, one thing at a time, and says
    when it next needs to run. A thread runs it (see _run); tests call it
    directly with their own clock and their own Discord.
    """

    def __init__(
        self,
        opener: Callable[[], Optional[Channel]] = open_channel,
        cover_finder: Callable[[str], str] = find_cover,
    ) -> None:
        self._opener = opener
        self._find_cover = cover_finder
        self._lock = threading.Lock()
        self.enabled = False
        self.song: Optional[dict[str, Any]] = None
        self.paused_since: Optional[float] = None
        self.channel: Optional[Channel] = None
        # What the profile shows now, as far as Discord was told: None for
        # nothing (also after the connection closes: Discord clears it).
        self.shown: Optional[dict[str, Any]] = None
        self.last_sent = float('-inf')
        self.next_try = 0.0
        self.refused = ''
        # Discord said no to the full activity: send it without the extras.
        self.trimmed = False
        self.covers: OrderedDict[str, str] = OrderedDict()

    # From the window ---------------------------------------------------

    def hear(self, song: Optional[dict[str, Any]], now: float) -> None:
        with self._lock:
            was_playing = bool(self.song and self.song.get('playing'))
            if song and song.get('playing'):
                self.paused_since = None
            elif was_playing:
                self.paused_since = now
            elif not song:
                self.paused_since = None
            self.song = song

    # What should be shown ----------------------------------------------

    def wanted(self, now: float) -> Optional[dict[str, Any]]:
        with self._lock:
            song, paused_since, enabled = self.song, self.paused_since, self.enabled
        if not enabled or not song:
            return None
        if not song.get('playing'):
            # Kept as it was for a short pause, then taken off.
            if paused_since is not None and now - paused_since < PAUSE_GRACE:
                return self.shown
            return None
        video_id = str(song.get('video_id') or '')
        activity = activity_for(song, self.covers.get(video_id, ''))
        return plain(activity) if self.trimmed else activity

    def _cover_wanted(self) -> str:
        """A song that plays without artwork Discord can reach, and whose
        artwork has not been looked for yet: its video id."""

        song = self.song
        if not song or not song.get('playing') or picture(song.get('cover')):
            return ''
        video_id = str(song.get('video_id') or '')
        if not _YT_ID.match(video_id) or video_id in self.covers:
            return ''
        return video_id

    # Doing it -------------------------------------------------------------

    def step(self, now: float) -> Optional[float]:
        """Bring Discord up to date, or as near as can be now.

        Returns how many seconds until it should run again, or None to wait
        for the window to say something.
        """

        if not self.enabled:
            self._close()
            return None
        # Connected whenever this is on, song or not, so Settings can say
        # whether Discord is there.
        if self.channel is None:
            if now < self.next_try:
                return self.next_try - now
            if not self._connect(now):
                return max(0.0, self.next_try - now)
        want = self.wanted(now)
        if want != self.shown:
            wait = MIN_GAP - (now - self.last_sent)
            if wait > 0:
                return wait
            try:
                complaint = set_activity(self.channel, want)
                if complaint and want and not self.trimmed:
                    logger.debug('Discord would not take the activity ({}); sending it plainer', complaint)
                    self.trimmed = True
                    want = plain(want)
                    complaint = set_activity(self.channel, want)
                if complaint:
                    logger.debug('Discord would not take the activity: {}', complaint)
            except OSError:
                logger.opt(exception=True).debug('lost Discord')
                self._close()
                self.next_try = now + 1.0
                return 1.0
            self.last_sent = now
            self.shown = want
        # With the song on the profile, its artwork, when only the copy on
        # disk had any: looked up once per song, then shown.
        video_id = self._cover_wanted()
        if video_id:
            self.covers[video_id] = self._find_cover(video_id)
            while len(self.covers) > _COVERS_MOST:
                self.covers.popitem(last=False)
            return 0.0
        return self._later(now)

    def _later(self, now: float) -> Optional[float]:
        with self._lock:
            paused_since = self.paused_since
        if paused_since is not None and self.shown is not None:
            return max(0.0, PAUSE_GRACE - (now - paused_since))
        return None

    def _connect(self, now: float) -> bool:
        channel = None
        try:
            channel = self._opener()
            if channel is None:
                self.next_try = now + RETRY
                return False
            handshake(channel)
        except Refused as exc:
            logger.warning('Discord turned Dannify down: {}', exc)
            self.refused = str(exc)
            if channel is not None:
                channel.close()
            self.next_try = now + RETRY * 20
            return False
        except OSError:
            logger.opt(exception=True).debug('could not reach Discord')
            if channel is not None:
                channel.close()
            self.next_try = now + RETRY
            return False
        logger.info('Connected to Discord')
        self.channel = channel
        self.refused = ''
        self.shown = None
        return True

    def _close(self) -> None:
        if self.channel is not None:
            self.channel.close()
            logger.info('Disconnected from Discord')
        self.channel = None
        self.shown = None

    def status(self) -> dict[str, Any]:
        return {'enabled': self.enabled, 'connected': self.channel is not None}


_presence = Presence()
_wake = threading.Event()
_started = threading.Lock()
_thread: Optional[threading.Thread] = None
_dir: Optional[Path] = None


def _run() -> None:
    while True:
        try:
            delay = _presence.step(time.time())
        except Exception:
            logger.opt(exception=True).warning('Discord presence went wrong; trying again shortly')
            delay = RETRY
        _wake.wait(delay)
        _wake.clear()


def _ensure_thread() -> None:
    global _thread
    with _started:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_run, name='discord-presence', daemon=True)
            _thread.start()


def init(data_dir: Path) -> None:
    """Read whether it is on. Nothing more happens until it is."""

    global _dir
    _dir = Path(data_dir)
    try:
        saved = json.loads((_dir / _FILE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        saved = {}
    _presence.enabled = bool(isinstance(saved, dict) and saved.get('enabled'))
    if _presence.enabled:
        _ensure_thread()


def status() -> dict[str, Any]:
    return _presence.status()


def set_enabled(on: bool) -> dict[str, Any]:
    """Turn it on or off, and remember the choice."""

    _presence.enabled = bool(on)
    if _dir is not None:
        path = _dir / _FILE
        temp = path.with_suffix('.tmp')
        try:
            temp.write_text(json.dumps({'enabled': _presence.enabled}), encoding='utf-8')
            os.replace(temp, path)
        except OSError:
            logger.opt(exception=True).warning('could not keep the Discord setting')
    _ensure_thread()
    _wake.set()
    return status()


def now_playing(info: Any) -> None:
    """The window says what is playing (see clean). Kept even while this is
    off, so turning it on shows the song at once."""

    _presence.hear(clean(info), time.time())
    if _presence.enabled:
        _wake.set()
