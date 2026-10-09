"""Saving songs: single and batch downloads, and the download queue."""

from __future__ import annotations

import asyncio
import contextlib
import re
import threading
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
from loguru import logger

from .. import library as library_mod
from .. import m3u, providers, spotify
from .common import state

router = APIRouter()

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
