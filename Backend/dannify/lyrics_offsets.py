"""Persistent, shared per-song lyric preferences (timing offset + version).

When a user fine-tunes a song's lyrics: nudging the timing offset and/or
picking which of several synced versions syncs best: those choices are stored
keyed by ``artist|title`` in a small JSON file. Every future playback of that
song, for any user, then applies the saved preferences automatically. A
crowd-sourced lyric-correction layer.

Record shape:  ``{ "offset": float_seconds, "version": int_index }``
Legacy records may be a bare float (offset only): handled transparently.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional

from loguru import logger

_lock = threading.Lock()
_path: Optional[Path] = None
_data: dict[str, dict[str, Any]] = {}
_loaded = False


def _coerce(value: Any) -> dict[str, Any]:
    """Normalize a stored record (legacy float or dict) into a dict."""

    if isinstance(value, dict):
        return {
            'offset': float(value.get('offset') or 0.0),
            'version': int(value.get('version') or 0),
        }
    try:
        return {'offset': float(value), 'version': 0}
    except (TypeError, ValueError):
        return {'offset': 0.0, 'version': 0}


def init(database_dir: Path) -> None:
    """Point the store at ``<database_dir>/lyric_offsets.json`` and load it."""

    global _path, _data, _loaded
    _path = Path(database_dir) / 'lyric_offsets.json'
    try:
        if _path.exists():
            raw = json.loads(_path.read_text(encoding='utf-8'))
            _data = {str(k): _coerce(v) for k, v in raw.items()}
    except Exception:
        logger.opt(exception=True).warning('Could not load lyric prefs')
        _data = {}
    _loaded = True


def _key(title: str, artist: str) -> str:
    return f'{(artist or "").strip().lower()}|{(title or "").strip().lower()}'


def _persist() -> None:
    if _path is None:
        return
    try:
        _path.write_text(json.dumps(_data, indent=2), encoding='utf-8')
    except Exception:
        logger.opt(exception=True).warning('Could not persist lyric prefs')


def get_prefs(title: str, artist: str) -> dict[str, Any]:
    """Return ``{offset, version}`` for the song (defaults 0/0)."""

    if not _loaded:
        return {'offset': 0.0, 'version': 0}
    with _lock:
        rec = _data.get(_key(title, artist))
        return dict(rec) if rec else {'offset': 0.0, 'version': 0}


# Back-compat: offset-only accessor used elsewhere.
def get(title: str, artist: str) -> float:
    return get_prefs(title, artist).get('offset', 0.0)


def set(  # noqa: A001 - mirrors prior public name
    title: str,
    artist: str,
    offset: Optional[float] = None,
    version: Optional[int] = None,
) -> dict[str, Any]:
    """Update offset and/or version for the song; persist; return the record."""

    if not title or not artist:
        return {'offset': 0.0, 'version': 0}
    key = _key(title, artist)
    with _lock:
        rec = dict(_data.get(key) or {'offset': 0.0, 'version': 0})
        if offset is not None:
            rec['offset'] = max(-30.0, min(30.0, float(offset)))
        if version is not None:
            rec['version'] = max(0, int(version))
        # Drop the record entirely if it's back to defaults.
        if abs(rec.get('offset', 0.0)) < 1e-3 and int(rec.get('version', 0)) == 0:
            _data.pop(key, None)
        else:
            _data[key] = rec
        _persist()
        return rec
