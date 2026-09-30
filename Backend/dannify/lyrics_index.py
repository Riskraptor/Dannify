"""Central lyrics storage with a fast (artist|title) index.

When the user picks ``lyrics_storage = 'central'`` we put every ``.lrc`` in
``<download_dir>/.lyrics/`` and maintain a small JSON index so we can
locate the file for any song instantly: even after the audio is moved,
renamed, or before any audio is downloaded at all.

The index key is a normalized ``artist|title`` pair (same normalisation
as :mod:`library`'s search keys: lowercase, alphanumeric + space only).
That makes it tolerant of casing, punctuation, and feat. artists in the
file name while still being O(1) to look up.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Iterable, Optional

from loguru import logger


_lock = threading.Lock()
_index: dict[str, str] = {}  # key -> relative .lrc filename within base
_index_path: Optional[Path] = None  # JSON sidecar (lives next to .lyrics/)
_lyrics_base: Optional[Path] = None  # the .lyrics folder itself

_FS_INVALID = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _norm(text: str) -> str:
    # Letters in any script: the a-to-z version gave every non-Latin song the
    # same empty key, and showed one song's lyrics on another.
    from .library import fold  # noqa: PLC0415

    return fold(text)


def _key(artist: str, title: str) -> str:
    return f'{_norm(artist)}|{_norm(title)}'


def _safe_filename(stem: str) -> str:
    """Filesystem-safe ``stem`` with a length cap (Windows MAX_PATH friendly)."""
    cleaned = _FS_INVALID.sub('', stem or '').strip().strip('.') or 'lyrics'
    return cleaned[:140]


def init(download_dir: Path) -> None:
    """Configure the central store under ``<download_dir>/.lyrics``.

    Re-reads the on-disk index so a previous session's state survives
    restart and any download-dir change (the user picking a new folder
    triggers another :func:`init` to repoint at the new location).
    """

    global _index, _index_path, _lyrics_base
    base = Path(download_dir) / '.lyrics'
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.opt(exception=True).warning(
            'Could not create lyrics folder {}', base
        )
        return
    idx_path = base / 'index.json'
    with _lock:
        _lyrics_base = base
        _index_path = idx_path
        _index = {}
        if idx_path.exists():
            try:
                raw = json.loads(idx_path.read_text(encoding='utf-8'))
                if isinstance(raw, dict):
                    _index = {
                        str(k): str(v) for k, v in raw.items() if v
                    }
            except Exception:
                logger.opt(exception=True).debug(
                    'Could not load lyrics index: will rebuild on demand'
                )
        # Self-heal: drop entries whose .lrc has been deleted.
        stale = [k for k, v in _index.items() if not (base / v).is_file()]
        for k in stale:
            _index.pop(k, None)
        if stale:
            _persist_locked()


def base_dir() -> Optional[Path]:
    return _lyrics_base


def _persist_locked() -> None:
    if _index_path is None:
        return
    try:
        tmp = _index_path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(_index, indent=0), encoding='utf-8')
        tmp.replace(_index_path)  # atomic on Windows + POSIX
    except OSError:
        logger.opt(exception=True).debug('Could not persist lyrics index')


def lookup(artist: str, title: str) -> Optional[Path]:
    """Return the full path of the stored .lrc for *artist*/*title* or None."""
    if _lyrics_base is None:
        return None
    with _lock:
        rel = _index.get(_key(artist, title))
    if not rel:
        return None
    p = _lyrics_base / rel
    return p if p.is_file() else None


def lookup_text(artist: str, title: str) -> Optional[str]:
    p = lookup(artist, title)
    if p is None:
        return None
    try:
        return p.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return None


def store(artist: str, title: str, text: str) -> Optional[Path]:
    """Persist *text* as the .lrc for *artist*/*title*; return its path."""
    if _lyrics_base is None or not (artist and title and text):
        return None
    fname = _safe_filename(f'{artist} - {title}') + '.lrc'
    target = _lyrics_base / fname
    try:
        tmp = target.with_name(target.name + '.tmp')
        tmp.write_text(text, encoding='utf-8')
        tmp.replace(target)
    except OSError:
        logger.opt(exception=True).debug('Could not write lyrics {}', target)
        return None
    with _lock:
        _index[_key(artist, title)] = fname
        _persist_locked()
    return target


def all_keys() -> Iterable[str]:
    with _lock:
        return tuple(_index.keys())
