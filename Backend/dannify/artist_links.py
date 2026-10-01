"""Who a saved artist is online: their YouTube Music page and their picture.

The library only knows a name, read off the tags. Its artist pages used to be
a list of downloaded songs and a button that searched for the name, and every
artist in the sidebar wore the cover of one of their albums. With a link to the
real artist, a page can carry on below the downloaded songs with everything
else they have released, and the picture can be the artist's own.

A name is looked up once and remembered on disk, found or not, so the network
is asked about each artist once, not on every start. Misses are tried again
after a week: a new artist may simply not have been indexed yet.

Who an artist is comes from their songs first and their name last. A song
saved now records the id of every artist it credits; an older one is asked
about by its video id, which YouTube answers with the same ids. Only an
artist none of whose songs can say is searched for by name, because a name
is not a person: two channels called "Mavokali" came back for that one, and
the first, picked before, was a channel of videos with no songs, not the one
that released the songs in the library.
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
# Entries written before the songs were asked who they credit carry no
# version. They are looked up again once, the old answer standing meanwhile.
_VERSION = 2

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


def relook(names: list[str], hints: Optional[dict[str, dict[str, list[str]]]] = None) -> int:
    """Look these artists up again, in the background.

    What is known stays in place until the new answer arrives. Dropping it
    first sent every avatar back to an album cover for the seconds the lookup
    took, and then to the new photo: a flicker for a button that was meant to
    make things look right.
    """

    todo = []
    with _lock:
        for name in names:
            key = fold(name)
            if not key or key in _NOT_A_NAME or key in _pending:
                continue
            _pending.add(key)
            todo.append((key, name))
    for key, name in todo:
        _pool.submit(_fill, key, name, (hints or {}).get(name))
    return len(todo)


def forget(names: list[str]) -> None:
    """Look these artists up again (their picture or page changed)."""

    with _lock:
        for name in names:
            _links.pop(fold(name), None)
    _save()


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


def _credited(name: str, credits: list[dict[str, str]]) -> str:
    want = fold(name)
    for a in credits:
        if a.get('id') and fold(a.get('name') or '') == want:
            return a['id']
    for a in credits:
        if a.get('id') and _same_artist(a.get('name') or '', name):
            return a['id']
    return ''


def _look_up(name: str, hint: Optional[dict[str, list[str]]] = None) -> dict[str, Any]:
    from . import explorer  # noqa: PLC0415  (imports ytmusicapi)

    hint = hint or {}
    try:
        ident = next(iter(hint.get('ids') or []), '')
        for video_id in (hint.get('videos') or [])[:3]:
            if ident:
                break
            ident = _credited(name, explorer.artists_of_video(video_id))
        if ident:
            try:
                brief = explorer.artist_brief(ident)
            except (KeyError, IndexError, TypeError, ValueError, AttributeError):
                brief = {}  # a page this cannot read: the id still stands
            return {
                'id': ident,
                'photo': brief.get('cover_url') or '',
                'name': brief.get('name') or name,
                't': time.time(),
                'v': _VERSION,
                'src': 'songs',
            }
        found = explorer.search_artists(name, 6)
    except Exception:
        logger.opt(exception=True).debug('artist lookup failed for {}', name)
        return {}  # offline or refused: not a miss, try again next time
    card = _pick(name, found)
    if card is None:
        return {'id': '', 'photo': '', 'name': '', 't': time.time(), 'v': _VERSION}
    return {
        'id': card['browse_id'],
        'photo': card.get('cover_url') or '',
        'name': card['name'],
        't': time.time(),
        'v': _VERSION,
        'src': 'name',
    }


def _fresh(entry: Optional[dict[str, Any]]) -> bool:
    if not entry:
        return False
    if entry.get('id'):
        return True
    return time.time() - float(entry.get('t') or 0) < _RETRY_MISS


def _outdated(entry: dict[str, Any], hint: Optional[dict[str, list[str]]]) -> bool:
    """An answer the songs now contradict, or one from before they were asked."""

    if not hint:
        return False
    ids = hint.get('ids') or []
    if ids and entry.get('id') not in ids:
        return True  # the songs credit someone else by this name
    return int(entry.get('v') or 1) < _VERSION and bool(ids or hint.get('videos'))


def link(name: str, hint: Optional[dict[str, list[str]]] = None) -> Optional[dict[str, Any]]:
    """``{id, photo, name}`` for *name*, looking it up now if need be."""

    key = fold(name)
    if not key or key in _NOT_A_NAME:
        return None
    with _lock:
        entry = _links.get(key)
    if not _fresh(entry) or _outdated(entry, hint):
        found = _look_up(name, hint)
        if found:
            entry = found
            with _lock:
                _links[key] = entry
            _save()
    return entry if entry and entry.get('id') else None


def known(
    names: list[str], hints: Optional[dict[str, dict[str, list[str]]]] = None,
) -> tuple[dict[str, dict[str, str]], int]:
    """What is already known about *names*, and how many are still coming.

    The ones not known yet are looked up in the background; asking again a
    little later picks them up. *hints* is what each artist's songs say about
    who they are (see library.artist_hints): an answer they contradict is
    looked up again, and stands until the new one is in.
    """

    hints = hints or {}
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
                if key in _pending:
                    missing.append((key, ''))  # being looked up again: still coming
                elif _outdated(entry, hints.get(name)):
                    _pending.add(key)
                    missing.append((key, name))
            elif key not in _pending:
                _pending.add(key)
                missing.append((key, name))
            else:
                missing.append((key, ''))
    for key, name in missing:
        if name:
            _pool.submit(_fill, key, name, hints.get(name))
    return out, len(missing)


def _fill(key: str, name: str, hint: Optional[dict[str, list[str]]] = None) -> None:
    try:
        entry = _look_up(name, hint)
        if entry:
            with _lock:
                _links[key] = entry
            _save()
    finally:
        with _lock:
            _pending.discard(key)
