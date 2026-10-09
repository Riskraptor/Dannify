"""Health, connectivity, storage, problem reports and the live websocket."""

from __future__ import annotations

import asyncio
import os
import time
import contextlib
from collections import deque
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, WebSocket, WebSocketDisconnect
from loguru import logger

from .. import library as library_mod
from .. import lyrics as lyrics_mod
from .. import artist_links
from .. import playlists as playlists_mod
from .. import report as report_mod
from .. import streaming, support, vault
from .common import state
from .library import _require_download_dir

router = APIRouter()

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
# Support the app + in-app updates
# ---------------------------------------------------------------------------
@router.get('/api/support')
def support_config_endpoint() -> dict[str, Any]:
    return support.config()
