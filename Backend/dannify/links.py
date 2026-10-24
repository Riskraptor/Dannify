"""Songs from a pasted link, made playable: each Spotify song paired with the
same song on YouTube Music, which is what Dannify plays and saves.

A playlist of a hundred songs is a hundred searches, so they are made a few
at a time, as the page asks for them, and remembered: opening the same
playlist again, or another with the same songs in it, asks for none twice.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from loguru import logger

from . import providers

# At most this many songs in one request: the page asks again for more.
MATCH_BATCH = 25
# Searches at once. YouTube Music answers a handful in parallel well; more
# only queues up behind them.
MATCH_WORKERS = 6
# Pairs found, remembered. A song not found is not: offline, or with YouTube
# Music not answering, every search finds nothing, and that must not stick.
_KEEP = 4000

_cache: "OrderedDict[str, tuple[float, Optional[dict[str, Any]]]]" = OrderedDict()
_lock = threading.Lock()


def _key(track: dict[str, Any]) -> str:
    sid = str(track.get('song_id') or '').strip()
    if sid:
        return 'spotify:' + sid
    artists = track.get('artists') or []
    who = ' '.join(a if isinstance(a, str) else str(a.get('name', '')) for a in artists)
    return 'text:' + ' '.join(f"{who} {track.get('name', '')}".lower().split())


def _remembered(key: str) -> tuple[bool, Optional[dict[str, Any]]]:
    with _lock:
        hit = _cache.get(key)
        if not hit:
            return False, None
        _, song = hit
        _cache.move_to_end(key)
        return True, song


def _remember(key: str, song: dict[str, Any]) -> None:
    with _lock:
        _cache[key] = (time.time(), song)
        _cache.move_to_end(key)
        while len(_cache) > _KEEP:
            _cache.popitem(last=False)


def _clean(track: dict[str, Any]) -> dict[str, Any]:
    artists = track.get('artists') or []
    if isinstance(artists, str):
        artists = [artists]
    return {
        'song_id': str(track.get('song_id') or '')[:64],
        'name': str(track.get('name') or '')[:200],
        'artists': [str(a if isinstance(a, str) else a.get('name', ''))[:120] for a in artists][:8],
        'duration': int(track.get('duration') or 0),
        'album_name': str(track.get('album_name') or '')[:200],
    }


def _match_one(track: dict[str, Any]) -> Optional[dict[str, Any]]:
    try:
        video_id, best = providers.find_match(track)
    except Exception:
        logger.opt(exception=True).info('link match failed for {!r}', track.get('name'))
        return None
    if not video_id or not best:
        return None
    song = providers._result_to_song(best)
    if not song:
        return None
    # The song as Spotify names it, where YouTube Music's own name is
    # missing: the pair is still the same song.
    song['name'] = song.get('name') or track['name']
    song['spotify_id'] = track['song_id']
    return song


def match(tracks: list[dict[str, Any]]) -> list[Optional[dict[str, Any]]]:
    """For each track, the same song on YouTube Music, or None when there is
    none. In the order given; at most ``MATCH_BATCH`` at a time."""

    wanted = [_clean(t) for t in tracks[:MATCH_BATCH] if isinstance(t, dict)]
    out: list[Optional[dict[str, Any]]] = [None] * len(wanted)
    todo: list[int] = []
    for i, track in enumerate(wanted):
        known, song = _remembered(_key(track))
        if known:
            out[i] = song
        elif track['name']:
            todo.append(i)
    if todo:
        with ThreadPoolExecutor(max_workers=min(MATCH_WORKERS, len(todo))) as pool:
            results = list(pool.map(lambda i: _match_one(wanted[i]), todo))
        for i, song in zip(todo, results):
            out[i] = song
            if song is not None:
                _remember(_key(wanted[i]), song)
    return out

