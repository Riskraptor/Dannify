"""Playlists the listener makes: named lists of songs, in their order.

A song in a playlist is kept as what identifies it (its YouTube id, and its
file when it is saved) plus what is needed to show it (title, artists,
album, length, picture). A saved song plays from the library; one that is not
saved, or no longer is, plays from YouTube by its id. So a playlist survives
songs being deleted, re-downloaded or moved between folders.

Everything is in one small JSON file in the app's data folder, written whole
and atomically: a crash mid-write leaves the previous version, never half of
one.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Optional

from loguru import logger

_lock = threading.Lock()
_path: Optional[Path] = None
_data: dict[str, Any] = {'version': 1, 'playlists': []}

MAX_PLAYLISTS = 500
MAX_TRACKS = 5000
NAME_LIMIT = 120

_TEXT_FIELDS = ('video_id', 'file', 'title', 'album', 'album_id', 'cover_url')


class NotFound(KeyError):
    """No playlist with that id."""


def init(data_dir: Path) -> None:
    global _path, _data
    _path = Path(data_dir) / 'playlists.json'
    try:
        raw = json.loads(_path.read_text(encoding='utf-8'))
        if isinstance(raw, dict) and isinstance(raw.get('playlists'), list):
            with _lock:
                _data = {
                    'version': 1,
                    'playlists': [p for p in (_clean_playlist(x) for x in raw['playlists']) if p],
                }
    except FileNotFoundError:
        pass
    except Exception:
        logger.opt(exception=True).warning('playlists file unreadable; kept aside, starting empty')
        try:
            _path.replace(_path.with_suffix(f'.broken-{int(time.time())}.json'))
        except OSError:
            pass


def _save() -> None:
    if _path is None:
        return
    with _lock:
        text = json.dumps(_data, ensure_ascii=False)
    part = _path.with_name(_path.name + '.part')
    try:
        part.write_text(text, encoding='utf-8')
        os.replace(part, _path)
    except OSError:
        logger.opt(exception=True).warning('could not save playlists')


def clean_track(raw: Any) -> Optional[dict[str, Any]]:
    """A song as a playlist keeps it, from whatever the window sent."""

    if not isinstance(raw, dict):
        return None
    track: dict[str, Any] = {}
    for key in _TEXT_FIELDS:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            track[key] = value.strip()[:2000]
    artists = raw.get('artists')
    if isinstance(artists, list):
        track['artists'] = [str(a)[:200] for a in artists if isinstance(a, str) and a.strip()][:20]
    ids = raw.get('artist_ids')
    if isinstance(ids, list):
        track['artist_ids'] = [
            {'name': str(a['name'])[:200], 'id': str(a['id'])[:64]}
            for a in ids
            if isinstance(a, dict) and a.get('name') and a.get('id')
        ][:20]
    try:
        track['duration'] = max(0, int(float(raw.get('duration') or 0)))
    except (TypeError, ValueError):
        track['duration'] = 0
    # Something to play it by: a saved file, or a YouTube id.
    if not track.get('video_id') and not track.get('file'):
        return None
    track.setdefault('title', track.get('file', track.get('video_id', '')))
    return track


def _clean_playlist(raw: Any) -> Optional[dict[str, Any]]:
    if not isinstance(raw, dict) or not raw.get('id'):
        return None
    tracks = [t for t in (clean_track(x) for x in raw.get('tracks') or []) if t]
    return {
        'id': str(raw['id'])[:40],
        'name': (str(raw.get('name') or '').strip() or 'Playlist')[:NAME_LIMIT],
        'created': float(raw.get('created') or time.time()),
        'updated': float(raw.get('updated') or time.time()),
        'tracks': tracks[:MAX_TRACKS],
    }


def _summary(p: dict[str, Any]) -> dict[str, Any]:
    covers: list[str] = []
    for t in p['tracks']:
        cover = t.get('cover_url') or (('file:' + t['file']) if t.get('file') else '')
        if cover and cover not in covers:
            covers.append(cover)
        if len(covers) == 4:
            break
    return {
        'id': p['id'],
        'name': p['name'],
        'count': len(p['tracks']),
        'duration': sum(int(t.get('duration') or 0) for t in p['tracks']),
        'covers': covers,
        'updated': p['updated'],
    }


def _find(pid: str) -> dict[str, Any]:
    for p in _data['playlists']:
        if p['id'] == pid:
            return p
    raise NotFound(pid)


def all_playlists() -> list[dict[str, Any]]:
    with _lock:
        return [_summary(p) for p in _data['playlists']]


def get(pid: str) -> dict[str, Any]:
    with _lock:
        p = _find(pid)
        return {**_summary(p), 'tracks': [dict(t) for t in p['tracks']]}


def create(name: str, tracks: Optional[list[Any]] = None) -> dict[str, Any]:
    clean = [t for t in (clean_track(x) for x in tracks or []) if t][:MAX_TRACKS]
    now = time.time()
    p = {
        'id': secrets.token_hex(6),
        'name': (str(name or '').strip() or 'Playlist')[:NAME_LIMIT],
        'created': now,
        'updated': now,
        'tracks': clean,
    }
    with _lock:
        if len(_data['playlists']) >= MAX_PLAYLISTS:
            raise ValueError('too many playlists')
        _data['playlists'].append(p)
    _save()
    return get(p['id'])


def rename(pid: str, name: str) -> dict[str, Any]:
    with _lock:
        p = _find(pid)
        p['name'] = (str(name or '').strip() or p['name'])[:NAME_LIMIT]
        p['updated'] = time.time()
    _save()
    return get(pid)


def set_tracks(pid: str, tracks: list[Any]) -> dict[str, Any]:
    """Replace the songs, in the order given (a reorder, or several removed)."""

    clean = [t for t in (clean_track(x) for x in tracks or []) if t][:MAX_TRACKS]
    with _lock:
        p = _find(pid)
        p['tracks'] = clean
        p['updated'] = time.time()
    _save()
    return get(pid)


def add_tracks(pid: str, tracks: list[Any], position: Optional[int] = None) -> dict[str, Any]:
    clean = [t for t in (clean_track(x) for x in tracks or []) if t]
    with _lock:
        p = _find(pid)
        room = MAX_TRACKS - len(p['tracks'])
        clean = clean[: max(0, room)]
        at = len(p['tracks']) if position is None else max(0, min(int(position), len(p['tracks'])))
        p['tracks'][at:at] = clean
        p['updated'] = time.time()
        added = len(clean)
    _save()
    out = get(pid)
    out['added'] = added
    return out


def remove_tracks(pid: str, indices: list[int]) -> dict[str, Any]:
    drop = {int(i) for i in indices if isinstance(i, (int, float, str)) and str(i).lstrip('-').isdigit()}
    with _lock:
        p = _find(pid)
        p['tracks'] = [t for i, t in enumerate(p['tracks']) if i not in drop]
        p['updated'] = time.time()
    _save()
    return get(pid)


def delete(pid: str) -> None:
    with _lock:
        before = len(_data['playlists'])
        _data['playlists'] = [p for p in _data['playlists'] if p['id'] != pid]
        if len(_data['playlists']) == before:
            raise NotFound(pid)
    _save()
