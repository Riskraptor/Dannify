"""Fixes that reach every copy without a new version.

A signed file on the repository's main branch, ``config/live.json``, read at
start and every few hours after, kept for when there is no connection, and
believed only when its signature is the release key's (``updates.PUBLIC_KEY``)
and it is no older than the one kept: neither a changed file nor an old one
put back can tell a copy anything.

What it can say:

* ``clients``: the identities YouTube is asked with (see innertube.py). When
  YouTube changes what it accepts, songs stop playing everywhere at once; this
  puts it right everywhere at once, with no update to install.
* ``emergency``: a fix build every copy in a range should take now, said as
  ``{"version": "4.15.0.1", "from": "4.15.0", "notes": {"en": "...", ...}}``.
  A copy between ``from`` and ``version`` shows it as an important fix and
  fetches it, instead of waiting for its next check.
* ``notice``: a line for everyone (``{"id", "text": {"en": ...}, "until"}``),
  shown once per id, for something people should know (a service down).

Nothing else in the file is read. Changed with ``packaging/live_details.py``.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

NAME = 'live.json'
KIND = 'live'
FIELDS = ('clients', 'emergency', 'notice')
EVERY = 3 * 3600
MAX_BYTES = 256 * 1024

_lock = threading.Lock()
_live: dict[str, Any] = {}
_dir: Optional[Path] = None
_listeners: list[Callable[[dict[str, Any]], None]] = []


def accept(raw: bytes, signature: str, public_hex: str, newer_than: int = 0) -> Optional[dict[str, Any]]:
    """What *raw* says, if *signature* is the release key's over it and its
    version is not older than *newer_than*; else None."""

    from . import signing

    try:
        data = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    version = data.get('version')
    if not isinstance(version, int) or isinstance(version, bool) or version < max(1, newer_than):
        return None
    digest = hashlib.sha256(raw).hexdigest()
    if not signing.verify_release(public_hex, KIND, str(version), digest, signature):
        return None
    out = {k: data[k] for k in FIELDS if k in data}
    out['version'] = version
    return out


def _files() -> tuple[Optional[Path], Optional[Path]]:
    if _dir is None:
        return None, None
    from . import signing

    path = _dir / NAME
    return path, path.with_name(path.name + signing.SIGNATURE_SUFFIX)


def _take(found: dict[str, Any]) -> None:
    with _lock:
        _live.clear()
        _live.update(found)
    for listener in list(_listeners):
        try:
            listener(dict(found))
        except Exception:
            logger.opt(exception=True).debug('a live fix could not be applied')


def init(data_dir: Path) -> None:
    """Where the kept file is; what it says is taken at once, checked again."""

    global _dir
    _dir = Path(data_dir)
    from . import updates

    path, sig = _files()
    try:
        raw, signature = path.read_bytes(), sig.read_text(encoding='utf-8')
    except (OSError, AttributeError):
        return
    found = accept(raw, signature, updates.PUBLIC_KEY) if updates.PUBLIC_KEY else None
    if found:
        _take(found)
    else:
        logger.debug('the kept live file is not believed')


def on_change(listener: Callable[[dict[str, Any]], None]) -> None:
    """Call *listener* with what the file says now, and whenever it changes."""

    _listeners.append(listener)
    with _lock:
        now = dict(_live)
    if now:
        listener(now)


def refresh() -> bool:
    """Fetch the file from the repository and take it if it is good and at
    least as new as the one kept. Whether anything changed."""

    from . import signing, updates

    path, sig = _files()
    if path is None or not updates.PUBLIC_KEY:
        return False
    base = f'https://raw.githubusercontent.com/{updates.repo()}/main/config/{NAME}'

    def get(url: str) -> bytes:
        request = urllib.request.Request(url, headers={'User-Agent': 'Dannify', 'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read(MAX_BYTES)

    try:
        raw = get(base)
        signature = get(base + signing.SIGNATURE_SUFFIX).decode('utf-8', 'replace')
    except Exception as exc:
        logger.debug('live fixes not fetched: {}', exc)
        return False
    with _lock:
        kept = int(_live.get('version') or 0)
    found = accept(raw, signature, updates.PUBLIC_KEY, newer_than=kept)
    if not found or found['version'] == kept:
        return False
    try:
        path.write_bytes(raw)
        sig.write_text(signature, encoding='utf-8')
    except OSError:
        logger.opt(exception=True).debug('live fixes not kept on disk')
    _take(found)
    logger.info('live fixes version {} taken', found['version'])
    return True


def start() -> None:
    """Look for fixes now and every few hours, in the background."""

    def loop() -> None:
        while True:
            try:
                refresh()
            except Exception:
                logger.opt(exception=True).debug('live fixes check failed')
            time.sleep(EVERY)

    threading.Thread(target=loop, name='live-fixes', daemon=True).start()


def _text(value: Any) -> dict[str, str]:
    """``{"en": "...", ...}`` from a string or a dict of them, short."""

    if isinstance(value, str):
        return {'en': value[:500]}
    if isinstance(value, dict):
        return {str(k)[:8]: str(v)[:500] for k, v in value.items() if isinstance(v, str)}
    return {}


def status(current_version: str, now: Optional[float] = None) -> dict[str, Any]:
    """What the window should know: an important fix for this version, and a
    notice for everyone, each only when it applies."""

    from . import updates

    now = time.time() if now is None else now
    with _lock:
        live = dict(_live)
    out: dict[str, Any] = {'version': int(live.get('version') or 0), 'emergency': None, 'notice': None}
    em = live.get('emergency')
    if isinstance(em, dict) and isinstance(em.get('version'), str):
        target = em['version'].strip().lstrip('vV')
        start = str(em.get('from') or '').strip().lstrip('vV')
        if target and updates.is_newer(target, current_version) and (
            not start or not updates.is_newer(start, current_version)
        ):
            out['emergency'] = {'version': target, 'notes': _text(em.get('notes'))}
    notice = live.get('notice')
    if isinstance(notice, dict) and notice.get('id'):
        until = notice.get('until')
        if not isinstance(until, (int, float)) or until > now:
            out['notice'] = {'id': str(notice['id'])[:40], 'text': _text(notice.get('text'))}
    return out
