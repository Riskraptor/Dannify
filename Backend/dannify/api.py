"""FastAPI router exposed by Dannify.

The endpoints intentionally mirror the surface that the previous
``spotdl``-powered backend exposed so the existing Vue frontend keeps
working without changes:

* ``GET  /api/version``
* ``GET  /api/songs/search``
* ``POST /api/download/url`` (optional JSON body: resolved Spotify row so
  ``track_number`` / ``album_track_total`` survive re-fetch by URL)
* ``GET  /api/settings``
* ``POST /api/settings/update``
* ``WS   /api/ws``
* ``GET  /api/check_update``
"""

from __future__ import annotations

import asyncio
import os
import time
import contextlib
from collections import deque
import json
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Body,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from loguru import logger

from . import account
from . import library as library_mod
from . import lyrics as lyrics_mod
from . import lyrics_index
from . import lyrics_offsets
from . import lyrics_publish
from . import explorer
from . import artist_links
from . import playlists as playlists_mod
from . import report as report_mod
from . import details as details_mod
from . import layout, m3u, providers, repair, spotify, streaming, support, updates, vault
from .downloader import Downloader

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
router = APIRouter()


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


@router.get('/api/version')
def get_version() -> str:
    return state.version


def _reachable() -> bool:
    """Whether YouTube Music answers from here, right now.

    Through the same proxies as everything else the app fetches. Any answer
    at all counts: what is being asked is whether there is a way out.
    """

    import requests  # noqa: PLC0415

    try:
        requests.head('https://music.youtube.com/', timeout=4, allow_redirects=False)
        return True
    except requests.RequestException:
        return False


@router.get('/api/net')
async def net_endpoint() -> dict[str, Any]:
    """Is the connection there? Asked fresh every time.

    The window used to ask the update check, which remembers a good answer
    for six hours: online in the morning, offline by noon, and the app went
    on believing it was online, saying "something went wrong" instead of
    "you're offline", and never retrying when the connection came back.
    """

    return {'online': await asyncio.to_thread(_reachable)}


@router.get('/api/health')
def health() -> dict[str, Any]:
    """Anything wrong that the person using the app should be told about.

    Every failure so far has been a silent one. The key could not be read and
    the app showed a library of grey squares with no album names and no
    lengths, and a play button that produced a message about a file having been
    moved or deleted. Nothing anywhere said the real reason, so the same fault
    was diagnosed from scratch three times, twice by someone who only had a
    screenshot to go on.

    So the app checks the things it needs and reports what is not there. The
    window shows it. No log files are mentioned to anybody: what is wrong and
    what to do about it has to be on screen.
    """

    problems: list[dict[str, Any]] = []
    base = Path(state.download_dir) if state.download_dir else None

    # Ask the files, not the key. A key that loads is not the same as a key
    # that fits: making a fresh one is exactly what happens on a new PC, a new
    # Windows account, or after the data folder is lost, and every track saved
    # before then becomes unreadable while the app reports itself healthy.
    # That is the failure this whole endpoint exists to stop being invisible,
    # so it is the one it must actually test for.
    sealed = broken = 0
    # Not while a conversion is running: a track being rewritten is unreadable
    # for the moment it takes, and telling somebody their songs will not play
    # because the app is in the middle of fixing them would be its own bug.
    if base is not None and not vault.busy():
        try:
            for path in base.rglob('*' + vault.SUFFIX):
                sealed += 1
                if vault.inspect(path)[1]:
                    broken += 1
                if sealed >= 4000:  # a library, not a disk scan
                    break
        except OSError:
            pass

    # What is said about it is deliberately plain: a song that will not play,
    # and a button that fixes it. How saved songs are protected is nobody's
    # business but the app's, and naming the mechanism in a message is an
    # invitation to go poking at it. Whether it was sealed elsewhere or cut
    # short, the fix is the same.
    if not vault.ready():
        problems.append({'code': 'storage_unavailable'})
    elif broken:
        problems.append({
            'code': 'songs_unplayable',
            'tracks': broken,
            'of': sealed,
            'repairable': state.downloader is not None,
        })

    # Dannify 3.x wrote down each update it was about to apply and compared
    # it on the next start. The launcher applies updates now, and puts the
    # old version back itself if a new one cannot start, so a note left over
    # from then could only ever raise a false alarm.
    note = Path(state.data_dir) / 'update-result.json' if state.data_dir else None
    if note is not None and note.is_file():
        with contextlib.suppress(OSError):
            note.unlink()

    if base is None or not base.is_dir():
        problems.append({'code': 'folder_missing', 'path': str(base or '')})
    else:
        probe = base / '.dannify-write-test'
        try:
            probe.write_bytes(b'')
            probe.unlink()
        except OSError:
            problems.append({'code': 'folder_read_only', 'path': str(base)})

    return {
        'ok': not problems,
        'problems': problems,
        'version': state.version,
    }


@router.get('/api/check_update')
def check_update() -> Optional[dict[str, Any]]:
    return None


@router.get('/api/songs/search')
async def search_endpoint(query: str = Query('')) -> list[dict[str, Any]]:
    return await asyncio.to_thread(providers.search_songs, query, 20)


def _merge_client_track_hints(
    base: dict[str, Any],
    hints: Optional[dict[str, Any]],
) -> None:
    """Copy tagging fields from the client-resolved Spotify row.

    ``POST /api/download/url`` re-fetches metadata from the URL only, which loses
    ``track_number`` for rows that came from an album/playlist browse.
    """

    if not isinstance(hints, dict) or not hints:
        return
    tn = hints.get('track_number')
    if tn is not None:
        try:
            iv = int(tn)
        except (TypeError, ValueError):
            pass
        else:
            if iv > 0:
                base['track_number'] = iv
    tt = hints.get('album_track_total')
    if tt is not None:
        try:
            tv = int(tt)
        except (TypeError, ValueError):
            pass
        else:
            if tv > 0:
                base['album_track_total'] = tv
    rd = hints.get('release_date')
    if isinstance(rd, str) and rd.strip():
        base['release_date'] = rd.strip()
    yr = hints.get('year')
    if isinstance(yr, str) and yr.strip():
        base['year'] = yr.strip()


def _song_for_download(url: str) -> dict[str, Any]:
    parsed = spotify.parse_spotify_url(url)
    if parsed is not None:
        kind, sid = parsed
        if kind == 'track':
            return spotify.track_from_id(sid)
        raise HTTPException(
            status_code=400,
            detail='Only Spotify track URLs are supported here',
        )
    if 'youtube.com' in url or 'youtu.be' in url or 'music.youtube' in url:
        match = re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})', url)
        if not match:
            raise HTTPException(status_code=400, detail='Invalid YouTube URL')
        return providers.song_from_video_id(match.group(1))
    raise HTTPException(status_code=400, detail='Unsupported URL')


# A stop switch per download, set when its row is taken off the queue. The
# row used to vanish from the list while the download carried on to the end
# and saved the song anyway.
_cancels: dict[str, threading.Event] = {}
# Finished rows are kept for the queue view, but not for ever: a session
# left open for a week of playlists used to hold every one of them.
_MAX_JOBS = 400


def _song_key(song: dict[str, Any]) -> str:
    return str(song.get('song_id') or song.get('url') or id(song))


def _in_flight(song_id: str) -> bool:
    job = state.download_jobs.get(song_id)
    return bool(job) and job.get('status') in ('queued', 'downloading')


async def _wait_for_job(song_id: str) -> Optional[str]:
    """The file an in-flight download of this song ends with, once it does.

    The same song asked for again while it is already on its way (an album
    saved while one of its songs was downloading on its own, "Download all"
    pressed twice) used to start a second run under the same id. That one
    replaced the first run's stop switch, so taking the song off the queue
    stopped only the newer run: the other carried on and saved it anyway.
    """

    while True:
        job = state.download_jobs.get(song_id)
        if job is None:
            return None  # taken off the queue
        if job.get('status') == 'done':
            return job.get('filename')
        if job.get('status') == 'error':
            raise RuntimeError(job.get('message') or 'download failed')
        await asyncio.sleep(0.5)


def _register_job(song: dict[str, Any], status: str = 'queued') -> str:
    song_id = _song_key(song)
    if len(state.download_jobs) >= _MAX_JOBS:
        finished = [k for k, j in state.download_jobs.items() if j.get('status') in ('done', 'error')]
        for key in finished[: max(1, len(finished) // 2)]:
            state.download_jobs.pop(key, None)
    _cancels[song_id] = threading.Event()
    state.download_jobs[song_id] = {
        'song': song,
        'status': status,
        'progress': 0,
        'message': '',
        'filename': None,
    }
    return song_id


async def _run_download(
    song: dict[str, Any],
    song_id: str,
    subdir: Optional[str] = None,
) -> Optional[str]:
    """Run a single download to completion, updating jobs state and broadcasting WS events."""

    if state.downloader is None:
        raise RuntimeError('Downloader not ready')

    loop = state.loop or asyncio.get_running_loop()
    cancel = _cancels.get(song_id)
    if cancel is not None and cancel.is_set():
        return None  # taken off the queue before it started
    job = state.download_jobs.get(song_id)
    if job is None:
        song_id = _register_job(song, status='queued')
        job = state.download_jobs[song_id]
    cancel = _cancels.setdefault(song_id, threading.Event())

    def progress(pct: float, message: str) -> None:
        j = state.download_jobs.get(song_id)
        if j:
            j['progress'] = pct
            j['message'] = message
        asyncio.run_coroutine_threadsafe(
            state.connections.broadcast({
                'song': song,
                'progress': pct,
                'message': message,
                'status': 'downloading',
            }),
            loop,
        )

    sem = state.download_semaphore
    try:
        async with sem if sem is not None else contextlib.nullcontext():
            if cancel.is_set():
                return None  # removed while it waited for a free slot
            # Downloading from here, not from when it was asked for. Every
            # song of a batch used to say "Downloading" while all but a few
            # were still waiting for a free slot.
            job['status'] = 'downloading'
            await state.connections.broadcast({
                'song': song,
                'progress': 0,
                'message': '',
                'status': 'downloading',
            })
            filename = await loop.run_in_executor(
                None,
                lambda: state.downloader.download(
                    song, progress, subdir=subdir, cancel=cancel
                ),
            )
    except Exception as exc:
        if cancel.is_set():
            logger.info('Download stopped: {}', song_id)
            # Only its own entries. Taken off the list and put straight back,
            # the song already has a new job and a new stop switch under the
            # same id, and clearing those left the new run untracked: gone
            # from the list, and impossible to stop.
            if state.download_jobs.get(song_id) is job:
                state.download_jobs.pop(song_id, None)
            if _cancels.get(song_id) is cancel:
                _cancels.pop(song_id, None)
            return None
        if _cancels.get(song_id) is cancel:
            _cancels.pop(song_id, None)
        logger.exception('Download failed for {}', song_id)
        job['status'] = 'error'
        job['message'] = f'Error: {exc}'
        await state.connections.broadcast({
            'song': song,
            'progress': 0,
            'message': f'Error: {exc}',
            'status': 'error',
        })
        raise

    if _cancels.get(song_id) is cancel:
        _cancels.pop(song_id, None)
    job['status'] = 'done'
    job['filename'] = filename
    job['progress'] = 100
    await state.connections.broadcast({
        'song': song,
        'progress': 100,
        'message': 'Done',
        'status': 'done',
        'filename': filename,
    })
    # Invalidate library cache + tell the UI to re-index so the new song
    # immediately appears as "downloaded" everywhere (search, explorer,
    # MiniPlayer) and clicking it plays the local file instead of
    # re-streaming. No restart, no reload, no race.
    try:
        library_mod.invalidate_cache()
        await state.connections.broadcast({'type': 'library_changed'})
    except Exception:
        logger.opt(exception=True).debug('library_changed broadcast failed')
    return filename


@router.post('/api/download/url')
async def download_endpoint(
    url: str = Query(...),
    client_id: str = Query(''),
    client_hints: Optional[dict[str, Any]] = Body(None),
):
    if state.downloader is None:
        raise HTTPException(status_code=500, detail='Downloader not ready')

    song = _song_for_download(url)
    tn_before = song.get('track_number')
    yr_before = song.get('year') or song.get('release_date')
    _merge_client_track_hints(song, client_hints)
    logger.debug(
        'download/url: url={} body={} tn_before={!r} tn_after={!r} '
        'date_before={!r} date_after_year={!r} date_after_rd={!r}',
        url[:140],
        'json' if isinstance(client_hints, dict) else 'none',
        tn_before,
        song.get('track_number'),
        yr_before,
        song.get('year'),
        song.get('release_date'),
    )
    song_id = _song_key(song)
    try:
        if _in_flight(song_id):
            filename = await _wait_for_job(song_id)
        else:
            song_id = _register_job(song, status='queued')
            filename = await _run_download(song, song_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return filename


async def _process_batch(
    songs: list[dict[str, Any]],
    job_ids: list[str],
    playlist_url: str,
    generate_m3u: bool,
    following: Optional[set[str]] = None,
) -> None:
    # Resolve the playlist name up-front so all tracks land in a single,
    # per-playlist sub-folder. Loose batches (e.g. albums or unrelated
    # tracks) keep the legacy flat layout under download_dir.
    playlist_subdir: Optional[str] = None
    playlist_name: Optional[str] = None
    parsed = spotify.parse_spotify_url(playlist_url) if playlist_url else None
    if parsed is not None and parsed[0] == 'playlist':
        try:
            playlist_name, _ = await asyncio.to_thread(
                spotify.playlist_info_and_tracks, parsed[1]
            )
            playlist_subdir = m3u.sanitize_playlist_name(playlist_name)
        except Exception:
            logger.exception(
                'Failed to resolve playlist name for {}', playlist_url
            )

    async def _bounded(song: dict[str, Any], song_id: str, follow: bool) -> dict[str, Any]:
        try:
            if follow:
                filename = await _wait_for_job(song_id)
            else:
                filename = await _run_download(song, song_id, subdir=playlist_subdir)
        except Exception:
            filename = None
        return {'song': song, 'filename': filename}

    results = await asyncio.gather(
        *[
            _bounded(s, sid, sid in (following or ()))
            for s, sid in zip(songs, job_ids)
        ],
        return_exceptions=False,
    )

    if not (generate_m3u and playlist_subdir and playlist_name):
        return

    entries: list[dict[str, Any]] = []
    for r in results:
        if not r or not r.get('filename'):
            continue
        s = r['song']
        entries.append({
            'filename': r['filename'],
            'title': s.get('name') or '',
            'artist': ', '.join(s.get('artists') or []),
            'duration': s.get('duration') or 0,
        })
    if not entries:
        return

    # When organize_by_artist is on, songs land in per-artist folders instead
    # of the playlist subfolder, so the M3U must go to the legacy Playlists/
    # directory (playlist_subdir=None) where relative paths still resolve.
    organize = bool(state.downloader and state.downloader.organize_by_artist)
    try:
        await asyncio.to_thread(
            m3u.write_m3u,
            state.downloader.download_dir,
            playlist_name,
            entries,
            playlist_subdir=None if organize else playlist_subdir,
        )
    except Exception:
        logger.exception('Failed to write M3U for {}', playlist_url)


@router.post('/api/download/batch')
async def download_batch_endpoint(request: Request) -> dict[str, Any]:
    if state.downloader is None:
        raise HTTPException(status_code=500, detail='Downloader not ready')

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail='Invalid JSON') from exc

    songs = payload.get('songs') or []
    if not isinstance(songs, list) or not songs:
        raise HTTPException(
            status_code=400, detail='songs must be a non-empty list'
        )
    playlist_url = str(payload.get('playlist_url') or '')
    # Never: see DEFAULT_SETTINGS['generate_m3u'].
    generate_m3u = False

    valid_songs: list[dict[str, Any]] = []
    job_ids: list[str] = []
    following: set[str] = set()
    for song in songs:
        if not isinstance(song, dict):
            continue
        song_id = _song_key(song)
        if song_id in job_ids:
            continue  # listed twice in the same batch
        valid_songs.append(song)
        job_ids.append(song_id)
        if _in_flight(song_id):
            # Already on its way: this batch waits for that run instead of
            # starting another one (see _wait_for_job).
            following.add(song_id)
            continue
        _register_job(song, status='queued')
        await state.connections.broadcast({
            'song': song,
            'progress': 0,
            'message': '',
            'status': 'queued',
        })

    if not valid_songs:
        raise HTTPException(status_code=400, detail='No valid songs in batch')

    task = asyncio.create_task(
        _process_batch(valid_songs, job_ids, playlist_url, generate_m3u, following)
    )

    def _log_batch_failure(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.opt(exception=exc).error('Batch processing crashed')

    task.add_done_callback(_log_batch_failure)
    return {'job_ids': job_ids, 'count': len(job_ids)}


@router.get('/api/queue')
def get_queue() -> list[dict[str, Any]]:
    return list(state.download_jobs.values())


@router.delete('/api/queue')
def clear_queue() -> dict:
    # Clearing the list stops what is on it, as removing one row does.
    for ev in list(_cancels.values()):
        ev.set()
    state.download_jobs.clear()
    return {'cleared': True}


@router.delete('/api/queue/item')
def remove_queue_item(song_id: str = Query(...)) -> dict:
    ev = _cancels.get(song_id)
    if ev is not None:
        ev.set()
    if song_id in state.download_jobs:
        del state.download_jobs[song_id]
        return {'removed': True}
    return {'removed': False}


# Settings the interface has no business seeing. Where lyrics come from is an
# implementation detail: there is no picker for it, nothing renders it, and a
# name travelling to the UI is a name that ends up in the shipped bundle.
_PRIVATE_SETTINGS = (
    'lyrics_providers', 'audio_providers',
    # Fixed now (see INTERNAL_FORMAT). An old settings file may still hold a
    # choice from when they were offered; it is kept, and not used.
    'format', 'bitrate', 'generate_m3u',
)


@router.get('/api/settings')
def get_settings_endpoint(client_id: str = Query('')) -> dict[str, Any]:
    return {k: v for k, v in state.settings.items() if k not in _PRIVATE_SETTINGS}


@router.post('/api/settings/update')
async def update_settings_endpoint(
    request: Request, client_id: str = Query('')
) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if isinstance(payload, dict):
        # download_dir is special: validate THEN apply live (no restart).
        # Off the event loop: joining a folder walks all of it, and on a big
        # library or a network drive that held every stream, every search and
        # the websocket until it finished.
        if 'download_dir' in payload:
            await asyncio.to_thread(_apply_download_dir, payload['download_dir'])

        if 'lyrics_storage' in payload:
            mode = str(payload['lyrics_storage']).strip().lower()
            if mode in ('sidecar', 'central'):
                state.settings['lyrics_storage'] = mode
                # Downloads use it from now, not from the next start.
                if state.downloader is not None:
                    state.downloader.lyrics_storage = mode

        for key, value in payload.items():
            if key in ('download_dir', 'lyrics_storage') or key in _PRIVATE_SETTINGS:
                continue  # handled above, or not the window's to set
            if key in DEFAULT_SETTINGS:
                state.settings[key] = value
        _apply_to_downloader(payload)
    if state.settings_path is not None:
        await asyncio.to_thread(_save_settings, state.settings_path, state.settings)
    # The same view GET gives: the private ones stay private here too.
    return get_settings_endpoint()


def _apply_download_dir(value: Any) -> None:
    """Move the library to *value*, live. Runs on a worker thread."""

    new_dir = _coerce_download_dir(value)
    if new_dir is None:
        return
    state.download_dir = new_dir
    if state.downloader is not None:
        state.downloader.download_dir = new_dir
        new_dir.mkdir(parents=True, exist_ok=True)
    # Re-point the central lyrics index at the new folder
    # (no-op if storage mode is 'sidecar', it just exists).
    lyrics_index.init(new_dir)
    # And join it, so songs already in it open and new ones are
    # sealed the way that folder's songs are.
    try:
        vault.attach(new_dir)
    except Exception:
        logger.opt(exception=True).warning('could not join {}', new_dir)
    # Drop the library cache so the new location is scanned.
    library_mod.invalidate_cache()
    state.settings['download_dir'] = str(new_dir)
    # Broadcast so the frontend re-loads its library index.
    if state.loop is not None:
        asyncio.run_coroutine_threadsafe(
            state.connections.broadcast({'type': 'library_changed'}),
            state.loop,
        )


def _apply_to_downloader(payload: dict[str, Any]) -> None:
    """Hand the settings that shape a download to the downloader, live."""

    if state.downloader is not None:
        output = payload.get('output')
        if isinstance(output, str) and output:
            state.downloader.output_template = output.replace(
                '.{output-ext}', ''
            )
        if 'lyrics_providers' in payload or 'download_lyrics' in payload:
            state.downloader.lyrics_providers = (
                _effective_lyrics_providers(state.settings)
            )
        if 'organize_by_artist' in payload:
            state.downloader.organize_by_artist = bool(
                payload['organize_by_artist']
            )
    if 'max_parallel_downloads' in payload:
        try:
            count = max(1, int(payload['max_parallel_downloads']))
            if isinstance(state.download_semaphore, DownloadSlots):
                state.download_semaphore.resize(count)
            else:
                state.download_semaphore = DownloadSlots(count)
        except (TypeError, ValueError):
            pass


@router.post('/api/settings/pick-folder')
async def pick_folder_endpoint() -> dict[str, Any]:
    """Open the OS-native folder picker; return ``{path}`` or ``{cancelled:True}``.

    Uses pywebview's dialog when the app is running inside the desktop
    window. Falls back to Tk in browser-mode dev runs so the endpoint is
    safe to call from anywhere.
    """

    def _pick() -> Optional[str]:
        # 1) Desktop build: pywebview window present.
        try:
            import webview  # type: ignore
            if webview.windows:
                win = webview.windows[0]
                result = win.create_file_dialog(
                    webview.FOLDER_DIALOG,  # type: ignore[attr-defined]
                    allow_multiple=False,
                    directory=str(state.download_dir or Path.home()),
                )
                if result:
                    return result[0] if isinstance(result, (list, tuple)) else str(result)
                return None
        except Exception:
            logger.opt(exception=True).debug('pywebview folder picker unavailable')

        # 2) Dev / browser fallback.
        try:
            import tkinter as _tk
            from tkinter import filedialog as _fd

            root = _tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            chosen = _fd.askdirectory(
                title='Choose Dannify downloads folder',
                initialdir=str(state.download_dir or Path.home()),
            )
            root.destroy()
            return chosen or None
        except Exception:
            logger.opt(exception=True).debug('tk folder picker unavailable')
            return None

    chosen = await asyncio.to_thread(_pick)
    if not chosen:
        return {'cancelled': True}
    return {'path': str(Path(chosen).resolve())}


@router.get('/api/library/locate')
async def library_locate_endpoint(
    video_id: str = Query(''),
    title: str = Query(''),
    artist: str = Query(''),
) -> dict[str, Any]:
    """Return the local file path for a song if it's downloaded.

    Frontend calls this on every "click play" so a downloaded song is
    served from disk (instant, no ffmpeg, no network) instead of being
    re-streamed from YouTube. Uses the same canonical-artist matching as
    the library index, plus an exact ``video_id`` shortcut.
    """

    base = state.download_dir
    if base is None:
        return {'found': False}
    try:
        hit = await asyncio.to_thread(
            library_mod.locate, base, video_id, artist, title
        )
    except Exception:
        logger.opt(exception=True).debug('library locate failed')
        return {'found': False}
    if hit is None:
        return {'found': False}
    return {'found': True, **hit}


# ---------------------------------------------------------------------------
# Preview (resolve a Spotify/YouTube link before downloading)
# ---------------------------------------------------------------------------


@router.get('/api/preview')
def preview_endpoint(url: str = Query(...)) -> dict[str, Any]:
    """Resolve a Spotify/YouTube link into a rich, UI-ready preview payload.

    For tracks returns ``{type:'track', tracks:[...]}``; for albums/playlists
    returns the full track list so the UI can let the user pick a subset
    *before* any download or stream happens.
    """

    parsed = spotify.parse_spotify_url(url)
    if parsed is None:
        # Try a bare YouTube video.
        if 'youtu' in url:
            try:
                song = streaming.resolve_stream(url)
            except Exception as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            return {
                'type': 'track',
                'name': song.get('name'),
                'tracks': [song],
                'total': 1,
            }
        raise HTTPException(status_code=400, detail='Invalid URL')

    kind, sid = parsed
    try:
        if kind == 'track':
            song = spotify.track_from_id(sid)
            return {
                'type': 'track',
                'name': song.get('name'),
                'cover': song.get('cover_url'),
                'tracks': [song],
                'total': 1,
            }
        if kind == 'album':
            tracks = spotify.album_tracks_from_id(sid)
            cover = tracks[0].get('cover_url') if tracks else ''
            return {
                'type': 'album',
                'name': (tracks[0].get('album_name') if tracks else '') or '',
                'cover': cover,
                'tracks': tracks,
                'total': len(tracks),
            }
        if kind == 'playlist':
            name, tracks = spotify.playlist_info_and_tracks(sid)
            cover = tracks[0].get('cover_url') if tracks else ''
            return {
                'type': 'playlist',
                'name': name,
                'cover': cover,
                'playlist_url': url,
                'tracks': tracks,
                'total': len(tracks),
            }
    except Exception as exc:
        logger.exception('Preview failed for {}', url)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=f'Unsupported type: {kind}')


# ---------------------------------------------------------------------------
# Online explorer - Spotify-style discovery (songs/artists/albums/playlists)
# ---------------------------------------------------------------------------


@router.get('/api/explore/search')
async def explore_search_endpoint(
    q: str = Query(''), limit: int = Query(20)
) -> dict[str, Any]:
    if not q.strip():
        return {'songs': [], 'artists': [], 'albums': [], 'playlists': []}
    try:
        return await asyncio.to_thread(explorer.search, q, limit)
    except explorer.SearchUnavailable as exc:
        # The window tells "no connection" from "nothing found" by this.
        raise HTTPException(status_code=503, detail='unreachable') from exc
    except Exception as exc:
        logger.exception('explore search failed for {}', q)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get('/api/explore/artist')
async def explore_artist_endpoint(id: str = Query(...)) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(explorer.artist, id)
    except LookupError as exc:
        # No such artist or channel (removed, or a wrong link): say so, so
        # the page can tell it from YouTube failing to answer.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('explore artist failed for {}', id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get('/api/explore/album')
async def explore_album_endpoint(id: str = Query(...)) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(explorer.album, id)
    except Exception as exc:
        logger.exception('explore album failed for {}', id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get('/api/explore/moods')
async def explore_moods_endpoint() -> dict[str, Any]:
    try:
        return {'sections': await asyncio.to_thread(explorer.moods)}
    except Exception as exc:
        logger.opt(exception=True).info('moods and genres failed')
        raise HTTPException(status_code=502, detail='unavailable') from exc


@router.get('/api/explore/moods/playlists')
async def explore_mood_playlists_endpoint(params: str = Query(..., max_length=400)) -> dict[str, Any]:
    try:
        return {'playlists': await asyncio.to_thread(explorer.mood_playlists, params)}
    except Exception as exc:
        logger.opt(exception=True).info('mood playlists failed')
        raise HTTPException(status_code=502, detail='unavailable') from exc


@router.get('/api/explore/playlist')
async def explore_playlist_endpoint(
    id: str = Query(...), limit: int = Query(200)
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(explorer.playlist, id, limit)
    except Exception as exc:
        logger.exception('explore playlist failed for {}', id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Streaming (play without downloading)
# ---------------------------------------------------------------------------


@router.get('/api/resolve')
async def resolve_endpoint(url: str = Query(...)) -> dict[str, Any]:
    try:
        song = await asyncio.to_thread(streaming.resolve_stream, url)
        # Warm the direct-URL cache + attach duration so the player can show
        # the end time immediately (transcoded streams carry no length header).
        vid = str(song.get('video_id') or '')
        if vid:
            try:
                info = await asyncio.to_thread(streaming.probe, vid)
                if info.get('duration'):
                    song = {**song, 'duration': info['duration']}
                song = {**song, 'stream_mime': info.get('mime')}
            except Exception:
                logger.opt(exception=True).debug('probe failed for {}', vid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('Resolve failed for {}', url)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return song


_YT_ID_RE = re.compile(r'[A-Za-z0-9_-]{11}')
_SPOTIFY_ID_RE = re.compile(r'[A-Za-z0-9]{22}')


async def _resolve_video_id(video_id: str, url: str) -> str:
    """Return a valid 11-char YouTube videoId, resolving non-YT ids/URLs.

    Hardens the stream endpoints against any client (or stale build) that
    sends a Spotify track id / URL instead of a YouTube videoId.
    """

    vid = (video_id or '').strip()
    if not vid and url:
        song = await asyncio.to_thread(streaming.resolve_stream, url)
        vid = str(song.get('video_id') or '')

    if vid and not _YT_ID_RE.fullmatch(vid):
        resolve_src = url
        if not resolve_src and _SPOTIFY_ID_RE.fullmatch(vid):
            resolve_src = f'https://open.spotify.com/track/{vid}'
        if resolve_src:
            song = await asyncio.to_thread(
                streaming.resolve_stream, resolve_src
            )
            vid = str(song.get('video_id') or '')
    return vid


@router.get('/api/stream/info')
async def stream_info_endpoint(
    video_id: str = Query(''),
    url: str = Query(''),
    prefetch: int = Query(0),
) -> dict[str, Any]:
    """Return ``{duration, mime}`` for a streamable source (no audio yet).

    Pass ``prefetch=1`` to also warm the on-disk cache in the background so a
    subsequent play (e.g. the next queued track) starts instantly.
    """

    try:
        vid = await _resolve_video_id(video_id, url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not vid:
        raise HTTPException(status_code=400, detail='Missing video_id or url')
    try:
        info = await asyncio.to_thread(streaming.probe, vid)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if prefetch:
        try:
            streaming.prefetch(vid)
        except Exception:
            pass
    return info


@router.get('/api/stream/prefetch')
async def stream_prefetch_endpoint(video_id: str = Query(...)) -> dict[str, Any]:
    vid = video_id.strip()
    if not vid:
        raise HTTPException(status_code=400, detail='Missing video_id')
    streaming.prefetch(vid)
    return {'prefetching': vid}


@router.get('/api/stream')
async def stream_endpoint(
    request: Request,
    video_id: str = Query('', alias='video_id'),
    url: str = Query(''),
    t: float = Query(0.0),
    force_mp3: int = Query(0),
):
    """Stream audio for a videoId.

    **Default path**: pure HTTP byte-range proxy to the upstream
    googlevideo URL. Forwards the browser's ``Range:`` header and
    response with ``Accept-Ranges: bytes`` + ``Content-Length`` so
    the browser does NATIVE seeking on the progress bar (instant
    same as scrubbing an MP3 served from any web server). No ffmpeg,
    no re-encode, no rebuffer.

    **Fallback path** (``?force_mp3=1`` or legacy ``?t=`` seek hint)
    transcode the audio to MP3 with ffmpeg on the fly. Slower; only
    kept for the (rare) browsers/codecs the proxy can't handle.
    """

    try:
        vid = await _resolve_video_id(video_id, url)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception('Stream resolve failed for {} / {}', video_id, url)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not vid:
        raise HTTPException(status_code=400, detail='Missing video_id or url')

    # Honour the explicit fallback flag (or the legacy ``?t=`` seek path,
    # which only works on the ffmpeg side: but with the new proxy the
    # browser handles seeking natively, so ``?t=`` is essentially dead
    # code on the happy path).
    if force_mp3 or t > 0:
        try:
            mime, gen = await asyncio.to_thread(
                streaming.open_stream, vid, max(0.0, t)
            )
        except Exception as exc:
            logger.exception('Streaming (ffmpeg) failed for {}', vid)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return StreamingResponse(
            gen,
            media_type=mime,
            headers={
                'Content-Type': mime,
                'Cache-Control': 'no-store',
                'Accept-Ranges': 'none',
            },
        )

    # --- Default: native byte-range proxy (instant seek) ---
    range_header = request.headers.get('range') or request.headers.get('Range')
    try:
        status, headers, gen = await asyncio.to_thread(
            streaming.open_proxy, vid, range_header
        )
    except Exception as exc:
        logger.exception('Stream proxy failed for {}', vid)
        # Fallback to ffmpeg path on hard proxy failure so the user still
        # gets audio. Better degraded than broken.
        try:
            mime, fb_gen = await asyncio.to_thread(streaming.open_stream, vid)
        except Exception as exc2:
            raise HTTPException(status_code=502, detail=str(exc2)) from exc2
        return StreamingResponse(
            fb_gen,
            media_type=mime,
            headers={
                'Content-Type': mime,
                'Cache-Control': 'no-store',
                'Accept-Ranges': 'none',
            },
        )
    return StreamingResponse(
        gen,
        status_code=status,
        media_type=headers.get('Content-Type', 'audio/mp4'),
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Lyrics (synced + plain) for streamed or downloaded tracks
# ---------------------------------------------------------------------------


def _lyrics_storage_mode() -> str:
    return str(state.settings.get('lyrics_storage') or 'sidecar').lower()


def _persist_lyrics(full: Path, artist: str, title: str, text: str) -> None:
    """Write *text* as the .lrc for this track in the user-chosen location."""
    if not text:
        return
    # The song itself has to be there. Lyrics for one deleted a moment ago
    # (still on screen, still paused) used to be written beside its old name,
    # leaving a lyrics file behind with nothing to belong to.
    if not full.is_file():
        return
    mode = _lyrics_storage_mode()
    try:
        if mode == 'central':
            lyrics_index.store(artist, title, text)
        else:
            full.with_suffix('.lrc').write_text(text, encoding='utf-8')
    except OSError:
        logger.opt(exception=True).debug('Could not write .lrc for {}', full)


def _read_existing_lyrics(full: Path, artist: str, title: str) -> str:
    """Return any already-stored .lrc text for this track, '' if none.

    Looks in BOTH places (sidecar + central) regardless of the current
    setting, so toggling the storage mode doesn't orphan previously
    saved lyrics.
    """
    sidecar = full.with_suffix('.lrc')
    if sidecar.is_file():
        try:
            return sidecar.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            pass
    central = lyrics_index.lookup_text(artist, title)
    return central or ''


def _lyrics_from_file(
    file: str,
    refresh: bool = False,
    hints: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Read synced/plain lyrics from a downloaded file's .lrc or tags.

    When *refresh* is True the local ``.lrc``/embedded copies are skipped and
    fresh lyrics are fetched online (and re-saved), so the reload button always
    re-queries the source.
    """

    if state.download_dir is None:
        raise HTTPException(status_code=500, detail='Library not ready')
    full = _library_file(file)
    if full is None:
        raise HTTPException(status_code=400, detail='Invalid path')

    # Prefer a stored .lrc (sidecar OR central index) unless reloading.
    meta_for_keys = library_mod._read_tags(full)
    keys_artist = meta_for_keys.get('artist', '') or ''
    keys_title = meta_for_keys.get('title', '') or ''
    if not refresh:
        stored = _read_existing_lyrics(full, keys_artist, keys_title)
        if stored:
            lines = lyrics_mod.parse_lrc(stored)
            if lines:
                plain = '\n'.join(
                    ln['text'] for ln in lines if ln['text']
                ) or None
                return {'synced': lines, 'plain': plain, 'has': True}
            txt = stored.strip()
            if txt:
                return {'synced': [], 'plain': txt, 'has': True}

    # Fall back to plain lyrics kept in the file itself.
    plain = None
    try:
        from . import tags as _tags  # noqa: PLC0415

        plain = _tags.lyrics(full) or None
    except Exception:
        logger.opt(exception=True).debug('Embedded lyrics read failed')

    # ------------------------------------------------------------------
    # Online fallback: if the file has no synced lyrics locally, query the
    # online source (lrclib) using the file's own tags, then PERSIST the
    # result as a .lrc sidecar so future loads are instant (offline): unless
    # the user explicitly reloads.
    # ------------------------------------------------------------------
    try:
        meta = library_mod._read_tags(full)
        song = {
            'name': meta.get('title') or '',
            'artists': meta.get('artists') or (
                [meta['artist']] if meta.get('artist') else []
            ),
            'album_name': meta.get('album') or '',
            'duration': meta.get('duration') or 0,
        }
        # A downloaded file's tags are whatever the download managed to
        # write, and they are regularly thinner than what the app itself
        # knows: a missing artist used to skip the online lookup entirely,
        # which is why lyrics published for a downloaded song never came
        # back. Fall back to what the player is showing.
        hint = hints or {}
        if not song['name']:
            song['name'] = str(hint.get('title') or '')
        if not song['artists']:
            song['artists'] = [
                a.strip()
                for a in str(hint.get('artist') or '').split(',')
                if a.strip()
            ]
        if not song['album_name']:
            song['album_name'] = str(hint.get('album') or '')
        if not song['duration']:
            song['duration'] = int(hint.get('duration') or 0)

        if song['name'] and song['artists']:
            raw = lyrics_mod.fetch(
                song, _effective_lyrics_providers(state.settings) or ['lrclib']
            )
            # Tags and the player can disagree about how a track is named.
            # If the file's own version found nothing, try the player's.
            if (raw is None or not raw.has_any()) and hint.get('title'):
                alt = {
                    'name': str(hint.get('title') or ''),
                    'artists': [
                        a.strip()
                        for a in str(hint.get('artist') or '').split(',')
                        if a.strip()
                    ],
                    'album_name': str(hint.get('album') or ''),
                    'duration': int(hint.get('duration') or 0),
                }
                if alt['name'] and alt['artists'] and alt != song:
                    raw = lyrics_mod.fetch(
                        alt,
                        _effective_lyrics_providers(state.settings) or ['lrclib'],
                    )
            if raw is not None and raw.has_any():
                # Persist using the user-chosen storage location.
                text_to_save = raw.synced or (raw.plain or '')
                if text_to_save:
                    _persist_lyrics(
                        full,
                        meta.get('artist', '') or keys_artist,
                        meta.get('title', '') or keys_title,
                        text_to_save,
                    )

                synced_lines = lyrics_mod.parse_lrc(raw.synced)
                out_plain = raw.plain or plain
                if not out_plain and synced_lines:
                    out_plain = '\n'.join(
                        ln['text'] for ln in synced_lines if ln['text']
                    ) or None
                return {
                    'synced': synced_lines,
                    'plain': out_plain,
                    'has': bool(synced_lines or out_plain),
                }
    except Exception:
        logger.opt(exception=True).debug('Online lyrics fallback failed')

    return {
        'synced': [],
        'plain': plain,
        'has': bool(plain),
    }


@router.get('/api/lyrics')
async def lyrics_endpoint(
    file: str = Query(''),
    url: str = Query(''),
    title: str = Query(''),
    artist: str = Query(''),
    album: str = Query(''),
    duration: int = Query(0),
    refresh: int = Query(0),
) -> dict[str, Any]:
    """Return ``{synced:[{time,text}], plain, has}`` for a track.

    Accepts either a downloaded ``file`` (reads .lrc/embedded), a Spotify/
    YouTube ``url`` (live lrclib lookup), or raw ``title``/``artist`` hints.
    Pass ``refresh=1`` to bypass the lyrics cache and re-query the source.
    """
    if refresh:
        lyrics_mod.clear_cache()

    if file:
        result = await asyncio.to_thread(
            _lyrics_from_file,
            file,
            bool(refresh),
            {
                'title': title,
                'artist': artist,
                'album': album,
                'duration': duration,
            },
        )
        # Attach the crowd-sourced prefs using the file's own tags.
        try:
            where = _library_file(file)
            if where is None:
                raise ValueError('not in the library')
            meta = library_mod._read_tags(where)
            prefs = lyrics_offsets.get_prefs(
                meta.get('title', ''), meta.get('artist', '')
            )
            result['offset'] = prefs['offset']
            result['version'] = prefs['version']
            result['title'] = meta.get('title', '')
            result['artist'] = meta.get('artist', '')
        except Exception:
            result.setdefault('offset', 0.0)
            result.setdefault('version', 0)
        return result

    song: dict[str, Any]
    if url:
        parsed = spotify.parse_spotify_url(url)
        if parsed is not None and parsed[0] == 'track':
            song = await asyncio.to_thread(spotify.track_from_id, parsed[1])
        else:
            song = await asyncio.to_thread(streaming.resolve_stream, url)
    else:
        artists = [a.strip() for a in artist.split(',') if a.strip()]
        song = {
            'name': title,
            'artists': artists,
            'album_name': album,
            'duration': duration,
        }
    if not song.get('name'):
        return {
            'synced': [], 'plain': None, 'has': False,
            'offset': 0.0, 'version': 0, 'version_count': 0,
        }

    song_artists = song.get('artists') or []
    primary = song_artists[0] if song_artists else ''
    prefs = lyrics_offsets.get_prefs(song.get('name', ''), primary)

    if prefs['version'] > 0:
        # User picked a specific version → resolve the full list.
        versions = await asyncio.to_thread(
            lyrics_mod.fetch_versions_structured, song
        )
        if versions:
            idx = prefs['version'] if prefs['version'] < len(versions) else 0
            chosen = versions[idx]
            result = {
                'synced': chosen['synced'],
                'plain': chosen['plain'],
                'has': True,
                'version_count': len(versions),
            }
        else:
            result = await asyncio.to_thread(
                lyrics_mod.fetch_structured,
                song,
                _effective_lyrics_providers(state.settings) or ['lrclib'],
            )
            result['version_count'] = 0
    else:
        # FAST PATH: single best-match fetch (one parallel /get+/search round).
        # The version count is discovered lazily by the frontend only when the
        # user opens the switcher: keeping the common load quick.
        result = await asyncio.to_thread(
            lyrics_mod.fetch_structured,
            song,
            _effective_lyrics_providers(state.settings) or ['lrclib'],
        )
        # -1 means "unknown; ask /api/lyrics/versions on demand".
        result['version_count'] = -1 if result.get('synced') else 0

    result['offset'] = prefs['offset']
    result['version'] = prefs['version']
    result['title'] = song.get('name', '')
    result['artist'] = primary
    return result


@router.get('/api/lyrics/versions')
async def lyrics_versions_endpoint(
    title: str = Query(''),
    artist: str = Query(''),
    album: str = Query(''),
    duration: int = Query(0),
    url: str = Query(''),
    file: str = Query(''),
) -> dict[str, Any]:
    """Return ALL synced lyric versions for a song so the UI can switch.

    Each entry: ``{synced:[{time,text}], plain}``. The currently-saved version
    index + offset are included.
    """

    song: dict[str, Any]
    where = _library_file(file) if file else None
    if where is not None:
        try:
            meta = library_mod._read_tags(where)
            song = {
                'name': meta.get('title') or '',
                'artists': meta.get('artists')
                or ([meta['artist']] if meta.get('artist') else []),
                'album_name': meta.get('album') or '',
                'duration': meta.get('duration') or 0,
            }
        except Exception:
            song = {'name': title, 'artists': [artist] if artist else []}
    elif url:
        parsed = spotify.parse_spotify_url(url)
        if parsed is not None and parsed[0] == 'track':
            song = await asyncio.to_thread(spotify.track_from_id, parsed[1])
        else:
            song = await asyncio.to_thread(streaming.resolve_stream, url)
    else:
        artists = [a.strip() for a in artist.split(',') if a.strip()]
        song = {
            'name': title,
            'artists': artists,
            'album_name': album,
            'duration': duration,
        }
    if not song.get('name'):
        return {'versions': [], 'version': 0, 'offset': 0.0}
    versions = await asyncio.to_thread(
        lyrics_mod.fetch_versions_structured, song
    )
    song_artists = song.get('artists') or []
    primary = song_artists[0] if song_artists else ''
    prefs = lyrics_offsets.get_prefs(song.get('name', ''), primary)
    return {
        'versions': versions,
        'version': prefs['version'] if prefs['version'] < len(versions) else 0,
        'offset': prefs['offset'],
        'title': song.get('name', ''),
        'artist': primary,
    }


@router.post('/api/lyrics/offset')
async def lyrics_offset_endpoint(request: Request) -> dict[str, Any]:
    """Save per-song lyric prefs (timing offset + chosen version). Shared.

    Body: ``{title, artist, offset?, version?}``. Positive offset = lyrics
    appear later; version = index of the synced version that syncs best.
    """

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid JSON')
    title = str(payload.get('title') or '').strip()
    artist = str(payload.get('artist') or '').strip()
    if not title or not artist:
        raise HTTPException(status_code=400, detail='title and artist required')
    offset = payload.get('offset')
    version = payload.get('version')
    try:
        offset = None if offset is None else float(offset)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='offset must be a number')
    try:
        version = None if version is None else int(version)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='version must be an int')
    rec = await asyncio.to_thread(
        lyrics_offsets.set, title, artist, offset, version
    )
    return {
        'title': title,
        'artist': artist,
        'offset': rec['offset'],
        'version': rec['version'],
    }


@router.post('/api/lyrics/publish')
async def lyrics_publish_endpoint(request: Request) -> dict[str, Any]:
    """Submit lyrics to lrclib.

    Body: ``{track, artist, album, duration, plain?, synced?}``.

    The flow is entirely synchronous from the client's POV: this endpoint
    requests a fresh proof-of-work challenge from lrclib, solves it
    (multi-process search, ~10-20 s on a typical box), then posts the
    final lyrics. We invalidate the in-memory lyrics cache for this song
    on success so the next ``/api/lyrics`` lookup picks up the new
    contribution from lrclib.

    Returns ``{published: true}`` on success or ``{published: false,
    error: '…'}`` on failure (HTTP 200 either way. The UI shows the
    error inline; this avoids needing two error-handling paths).
    """

    try:
        payload = await request.json()
    except Exception:
        return {'published': False, 'error': 'Invalid JSON body'}

    track = str(payload.get('track') or '').strip()
    artist = str(payload.get('artist') or '').strip()
    album = str(payload.get('album') or '').strip()
    plain = str(payload.get('plain') or '')
    synced = str(payload.get('synced') or '')
    try:
        duration = float(payload.get('duration') or 0)
    except (TypeError, ValueError):
        return {'published': False, 'error': 'duration must be a number'}

    if not track or not artist:
        return {
            'published': False,
            'error': 'Track title and artist are required.',
        }
    if duration <= 0:
        return {
            'published': False,
            'error': 'Track duration is required (must be > 0).',
        }
    if not plain.strip() and not synced.strip():
        # lrclib's docs allow empty-both (marks track as instrumental),
        # but our UI shouldn't be sending that: guard explicitly.
        return {
            'published': False,
            'error': 'No lyrics provided. Add plain or synced lyrics.',
        }

    try:
        await asyncio.to_thread(
            lyrics_publish.publish,
            track_name=track,
            artist_name=artist,
            album_name=album,
            duration=duration,
            plain_lyrics=plain,
            synced_lyrics=synced,
        )
    except lyrics_publish.PublishError as exc:
        logger.warning('lyrics publish refused: {}', exc)
        return {'published': False, 'error': str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.exception('lyrics publish crashed')
        return {'published': False, 'error': f'Unexpected error: {exc}'}

    # Drop our caches for this song so the next lookup refreshes from
    # lrclib (which now serves the user's own contribution).
    try:
        song_key = {
            'name': track,
            'artists': [artist],
        }
        lyrics_mod.clear_cache(song_key)
    except Exception:
        logger.opt(exception=True).debug(
            'Could not clear lyrics cache after publish'
        )

    return {'published': True}


# ---------------------------------------------------------------------------
# Offline library: artists, albums, search
# ---------------------------------------------------------------------------


def _require_download_dir() -> Path:
    if state.download_dir is None:
        raise HTTPException(status_code=500, detail='Library not ready')
    return state.download_dir


def _library_file(file: str) -> Optional[Path]:
    """*file* inside the music folder, or None if it names anywhere else.

    Checked by its shape before anything touches the disk: resolving a
    network path (a UNC name, host and share) is already a connection to that
    host, and the lyrics endpoints used to join whatever they were given onto
    the music folder and read its tags, which answers for any file on the
    machine.
    """

    base = state.download_dir
    if base is None or not file:
        return None
    rel = Path(str(file).replace(chr(92), '/'))
    if rel.is_absolute() or rel.drive or rel.anchor or '..' in rel.parts or ':' in str(file):
        return None
    root = Path(base).resolve()
    try:
        full = (root / rel).resolve()
        full.relative_to(root)
    except (ValueError, RuntimeError, OSError):
        return None
    return full


@router.get('/api/library')
async def library_endpoint() -> dict[str, Any]:
    base = _require_download_dir()
    return await asyncio.to_thread(library_mod.library, base)


@router.get('/api/library/search')
async def library_search_endpoint(
    q: str = Query(''), limit: int = Query(50)
) -> dict[str, Any]:
    base = _require_download_dir()
    return await asyncio.to_thread(library_mod.search, base, q, limit)


@router.get('/api/artists')
async def artists_endpoint() -> list[dict[str, Any]]:
    base = _require_download_dir()
    return await asyncio.to_thread(library_mod.artists, base)


# ---------------------------------------------------------------------------
# Storage: what the library takes up, and the caches that can go
# ---------------------------------------------------------------------------

_CACHE_FILES = ('lyrics_cache.json', 'direct_cache.json', 'artist_links.json')
_CACHE_DIRS = ('ytdlp-cache',)


def _size_of(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())
    except OSError:
        return 0


@router.get('/api/storage')
async def storage_endpoint() -> dict[str, Any]:
    base = _require_download_dir()

    def measure() -> dict[str, Any]:
        songs = size = 0
        for path in base.rglob('*'):
            if path.suffix.lower() in library_mod._AUDIO_EXTS and path.is_file():
                songs += 1
                try:
                    size += path.stat().st_size
                except OSError:
                    pass
        data = Path(state.data_dir) if state.data_dir else None
        caches = 0
        if data is not None:
            caches = sum(_size_of(data / n) for n in _CACHE_FILES + _CACHE_DIRS)
        try:
            free = shutil.disk_usage(base).free
        except OSError:
            free = 0
        return {'songs': songs, 'bytes': size, 'free': free, 'caches': caches}

    return await asyncio.to_thread(measure)


@router.post('/api/storage/clear-caches')
async def clear_caches_endpoint() -> dict[str, Any]:
    """Forget what is only kept to be quick: looked-up lyrics, stream
    addresses, YouTube's player code and artist pictures. Never the music,
    and never lyrics anybody wrote or saved beside a song."""

    def clear() -> None:
        lyrics_mod.clear_cache()
        streaming.clear_direct_cache()
        artist_links.clear()
        if state.data_dir:
            for name in _CACHE_DIRS:
                folder = Path(state.data_dir) / name
                shutil.rmtree(folder, ignore_errors=True)
                folder.mkdir(parents=True, exist_ok=True)

    await asyncio.to_thread(clear)
    return {'cleared': True}


# ---------------------------------------------------------------------------
# Refreshing saved songs' details, and artists'
# ---------------------------------------------------------------------------

_details_lock: Optional[asyncio.Lock] = None


@router.post('/api/library/details')
async def refresh_details_endpoint(
    payload: Optional[dict[str, Any]] = Body(None),
) -> dict[str, Any]:
    """Fetch the details of saved songs again, around the same audio.

    ``{"files": [...]}``. Runs in the background, one song at a time; the
    window hears how it goes over the websocket (``type: details``).
    """

    global _details_lock
    body = payload if isinstance(payload, dict) else {}
    if not vault.ready():
        raise HTTPException(status_code=409, detail='storage_unavailable')
    wanted = [f for f in (body.get('files') or []) if isinstance(f, str)][:2000]
    paths = [(f, p) for f, p in ((f, _library_file(f)) for f in wanted) if p is not None and p.is_file()]
    if not paths:
        raise HTTPException(status_code=400, detail='no_files')
    if _details_lock is None:
        _details_lock = asyncio.Lock()
    root = Path(state.download_dir).resolve()
    providers_ = list(getattr(state.downloader, 'lyrics_providers', None) or [])

    async def run() -> None:
        async with _details_lock:
            updated = failed = 0
            reasons: dict[str, int] = {}
            for index, (rel, path) in enumerate(paths, 1):
                outcome, why = await asyncio.to_thread(details_mod.refresh, root, path, providers_)
                if outcome == details_mod.UPDATED:
                    updated += 1
                else:
                    failed += 1
                    reasons[why] = reasons.get(why, 0) + 1
                await state.connections.broadcast({
                    'type': 'details', 'file': rel, 'state': outcome,
                    'done': index, 'total': len(paths),
                })
                # The library shows each one as it lands, in batches.
                if outcome == details_mod.UPDATED and index % 10 == 0:
                    library_mod.invalidate_cache()
                    await state.connections.broadcast({'type': 'library_changed'})
            library_mod.invalidate_cache()
            await state.connections.broadcast({
                'type': 'details', 'finished': True,
                'updated': updated, 'failed': failed, 'reasons': reasons,
            })
            await state.connections.broadcast({'type': 'library_changed'})

    task = asyncio.create_task(run())
    task.add_done_callback(
        lambda t: t.cancelled() or not t.exception()
        or logger.opt(exception=t.exception()).error('details refresh crashed')
    )
    return {'queued': len(paths)}


@router.post('/api/artists-online/refresh')
async def refresh_artists_endpoint(
    payload: Optional[dict[str, Any]] = Body(None),
) -> dict[str, Any]:
    """Look artists up again: their picture and their online page.

    ``{"names": [...]}``, or every artist in the library when there are none.
    """

    body = payload if isinstance(payload, dict) else {}
    names = [n for n in (body.get('names') or []) if isinstance(n, str) and n.strip()]
    if not names:
        base = _require_download_dir()
        names = [a['name'] for a in await asyncio.to_thread(library_mod.artists, base)]
    for name in names:
        known = artist_links._links.get(library_mod.fold(name)) or {}
        if known.get('id'):
            explorer.forget_artist(known['id'])
    hints = await _artist_hints(names)
    await asyncio.to_thread(artist_links.relook, names, hints)
    links, pending = await asyncio.to_thread(artist_links.known, names, hints)
    return {'links': links, 'pending': pending}


async def _artist_hints(names: list[str]) -> dict[str, dict[str, list[str]]]:
    """What the songs in the library say about who each artist is."""

    base = state.download_dir
    if base is None:
        return {}
    try:
        return await asyncio.to_thread(library_mod.artist_hints, Path(base), names)
    except Exception:
        logger.opt(exception=True).debug('artist hints unavailable')
        return {}


# ---------------------------------------------------------------------------
# Problems: errors the window ran into, and a report to send (see report.py)
# ---------------------------------------------------------------------------

# The window's errors, newest last, for the report; and when each was logged,
# so a page stuck throwing on every frame cannot fill the log.
_window_errors: deque = deque(maxlen=40)
_window_error_times: deque = deque(maxlen=20)
WINDOW_ERRORS_PER_MINUTE = 20


@router.post('/api/client-error')
async def client_error_endpoint(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    now = time.time()
    message = str(payload.get('message') or 'error')[:500]
    stack = str(payload.get('stack') or '')[:4000]
    where = str(payload.get('route') or '')[:200]
    # The same error again soon after is counted, not written again.
    last = _window_errors[-1] if _window_errors else None
    if last and last['message'] == message and now - last['at'] < 60:
        last['times'] += 1
        return {'logged': False}
    while _window_error_times and now - _window_error_times[0] > 60:
        _window_error_times.popleft()
    if len(_window_error_times) >= WINDOW_ERRORS_PER_MINUTE:
        return {'logged': False}
    _window_error_times.append(now)
    _window_errors.append(
        {
            'at': now,
            'when': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)),
            'message': message,
            'stack': stack,
            'route': where,
            'times': 1,
        }
    )
    logger.bind(component='window').error('{} (on {})\n{}', message, where or '?', stack)
    return {'logged': True}


def _report_facts() -> dict[str, Any]:
    return {
        'Library folder': state.settings.get('download_dir') or state.download_dir or '',
        'Playlists': len(playlists_mod.all_playlists()),
        'Window errors this run': len(_window_errors),
    }


@router.get('/api/support/report/status')
async def support_report_status_endpoint() -> dict[str, Any]:
    """Whether reporting is open yet, and how many reports wait to go."""

    data = Path(state.data_dir) if state.data_dir else None
    return {
        'enabled': report_mod.enabled(),
        'pending': report_mod.pending(data) if data else 0,
        'categories': list(report_mod.CATEGORIES),
    }


@router.post('/api/support/report/send')
async def support_report_send_endpoint(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Send a problem report (see report.py): what the person wrote, and the
    diagnostics if they chose to include them. Queued when it cannot go now."""

    if not report_mod.enabled():
        raise HTTPException(status_code=503, detail='Reporting is not open yet')
    if not state.data_dir:
        raise HTTPException(status_code=503, detail='No data folder')
    try:
        fields = report_mod.clean_fields(
            payload.get('description'), payload.get('category'), payload.get('contact')
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data = Path(state.data_dir)
    report: dict[str, Any] = {'id': report_mod.new_id(), 'version': str(state.version or ''), **fields}
    if payload.get('include_diagnostics', True):
        log_file = os.getenv('DANNIFY_LOG_FILE')
        report['diagnostics'] = await asyncio.to_thread(
            report_mod.pack,
            data,
            report['version'],
            settings=dict(state.settings or {}),
            facts=_report_facts(),
            window_errors=list(_window_errors),
            log_file=Path(log_file) if log_file else None,
        )
    try:
        status = await asyncio.to_thread(report_mod.send, data, report)
    except report_mod.NotOpen as exc:
        raise HTTPException(status_code=503, detail='Reporting is not open yet') from exc
    logger.info('problem report {} {}', report['id'], status)
    return {'id': report['id'], 'status': status}


async def flush_reports() -> None:
    """At startup: reports that could not go before go now, and the zip
    files 4.3 and 4.4 saved for sending by hand are tidied away."""

    if not state.data_dir:
        return
    data = Path(state.data_dir)
    try:
        await asyncio.to_thread(report_mod.tidy_old_exports, data)
        if report_mod.enabled() and report_mod.pending(data):
            sent, left = await asyncio.to_thread(report_mod.flush, data)
            if sent:
                logger.info('sent {} waiting problem report(s); {} still waiting', sent, left)
    except Exception:
        logger.opt(exception=True).debug('could not send waiting reports')


# ---------------------------------------------------------------------------
# Playlists the listener makes (see playlists.py)
# ---------------------------------------------------------------------------


def _playlist_or_404(fn, *args):
    try:
        return fn(*args)
    except playlists_mod.NotFound as exc:
        raise HTTPException(status_code=404, detail='Playlist not found') from exc


@router.get('/api/playlists')
async def playlists_endpoint() -> dict[str, Any]:
    return {'playlists': playlists_mod.all_playlists()}


@router.post('/api/playlists')
async def playlist_create_endpoint(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    tracks = payload.get('tracks') if isinstance(payload.get('tracks'), list) else []
    try:
        return playlists_mod.create(str(payload.get('name') or ''), tracks)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get('/api/playlists/{pid}')
async def playlist_endpoint(pid: str) -> dict[str, Any]:
    return _playlist_or_404(playlists_mod.get, pid)


@router.patch('/api/playlists/{pid}')
async def playlist_update_endpoint(pid: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    if isinstance(payload.get('name'), str):
        _playlist_or_404(playlists_mod.rename, pid, payload['name'])
    if isinstance(payload.get('tracks'), list):
        return _playlist_or_404(playlists_mod.set_tracks, pid, payload['tracks'])
    return _playlist_or_404(playlists_mod.get, pid)


@router.post('/api/playlists/{pid}/tracks')
async def playlist_add_endpoint(pid: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    tracks = payload.get('tracks') if isinstance(payload.get('tracks'), list) else []
    position = payload.get('position')
    return _playlist_or_404(
        playlists_mod.add_tracks, pid, tracks, int(position) if isinstance(position, int) else None
    )


@router.delete('/api/playlists/{pid}')
async def playlist_delete_endpoint(pid: str) -> dict[str, Any]:
    _playlist_or_404(playlists_mod.delete, pid)
    return {'deleted': True}


@router.get('/api/artists-online/links')
async def artist_links_endpoint() -> dict[str, Any]:
    """The online identity (page id and picture) of every artist in the library.

    What is not known yet is looked up in the background; ``pending`` says how
    many, and asking again shortly picks them up.
    """

    base = _require_download_dir()
    names = [a['name'] for a in await asyncio.to_thread(library_mod.artists, base)]
    hints = await _artist_hints(names)
    links, pending = await asyncio.to_thread(artist_links.known, names, hints)
    return {'links': links, 'pending': pending}


@router.get('/api/artists-online/page')
async def artist_online_page_endpoint(name: str = Query(...)) -> dict[str, Any]:
    """Everything a saved artist has released, for the rest of their page."""

    hint = (await _artist_hints([name])).get(name)
    found = await asyncio.to_thread(artist_links.link, name, hint)
    if not found:
        raise HTTPException(status_code=404, detail='Artist not found online')
    try:
        page = await asyncio.to_thread(explorer.artist, found['id'])
    except Exception as exc:
        logger.opt(exception=True).info('online page for {} failed', name)
        raise HTTPException(status_code=502, detail='unavailable') from exc
    return page


# `:path`, because a name can hold a slash: "AC/DC" arrives as AC%2FDC and is
# decoded before routing, which a plain parameter does not match.
@router.get('/api/artists/{name:path}')
async def artist_detail_endpoint(name: str) -> dict[str, Any]:
    base = _require_download_dir()
    detail = await asyncio.to_thread(library_mod.artist_detail, base, name)
    if detail is None:
        raise HTTPException(status_code=404, detail='Artist not found')
    return detail


# ---------------------------------------------------------------------------
# Repairing saved tracks that will not play (see repair.py)
# ---------------------------------------------------------------------------


def _repair_context():
    base = state.download_dir
    if base is None:
        return None
    return Path(base), state.downloader, state.data_dir


def _repair_notify(message: dict[str, Any]) -> None:
    # Called from the repair threads; the sockets belong to the event loop.
    loop = state.loop
    if loop is None or loop.is_closed():
        return
    asyncio.run_coroutine_threadsafe(state.connections.broadcast(message), loop)


def _repair_changed() -> None:
    library_mod.invalidate_cache()
    _repair_notify({'type': 'library_changed'})


repair.jobs.configure(_repair_context, _repair_notify, _repair_changed)


@router.get('/api/library/repair')
def repair_status_endpoint() -> dict[str, Any]:
    return repair.jobs.status()


@router.post('/api/library/repair')
async def repair_endpoint(
    payload: Optional[dict[str, Any]] = Body(None),
) -> dict[str, Any]:
    """Download saved tracks again, in place.

    ``{"all": true}`` repairs every track the library finds a problem with.
    ``{"files": [...]}`` repairs those, and with ``"force": true`` does so even
    when nothing looks wrong: the player asks for that after a file failed to
    play for a reason the checks here cannot see.
    """

    body = payload if isinstance(payload, dict) else {}
    if not vault.ready():
        raise HTTPException(status_code=409, detail='unavailable')
    base = _require_download_dir()
    if body.get('all'):
        data = await asyncio.to_thread(library_mod.library, base)
        files = [tr['file'] for tr in data.get('tracks', []) if tr.get('problem')]
        force = False
    else:
        raw = body.get('files')
        files = (
            [f for f in raw if isinstance(f, str) and f.strip()]
            if isinstance(raw, list)
            else []
        )
        force = bool(body.get('force'))
    return await asyncio.to_thread(repair.jobs.add, files, force)


@router.post('/api/library/repair/stop')
def repair_stop_endpoint() -> dict[str, Any]:
    return repair.jobs.stop()


@router.websocket('/api/ws')
async def websocket_endpoint(
    ws: WebSocket, client_id: str = Query(...)
) -> None:
    await state.connections.connect(client_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        state.connections.disconnect(client_id, ws)
    except Exception:
        state.connections.disconnect(client_id, ws)


# ---------------------------------------------------------------------------
# Account (YouTube Music sign-in), personalized feeds and likes
# ---------------------------------------------------------------------------
@router.get('/api/account')
def account_status_endpoint() -> dict[str, Any]:
    return account.status()


@router.post('/api/account/signout')
async def account_signout_endpoint() -> dict[str, Any]:
    result = account.sign_out()
    explorer.clear_cache()
    return result


@router.get('/api/home')
async def home_endpoint(limit: int = Query(6)) -> dict[str, Any]:
    """The YouTube Music home feed: personalized once signed in."""

    try:
        sections = await asyncio.to_thread(explorer.home, limit)
    except Exception as exc:
        logger.opt(exception=True).info('home feed failed')
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {'sections': sections, 'signed_in': account.is_signed_in()}


@router.get('/api/liked')
async def liked_endpoint(limit: int = Query(250)) -> dict[str, Any]:
    if not account.is_signed_in():
        raise HTTPException(status_code=401, detail='Not signed in')
    try:
        songs = await asyncio.to_thread(account.liked_songs, limit)
    except Exception as exc:
        logger.opt(exception=True).info('liked songs failed')
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {'songs': songs}


@router.get('/api/library/playlists')
async def library_playlists_endpoint(limit: int = Query(50)) -> dict[str, Any]:
    if not account.is_signed_in():
        return {'playlists': []}
    try:
        playlists = await asyncio.to_thread(account.library_playlists, limit)
    except Exception:
        logger.opt(exception=True).debug('library playlists failed')
        playlists = []
    return {'playlists': playlists}


@router.get('/api/account/following')
async def account_following_endpoint() -> dict[str, Any]:
    if not account.is_signed_in():
        return {'artists': []}
    try:
        return {'artists': await asyncio.to_thread(account.subscriptions, 200)}
    except Exception:
        logger.opt(exception=True).debug('subscriptions failed')
        return {'artists': []}


@router.post('/api/account/follow')
async def account_follow_endpoint(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not account.is_signed_in():
        raise HTTPException(status_code=401, detail='Not signed in')
    try:
        return await asyncio.to_thread(
            account.follow, str(payload.get('channel_id') or ''), bool(payload.get('follow', True))
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.opt(exception=True).info('follow failed')
        raise HTTPException(status_code=502, detail='YouTube Music did not answer') from exc


@router.get('/api/account/history')
async def account_history_endpoint() -> dict[str, Any]:
    if not account.is_signed_in():
        return {'songs': []}
    try:
        return {'songs': await asyncio.to_thread(account.history)}
    except Exception:
        logger.opt(exception=True).debug('history failed')
        return {'songs': []}


@router.post('/api/account/history/add')
async def account_history_add_endpoint(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not account.is_signed_in():
        return {'added': False}
    try:
        added = await asyncio.to_thread(account.add_history, str(payload.get('video_id') or ''))
    except Exception:
        logger.opt(exception=True).debug('history item failed')
        added = False
    return {'added': added}


@router.post('/api/account/playlist/add')
async def account_playlist_add_endpoint(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not account.is_signed_in():
        raise HTTPException(status_code=401, detail='Not signed in')
    ids = payload.get('video_ids') if isinstance(payload.get('video_ids'), list) else []
    try:
        return await asyncio.to_thread(account.add_to_playlist, str(payload.get('playlist_id') or ''), ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.opt(exception=True).info('adding to a YouTube Music playlist failed')
        raise HTTPException(status_code=502, detail='YouTube Music did not take it') from exc


@router.post('/api/rate')
async def rate_endpoint(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Like / unlike a song on the signed-in YouTube Music account."""

    if not account.is_signed_in():
        raise HTTPException(status_code=401, detail='Not signed in')
    video_id = str(payload.get('video_id') or '').strip()
    liked = bool(payload.get('liked'))
    if not video_id:
        raise HTTPException(status_code=400, detail='video_id required')
    try:
        return await asyncio.to_thread(account.rate, video_id, liked)
    except Exception as exc:
        logger.opt(exception=True).info('rate failed')
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get('/api/radio')
async def radio_endpoint(
    video_id: str = Query(''), limit: int = Query(30)
) -> dict[str, Any]:
    """Endless mix for a track: powers autoplay when the queue runs out."""

    if not video_id:
        raise HTTPException(status_code=400, detail='video_id required')
    try:
        songs = await asyncio.to_thread(account.radio, video_id, limit)
    except Exception:
        logger.opt(exception=True).debug('radio failed for {}', video_id)
        songs = []
    return {'songs': songs}

# ---------------------------------------------------------------------------
# Support the app + in-app updates
# ---------------------------------------------------------------------------
@router.get('/api/support')
def support_config_endpoint() -> dict[str, Any]:
    return support.config()


@router.get('/api/update/check')
async def update_check_endpoint(force: int = Query(0)) -> dict[str, Any]:
    return await asyncio.to_thread(
        updates.check, state.version or '0.0.0', bool(force)
    )


@router.post('/api/update/download')
async def update_download_endpoint(
    payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    """Get the new version ready, streaming progress over the websocket.

    An installed copy builds the new version beside itself and the launcher
    swaps it in at the next start ('staged'). Anything else downloads the
    installer ('installer').
    """

    info = await asyncio.to_thread(updates.check, state.version or '0.0.0', False)
    loop = state.loop or asyncio.get_running_loop()

    def _progress(percent: float, stage: str = '', done: int = 0, total: int = 0) -> None:
        # A stage name and byte counts, not a sentence: the interface says it
        # in the user's language.
        asyncio.run_coroutine_threadsafe(
            state.connections.broadcast(
                {
                    'type': 'update_progress',
                    'progress': round(percent, 1),
                    'stage': stage,
                    'done': int(done or 0),
                    'total': int(total or 0),
                }
            ),
            loop,
        )

    if layout.managed() and info.get('package_url'):
        try:
            staged = await asyncio.to_thread(updates.stage, info, _progress)
        except Exception as exc:
            logger.opt(exception=True).info('update could not be prepared')
            raise HTTPException(status_code=502, detail='update_failed') from exc
        return {'path': str(staged), 'version': info.get('version', ''), 'kind': 'staged'}

    # Only ever the address the release itself names. The interface used to
    # be able to send one of its own, and whatever came back was offered to
    # run as the installer.
    url = str(info.get('download_url') or '')
    if not url:
        raise HTTPException(status_code=404, detail='no_download')
    dest = Path(state.data_dir or Path.home()) / 'updates'
    try:
        path = await asyncio.to_thread(
            updates.download,
            url,
            dest,
            _progress,
            str(info.get('version') or ''),
            str(info.get('installer_signature_url') or ''),
        )
    except Exception as exc:
        logger.opt(exception=True).info('update download failed')
        raise HTTPException(status_code=502, detail='update_failed') from exc
    return {
        'path': str(path),
        'version': info.get('version', ''),
        'kind': 'installer',
    }


@router.get('/api/update/status')
def update_status_endpoint() -> dict[str, Any]:
    """What the launcher and the last update left for the interface to say."""

    waiting = layout.pending()
    fresh = layout.just_updated()
    # A version the launcher had to take back out because it would not
    # start. It used to happen in silence: the update simply never arrived
    # and nobody knew why. Only while it is newer than what runs, so a later
    # release that did install puts an end to the message.
    bad = layout.skipped_version()
    rolled_back = (
        {'version': bad, 'running': state.version or ''}
        if bad and state.version and updates.is_newer(bad, state.version)
        else None
    )
    return {
        'managed': layout.managed(),
        'pending': {'version': str(waiting.get('version') or '')} if waiting else None,
        'just_updated': (
            {'version': state.version, 'notes': str(fresh.get('notes') or '')[:4000]}
            if fresh
            else None
        ),
        'rolled_back': rolled_back,
    }


@router.post('/api/update/acknowledge')
def update_acknowledge_endpoint() -> dict[str, Any]:
    """The "what is new" note was seen: do not show it again."""

    layout.acknowledge_update()
    return {'ok': True}


@router.post('/api/update/discard')
def update_discard_endpoint() -> dict[str, Any]:
    """Skipping a version also drops it if it was already waiting."""

    updates.discard_staged()
    return {'ok': True}
