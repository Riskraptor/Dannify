"""Who a saved artist is online: their YouTube Music page and their picture.

The library only knows a name, read off the tags. Its artist pages used to be
a list of downloaded songs and a button that searched for the name, and every
artist in the sidebar wore the cover of one of their albums. With a link to the
real artist, a page can carry on below the downloaded songs with everything
else they have released, and the picture can be the artist's own.

A name is looked up once and remembered on disk, found or not, so the network
is asked about each artist once, not on every start. Misses are tried again
after a week: a new artist may simply not have been indexed yet.
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from .library import _same_artist, fold

_RETRY_MISS = 7 * 24 * 3600

_lock = threading.Lock()
# One write of the file at a time: lookups finish on two threads at once.
_save_lock = threading.Lock()
_links: dict[str, dict[str, Any]] = {}
# The library's bucket for songs with no artist. Not an artist to look up: a
# real artist by that name would lend it their picture and their music.
_NOT_A_NAME = {'unknown artist', 'unknown', 'various artists'}
_path: Optional[Path] = None
_pending: set[str] = set()
# Two at a time: a library of a few hundred artists should fill in over a
# minute or two without looking like a flood to YouTube.
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='artist-link')


def init(data_dir: Path) -> None:
    global _path
    _path = Path(data_dir) / 'artist_links.json'
    try:
        raw = json.loads(_path.read_text(encoding='utf-8'))
        if isinstance(raw, dict):
            with _lock:
                _links.update({k: v for k, v in raw.items() if isinstance(v, dict)})
    except FileNotFoundError:
        pass
    except Exception:
        logger.opt(exception=True).debug('artist links unreadable; starting afresh')


def clear() -> None:
    """Forget every artist's link and picture; they are found again."""

    with _lock:
        _links.clear()
    _save()


def _save() -> None:
    if _path is None:
        return
    with _save_lock:
        with _lock:
            snapshot = dict(_links)
        try:
            part = _path.with_name(_path.name + '.part')
            part.write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf-8')
            os.replace(part, _path)
        except OSError:
            logger.opt(exception=True).debug('could not save artist links')


def _pick(name: str, found: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The search result that is this artist, or None rather than a guess."""

    want = fold(name)
    cards = [a for a in found if a.get('browse_id') and a.get('name')]
    for card in cards:
        if fold(card['name']) == want:
            return card
    # A spelling apart ("Stephen Kasolo" and "Stephen Kasolo Kitole") only
    # when it is the first result: that is the one YouTube thinks was meant.
    if cards and _same_artist(cards[0]['name'], name):
        return cards[0]
    return None


def _look_up(name: str) -> dict[str, Any]:
    from . import explorer  # noqa: PLC0415  (imports ytmusicapi)

    try:
        found = explorer.search_artists(name, 6)
    except Exception:
        logger.opt(exception=True).debug('artist lookup failed for {}', name)
        return {}  # offline or refused: not a miss, try again next time
    card = _pick(name, found)
    if card is None:
        return {'id': '', 'photo': '', 'name': '', 't': time.time()}
    return {
        'id': card['browse_id'],
        'photo': card.get('cover_url') or '',
        'name': card['name'],
        't': time.time(),
    }


def _fresh(entry: Optional[dict[str, Any]]) -> bool:
    if not entry:
        return False
    if entry.get('id'):
        return True
    return time.time() - float(entry.get('t') or 0) < _RETRY_MISS


def link(name: str) -> Optional[dict[str, Any]]:
    """``{id, photo, name}`` for *name*, looking it up now if need be."""

    key = fold(name)
    if not key or key in _NOT_A_NAME:
        return None
    with _lock:
        entry = _links.get(key)
    if not _fresh(entry):
        entry = _look_up(name)
        if entry:
            with _lock:
                _links[key] = entry
            _save()
    return entry if entry and entry.get('id') else None


def known(names: list[str]) -> tuple[dict[str, dict[str, str]], int]:
    """What is already known about *names*, and how many are still coming.

    The ones not known yet are looked up in the background; asking again a
    little later picks them up.
    """

    out: dict[str, dict[str, str]] = {}
    missing: list[tuple[str, str]] = []
    with _lock:
        for name in names:
            key = fold(name)
            if not key or key in _NOT_A_NAME:
                continue
            entry = _links.get(key)
            if _fresh(entry):
                if entry.get('id'):
                    out[name] = {'id': entry['id'], 'photo': entry.get('photo') or ''}
            elif key not in _pending:
                _pending.add(key)
                missing.append((key, name))
            else:
                missing.append((key, ''))
    for key, name in missing:
        if name:
            _pool.submit(_fill, key, name)
    return out, len(missing)


def _fill(key: str, name: str) -> None:
    try:
        entry = _look_up(name)
        if entry:
            with _lock:
                _links[key] = entry
            _save()
    finally:
        with _lock:
            _pending.discard(key)
