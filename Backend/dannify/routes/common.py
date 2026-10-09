"""What every part of the API shares: the app state, its settings and the
live connections to the window."""

from __future__ import annotations

import asyncio
import time
import contextlib
from collections import deque
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException, WebSocket
from loguru import logger

from ..downloader import Downloader

# What a saved song is inside its container. Not a choice any more: every
# saved song plays in Dannify and nowhere else, so the format inside is ours to
# pick, and the best pick is the stream as YouTube sends it. Its AAC is kept
# as it comes, not re-encoded into MP3 at a guessed bitrate: faster to save,
# and nothing lost on the way. The bitrate only matters for the rare track
# that arrives in another codec and has to be converted: that source is Opus
# at about 130 to 160 kbps, and 160 kbps AAC keeps all of it. It was 256,
# which made those songs nearly twice the size of what they came from for
# nothing anyone could hear.
INTERNAL_FORMAT = 'm4a'


INTERNAL_BITRATE = '160'


DEFAULT_SETTINGS: dict[str, Any] = {
    'audio_providers': ['youtube-music'],
    'lyrics_providers': ['lrclib'],
    'download_lyrics': True,
    'format': INTERNAL_FORMAT,
    'bitrate': INTERNAL_BITRATE,
    'output': '{artists} - {title}.{output-ext}',
    # Off, and no longer offered: a playlist file for other players listed
    # saved songs that none of them can open.
    'generate_m3u': False,
    'max_parallel_downloads': 3,
    # On by default: a flat folder of a few hundred tracks is unusable
    # outside the app, and an artist folder is what every music player
    # and every phone expects to find.
    'organize_by_artist': True,
    # User-controlled storage. The default '' is replaced at startup with
    # the OS-appropriate Music\Dannify folder by main.py.
    'download_dir': '',
    # 'sidecar' = write each .lrc next to its audio file (legacy);
    # 'central' = a single <download_dir>/.lyrics folder indexed by
    # (artist|title) so lyrics survive moving the audio file and can be
    # found instantly without scanning.
    'lyrics_storage': 'sidecar',
}


def _effective_lyrics_providers(settings: dict[str, Any]) -> list[str]:
    if not settings.get('download_lyrics', True):
        return []
    return [
        p
        for p in (settings.get('lyrics_providers') or [])
        if isinstance(p, str) and p
    ]


class ConnectionManager:
    """Tracks the active WebSocket clients keyed by ``client_id``."""

    def __init__(self) -> None:
        self._clients: dict[str, WebSocket] = {}
        # When a window started listening, after none was (monotonic).
        self._since = 0.0

    async def connect(self, client_id: str, ws: WebSocket) -> None:
        await ws.accept()
        if not self._clients:
            self._since = time.monotonic()
        self._clients[client_id] = ws

    def disconnect(self, client_id: str, ws: Optional[WebSocket] = None) -> None:
        # Only the socket that is going away. The window reconnects under the
        # same id, often before the server has noticed the old one close, and
        # the old one's clean-up used to take the new one with it: progress,
        # library changes and opened files all stopped arriving while the
        # window believed it was connected.
        if ws is None or self._clients.get(client_id) is ws:
            self._clients.pop(client_id, None)

    @property
    def connected(self) -> bool:
        """Whether a window is listening. Broadcasting to nobody is a no-op,
        which matters when something has to reach the window and not be lost:
        a file the shell asked us to open arrives before the page does."""

        return bool(self._clients)

    def settled(self, grace: float = 1.5) -> bool:
        """A window is listening, and has been for a moment.

        Its socket opens while the page is still putting itself together, and
        a message that arrives in that moment can find nothing yet to act on
        it: a song double-clicked in Explorer just as Dannify started was
        announced, and never played.
        """

        return bool(self._clients) and time.monotonic() - self._since >= grace

    async def send(self, client_id: str, message: dict[str, Any]) -> None:
        ws = self._clients.get(client_id)
        if ws is None:
            return
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            self.disconnect(client_id, ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        text = json.dumps(message)
        dead: list[tuple[str, WebSocket]] = []
        for client_id, ws in list(self._clients.items()):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append((client_id, ws))
        for client_id, ws in dead:
            self.disconnect(client_id, ws)


class DownloadSlots:
    """How many songs download at once, with a limit that can change while
    songs are waiting.

    It was a semaphore, made afresh when the setting changed. Songs already
    waiting held on to the old one, so turning "Parallel downloads" from 1 to
    5 in the middle of a long batch changed nothing for that batch.
    """

    def __init__(self, limit: int) -> None:
        self.limit = max(1, int(limit))
        self.busy = 0
        self._waiters: deque[asyncio.Future] = deque()

    async def __aenter__(self) -> 'DownloadSlots':
        while self.busy >= self.limit:
            waiter = asyncio.get_running_loop().create_future()
            self._waiters.append(waiter)
            try:
                await waiter
            except asyncio.CancelledError:
                with contextlib.suppress(ValueError):
                    self._waiters.remove(waiter)
                raise
        self.busy += 1
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self.busy -= 1
        self._wake()

    def resize(self, limit: int) -> None:
        self.limit = max(1, int(limit))
        self._wake()

    def _wake(self) -> None:
        free = self.limit - self.busy
        while free > 0 and self._waiters:
            waiter = self._waiters.popleft()
            if not waiter.done():
                waiter.set_result(None)
                free -= 1


class AppState:
    version: str = '0.0.0'
    # Shared secret the desktop shell hands to its own window. When set, any
    # request without it is answered as if the app were not there, so the
    # browser you happen to have open cannot drive it.
    auth_token: str = ''
    downloader: Optional[Downloader] = None
    connections: ConnectionManager = ConnectionManager()
    settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
    settings_path: Optional[Path] = None
    loop: Optional[asyncio.AbstractEventLoop] = None
    download_jobs: dict[str, dict[str, Any]] = {}
    download_semaphore: Optional[DownloadSlots] = None
    download_dir: Optional[Path] = None
    data_dir: Optional[Path] = None
    executor: Any = None


state = AppState()


def _load_settings(path: Path) -> dict[str, Any]:
    """Load saved settings from *path*, merging with DEFAULT_SETTINGS as base."""
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(saved, dict):
            merged = dict(DEFAULT_SETTINGS)
            for k, v in saved.items():
                if k in DEFAULT_SETTINGS:
                    merged[k] = v
            return merged
    except Exception:
        pass
    return dict(DEFAULT_SETTINGS)


def _save_settings(path: Path, settings: dict[str, Any]) -> None:
    """Atomic, crash-safe write of *settings* to *path*.

    Writes to a sibling ``.tmp`` then atomically replaces the target. A
    power loss between truncating and writing the body would otherwise
    leave the user with a zero-byte settings file and every preference
    reset to defaults on next launch.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(json.dumps(settings, indent=2), encoding='utf-8')
        tmp.replace(path)  # atomic on Windows + POSIX
    except Exception as exc:
        logger.warning('Could not persist settings: {}', exc)


def _coerce_download_dir(value: Any) -> Optional[Path]:
    """Validate and normalize a user-supplied download directory.

    Returns the resolved Path on success, ``None`` if blank, raises
    HTTPException(400) for invalid or non-writable paths so the UI gets a
    clean error instead of silently falling back to the old folder.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        p = Path(text).expanduser()
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f'Invalid path: {exc}'
        ) from exc
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=400,
            detail=f'Cannot create folder: {exc}',
        ) from exc
    # Writability probe: a folder we can create might still be on a
    # read-only mount (network share with no write perm, etc.).
    probe = p / '.dannify-write-probe'
    try:
        probe.write_text('ok', encoding='utf-8')
        probe.unlink()
    except OSError as exc:
        raise HTTPException(
            status_code=400,
            detail=f'Folder is not writable: {exc}',
        ) from exc
    return p.resolve()
