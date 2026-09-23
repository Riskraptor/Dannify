"""FastAPI router exposed by Dannify.

The endpoints intentionally mirror the surface that the previous
``spotdl``-powered backend exposed so the existing Vue frontend keeps
working without changes:

* ``GET  /api/version``
* ``GET  /api/songs/search``
* ``GET  /api/song/url`` and ``GET /api/url`` (alias)
* ``POST /api/download/url`` (optional JSON body: resolved Spotify row so
  ``track_number`` / ``album_track_total`` survive re-fetch by URL)
* ``POST /api/playlist/m3u``
* ``GET  /api/settings``
* ``POST /api/settings/update``
* ``WS   /api/ws``
* ``GET  /api/check_update``
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
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
from fastapi.responses import HTMLResponse, StreamingResponse
from loguru import logger

from . import account
from . import library as library_mod
from . import lyrics as lyrics_mod
from . import lyrics_index
from . import lyrics_offsets
from . import lyrics_publish
from . import explorer
from . import m3u, providers, spotify, streaming, support, updates
from .downloader import Downloader
from .monitor import PlaylistMonitorDB, check_playlist

DEFAULT_SETTINGS: dict[str, Any] = {
    'audio_providers': ['youtube-music'],
    'lyrics_providers': ['lrclib'],
    'download_lyrics': True,
    'format': 'mp3',
    'bitrate': '320',
    'output': '{artists} - {title}.{output-ext}',
    'generate_m3u': True,
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

    async def connect(self, client_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._clients[client_id] = ws

    def disconnect(self, client_id: str) -> None:
        self._clients.pop(client_id, None)

    async def send(self, client_id: str, message: dict[str, Any]) -> None:
        ws = self._clients.get(client_id)
        if ws is None:
            return
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            self._clients.pop(client_id, None)

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead: list[str] = []
        for client_id, ws in list(self._clients.items()):
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(client_id)
        for client_id in dead:
            self._clients.pop(client_id, None)


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
    monitor_db: Optional[PlaylistMonitorDB] = None
    download_jobs: dict[str, dict[str, Any]] = {}
    download_semaphore: Optional[asyncio.Semaphore] = None
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


@router.get('/api/check_update')
def check_update() -> Optional[dict[str, Any]]:
    return None


@router.get('/api/songs/search')
async def search_endpoint(query: str = Query('')) -> list[dict[str, Any]]:
    return await asyncio.to_thread(providers.search_songs, query, 20)


@router.get('/api/song/url')
async def song_url_endpoint(url: str = Query(...)):
    return await asyncio.to_thread(_resolve_url, url)


@router.get('/api/url')
async def url_endpoint(url: str = Query(...)):
    return await asyncio.to_thread(_resolve_url, url)


def _resolve_url(url: str):
    parsed = spotify.parse_spotify_url(url)
    if parsed is None:
        raise HTTPException(status_code=400, detail='Invalid Spotify URL')
    kind, sid = parsed
    try:
        if kind == 'track':
            return spotify.track_from_id(sid)
        if kind == 'album':
            return spotify.album_tracks_from_id(sid)
        if kind == 'playlist':
            return spotify.playlist_tracks_from_id(sid)
    except Exception as exc:
        logger.exception('Failed to resolve Spotify URL {}', url)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise HTTPException(
        status_code=400, detail=f'Unsupported entity type: {kind}'
    )


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


def _register_job(song: dict[str, Any], status: str = 'queued') -> str:
    song_id = str(song.get('song_id') or song.get('url') or id(song))
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
    job = state.download_jobs.get(song_id)
    if job is None:
        song_id = _register_job(song, status='downloading')
        job = state.download_jobs[song_id]
    else:
        job['status'] = 'downloading'

    await state.connections.broadcast({
        'song': song,
        'progress': 0,
        'message': '',
        'status': 'downloading',
    })

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
            filename = await loop.run_in_executor(
                None,
                lambda: state.downloader.download(
                    song, progress, subdir=subdir
                ),
            )
    except Exception as exc:
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
    song_id = _register_job(song, status='downloading')

    try:
        filename = await _run_download(song, song_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return filename


async def _process_batch(
    songs: list[dict[str, Any]],
    job_ids: list[str],
    playlist_url: str,
    generate_m3u: bool,
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

    async def _bounded(song: dict[str, Any], song_id: str) -> dict[str, Any]:
        try:
            filename = await _run_download(
                song, song_id, subdir=playlist_subdir
            )
        except Exception:
            filename = None
        return {'song': song, 'filename': filename}

    results = await asyncio.gather(
        *[_bounded(s, sid) for s, sid in zip(songs, job_ids)],
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
    generate_m3u = bool(payload.get('generate_m3u', True))

    valid_songs: list[dict[str, Any]] = []
    job_ids: list[str] = []
    for song in songs:
        if not isinstance(song, dict):
            continue
        song_id = _register_job(song, status='queued')
        valid_songs.append(song)
        job_ids.append(song_id)
        await state.connections.broadcast({
            'song': song,
            'progress': 0,
            'message': '',
            'status': 'queued',
        })

    if not valid_songs:
        raise HTTPException(status_code=400, detail='No valid songs in batch')

    task = asyncio.create_task(
        _process_batch(valid_songs, job_ids, playlist_url, generate_m3u)
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
    state.download_jobs.clear()
    return {'cleared': True}


@router.delete('/api/queue/item')
def remove_queue_item(song_id: str = Query(...)) -> dict:
    if song_id in state.download_jobs:
        del state.download_jobs[song_id]
        return {'removed': True}
    return {'removed': False}


@router.post('/api/playlist/m3u')
async def write_playlist_m3u_endpoint(request: Request) -> dict[str, Any]:
    """Write an M3U for the playlist after the per-track downloads.

    The frontend POSTs ``{playlist_url, tracks: [{filename, title,
    artist, duration}, ...]}``. The playlist name is resolved
    server-side via :func:`spotify.playlist_info_and_tracks` so the
    existing ``/api/song/url`` shape stays untouched.
    """

    if state.downloader is None:
        raise HTTPException(status_code=500, detail='Downloader not ready')
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail='Invalid JSON') from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail='Invalid payload')

    playlist_url = str(payload.get('playlist_url') or '').strip()
    if not playlist_url:
        raise HTTPException(status_code=400, detail='Missing playlist_url')
    parsed = spotify.parse_spotify_url(playlist_url)
    if parsed is None or parsed[0] != 'playlist':
        raise HTTPException(
            status_code=400, detail='Not a Spotify playlist URL'
        )

    tracks = payload.get('tracks') or []
    if not isinstance(tracks, list):
        raise HTTPException(status_code=400, detail='tracks must be a list')

    try:
        playlist_name, _ = await asyncio.to_thread(
            spotify.playlist_info_and_tracks, parsed[1]
        )
    except Exception as exc:
        logger.exception('Failed to resolve playlist {}', playlist_url)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    entries = [t for t in tracks if isinstance(t, dict)]
    playlist_subdir = m3u.sanitize_playlist_name(playlist_name)
    organize = bool(state.downloader and state.downloader.organize_by_artist)
    target, kept = m3u.write_m3u(
        state.downloader.download_dir,
        playlist_name,
        entries,
        playlist_subdir=None if organize else playlist_subdir,
    )
    if target is None:
        raise HTTPException(
            status_code=400, detail='No tracks resolved to a file on disk'
        )
    return {'path': str(target), 'count': kept}


# Settings the interface has no business seeing. Where lyrics come from is an
# implementation detail: there is no picker for it, nothing renders it, and a
# name travelling to the UI is a name that ends up in the shipped bundle.
_PRIVATE_SETTINGS = ('lyrics_providers', 'audio_providers')


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
        if 'download_dir' in payload:
            new_dir = _coerce_download_dir(payload['download_dir'])
            if new_dir is not None:
                state.download_dir = new_dir
                if state.downloader is not None:
                    state.downloader.download_dir = new_dir
                    new_dir.mkdir(parents=True, exist_ok=True)
                # Re-point the central lyrics index at the new folder
                # (no-op if storage mode is 'sidecar', it just exists).
                lyrics_index.init(new_dir)
                # Drop the library cache so the new location is scanned.
                library_mod.invalidate_cache()
                state.settings['download_dir'] = str(new_dir)
                # Broadcast so the frontend re-loads its library index.
                if state.loop is not None:
                    asyncio.run_coroutine_threadsafe(
                        state.connections.broadcast(
                            {'type': 'library_changed'}
                        ),
                        state.loop,
                    )

        if 'lyrics_storage' in payload:
            mode = str(payload['lyrics_storage']).strip().lower()
            if mode in ('sidecar', 'central'):
                state.settings['lyrics_storage'] = mode

        for key, value in payload.items():
            if key in ('download_dir', 'lyrics_storage'):
                continue  # already handled above
            if key in DEFAULT_SETTINGS:
                state.settings[key] = value
        if state.downloader is not None:
            fmt = payload.get('format')
            if isinstance(fmt, str) and fmt:
                state.downloader.audio_format = fmt
            bitrate = payload.get('bitrate')
            if isinstance(bitrate, str) and bitrate:
                state.downloader.audio_bitrate = bitrate
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
                state.download_semaphore = asyncio.Semaphore(count)
            except (TypeError, ValueError):
                pass
    if state.settings_path is not None:
        _save_settings(state.settings_path, state.settings)
    return state.settings


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
    except Exception as exc:
        logger.exception('explore search failed for {}', q)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get('/api/explore/artist')
async def explore_artist_endpoint(id: str = Query(...)) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(explorer.artist, id)
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


def _lyrics_from_file(file: str, refresh: bool = False) -> dict[str, Any]:
    """Read synced/plain lyrics from a downloaded file's .lrc or tags.

    When *refresh* is True the local ``.lrc``/embedded copies are skipped and
    fresh lyrics are fetched online (and re-saved), so the reload button always
    re-queries the source.
    """

    base = state.download_dir
    if base is None:
        raise HTTPException(status_code=500, detail='Library not ready')
    base = base.resolve()
    try:
        full = (base / file).resolve()
        full.relative_to(base)
    except (ValueError, RuntimeError):
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

    # Fall back to embedded plain lyrics via mutagen.
    plain = None
    try:
        from mutagen import File as MutagenFile  # local import

        audio = MutagenFile(str(full))
        if audio is not None and audio.tags is not None:
            for key in ('USLT::eng', 'USLT::XXX', '\xa9lyr', 'lyrics'):
                val = audio.tags.get(key)
                if val:
                    plain = str(
                        getattr(val, 'text', None)
                        or (val[0] if isinstance(val, list) else val)
                    )
                    break
            if plain is None:
                for k in audio.tags.keys():
                    if 'USLT' in str(k):
                        plain = str(audio.tags[k].text)
                        break
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
        if song['name'] and song['artists']:
            raw = lyrics_mod.fetch(
                song, _effective_lyrics_providers(state.settings) or ['lrclib']
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
            _lyrics_from_file, file, bool(refresh)
        )
        # Attach the crowd-sourced prefs using the file's own tags.
        try:
            meta = library_mod._read_tags((state.download_dir / file))
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
    if file and state.download_dir is not None:
        try:
            meta = library_mod._read_tags((state.download_dir / file))
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


@router.get('/api/artists/{name}')
async def artist_detail_endpoint(name: str) -> dict[str, Any]:
    base = _require_download_dir()
    detail = await asyncio.to_thread(library_mod.artist_detail, base, name)
    if detail is None:
        raise HTTPException(status_code=404, detail='Artist not found')
    return detail


@router.websocket('/api/ws')
async def websocket_endpoint(
    ws: WebSocket, client_id: str = Query(...)
) -> None:
    await state.connections.connect(client_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        state.connections.disconnect(client_id)
    except Exception:
        state.connections.disconnect(client_id)


# ---------------------------------------------------------------------------
# Playlist monitoring endpoints
# ---------------------------------------------------------------------------


def _require_monitor_db() -> PlaylistMonitorDB:
    if state.monitor_db is None:
        raise HTTPException(
            status_code=500, detail='Monitor database not ready'
        )
    return state.monitor_db


@router.get('/api/monitor/playlists')
async def list_monitor_playlists() -> list[dict[str, Any]]:
    db = _require_monitor_db()
    playlists = await asyncio.to_thread(db.list_playlists)
    return [p.to_dict() for p in playlists]


@router.post('/api/monitor/playlists')
async def add_monitor_playlist(request: Request) -> dict[str, Any]:
    db = _require_monitor_db()
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    url = payload.get('url', '')
    interval_minutes = int(payload.get('interval_minutes', 60))

    parsed = spotify.parse_spotify_url(url)
    if parsed is None or parsed[0] != 'playlist':
        raise HTTPException(
            status_code=400, detail='A valid Spotify playlist URL is required'
        )

    _, spotify_id = parsed

    existing = await asyncio.to_thread(db.get_by_spotify_id, spotify_id)
    if existing is not None:
        raise HTTPException(
            status_code=409, detail='This playlist is already being monitored'
        )

    try:
        name, _tracks = await asyncio.to_thread(
            spotify.playlist_info_and_tracks, spotify_id
        )
    except Exception as exc:
        logger.exception('Failed to resolve playlist {}', spotify_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    playlist = await asyncio.to_thread(
        db.add_playlist, spotify_id, name, url, interval_minutes
    )

    # Kick off the first download pass immediately so the user does not have
    # to wait up to a full monitor sweep interval for the initial backfill.
    if state.downloader is not None:
        loop = state.loop or asyncio.get_running_loop()

        async def _initial_check(pl=playlist) -> None:
            try:
                await check_playlist(
                    pl,
                    db,
                    state.downloader,  # type: ignore[arg-type]
                    state.connections.broadcast,
                    loop,
                    state.settings,
                )
            except Exception:
                logger.exception('Initial check failed for playlist {}', pl.id)

        asyncio.create_task(_initial_check())

    return playlist.to_dict()


@router.patch('/api/monitor/playlists/{playlist_id}')
async def update_monitor_playlist(
    playlist_id: int, request: Request
) -> dict[str, Any]:
    db = _require_monitor_db()
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    kwargs: dict[str, Any] = {}
    if 'interval_minutes' in payload:
        kwargs['interval_minutes'] = int(payload['interval_minutes'])
    if 'enabled' in payload:
        kwargs['enabled'] = bool(payload['enabled'])

    updated = await asyncio.to_thread(
        db.update_playlist, playlist_id, **kwargs
    )
    if updated is None:
        raise HTTPException(
            status_code=404, detail='Monitored playlist not found'
        )
    return updated.to_dict()


@router.delete('/api/monitor/playlists/{playlist_id}')
async def delete_monitor_playlist(playlist_id: int) -> dict[str, Any]:
    db = _require_monitor_db()
    deleted = await asyncio.to_thread(db.delete_playlist, playlist_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail='Monitored playlist not found'
        )
    return {'deleted': True, 'id': playlist_id}


@router.post('/api/monitor/playlists/{playlist_id}/check')
async def manual_check_playlist(playlist_id: int) -> dict[str, Any]:
    db = _require_monitor_db()
    playlist = await asyncio.to_thread(db.get_playlist, playlist_id)
    if playlist is None:
        raise HTTPException(
            status_code=404, detail='Monitored playlist not found'
        )
    if state.downloader is None:
        raise HTTPException(status_code=500, detail='Downloader not ready')

    loop = state.loop or asyncio.get_running_loop()

    async def _run() -> None:
        try:
            count = await check_playlist(
                playlist,  # type: ignore[arg-type]
                db,
                state.downloader,  # type: ignore[arg-type]
                state.connections.broadcast,
                loop,
            )
            logger.info(
                'Manual check: downloaded {} new track(s) from "{}"',
                count,
                playlist.name,
            )  # type: ignore[union-attr]
        except Exception:
            logger.exception(
                'Manual check failed for playlist {}', playlist_id
            )

    asyncio.create_task(_run())
    return {'status': 'check_started', 'id': playlist_id}

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
# Support the app (Paystack) + in-app updates
# ---------------------------------------------------------------------------
@router.get('/api/support')
def support_config_endpoint() -> dict[str, Any]:
    return support.config()


@router.get('/support/checkout')
def support_checkout_endpoint() -> HTMLResponse:
    """Paystack Inline checkout page (opened in its own window)."""

    return HTMLResponse(support.CHECKOUT_HTML)


@router.get('/api/update/check')
async def update_check_endpoint(force: int = Query(0)) -> dict[str, Any]:
    return await asyncio.to_thread(
        updates.check, state.version or '0.0.0', bool(force)
    )


@router.post('/api/update/download')
async def update_download_endpoint(
    payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    """Fetch the installer, streaming progress over the websocket."""

    info = await asyncio.to_thread(updates.check, state.version or '0.0.0', False)
    url = str(payload.get('url') or info.get('download_url') or '')
    if not url:
        raise HTTPException(status_code=404, detail='No installer in the latest release')

    loop = state.loop or asyncio.get_running_loop()

    def _progress(percent: float) -> None:
        asyncio.run_coroutine_threadsafe(
            state.connections.broadcast(
                {'type': 'update_progress', 'progress': round(percent, 1)}
            ),
            loop,
        )

    dest = Path(state.data_dir or Path.home()) / 'updates'
    try:
        path = await asyncio.to_thread(updates.download, url, dest, _progress)
    except Exception as exc:
        logger.opt(exception=True).info('update download failed')
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {'path': str(path), 'version': info.get('version', '')}
