"""Update checks against GitHub releases.

The app asks GitHub for the latest release, compares it with the running
version and: when the user agrees. Downloads the Windows installer and
hands it to the desktop shell, which runs it and relaunches the app.

Point it at your repository with ``DANNIFY_UPDATE_REPO=owner/name`` (or edit
``DEFAULT_REPO``). Nothing here needs a token: public releases only.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

DEFAULT_REPO = 'DANIELMWENDWA9451/Dannify'
CHECK_TTL = 60 * 60 * 6  # re-check at most every 6 hours
_USER_AGENT = 'Dannify-Updater'

_lock = threading.Lock()
_cache: dict[str, Any] = {'at': 0.0, 'result': None}
_settings: dict[str, Any] = {'repo': '', 'channel': 'stable'}


def init(data_dir: Path) -> None:
    """Read ``updates.json`` from the data folder (all keys optional).

    ``{"repo": "you/your-fork", "channel": "stable"}`` is enough to point the
    updater at your own GitHub releases without rebuilding the app. The
    ``DANNIFY_UPDATE_REPO`` environment variable still wins over the file.
    """

    from .support import config_paths

    for path in config_paths(data_dir, 'updates.json'):
        try:
            stored = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(stored, dict):
                continue
            value = str(stored.get('repo') or '').strip('/ ')
            if value:
                _settings['repo'] = value
            channel = str(stored.get('channel') or '').strip().lower()
            if channel in ('stable', 'prerelease'):
                _settings['channel'] = channel
        except FileNotFoundError:
            continue
        except Exception:
            logger.opt(exception=True).debug('Could not read {}', path)
    logger.debug('Update channel {} on {}', _settings['channel'], repo())


def repo() -> str:
    return (
        os.getenv('DANNIFY_UPDATE_REPO') or _settings['repo'] or DEFAULT_REPO
    ).strip('/ ')


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r'\d+', str(value or ''))
    return tuple(int(p) for p in parts[:4]) or (0,)


def is_newer(candidate: str, current: str) -> bool:
    return _version_tuple(candidate) > _version_tuple(current)


def _get(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': _USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode('utf-8'))


def _fetch_latest() -> dict[str, Any]:
    base = f'https://api.github.com/repos/{repo()}/releases'
    if _settings['channel'] == 'prerelease':
        # /latest skips pre-releases, so early adopters read the full list.
        for release in _get(f'{base}?per_page=10') or []:
            if isinstance(release, dict) and not release.get('draft'):
                return release
        return {}
    return _get(f'{base}/latest')


def check(current_version: str, force: bool = False) -> dict[str, Any]:
    """Return ``{available, version, notes, url, download_url, size}``."""

    now = time.time()
    with _lock:
        cached = _cache['result']
        if cached is not None and not force and now - _cache['at'] < CHECK_TTL:
            return cached

    result: dict[str, Any] = {
        'available': False,
        'current': current_version,
        'version': '',
        'notes': '',
        'url': '',
        'download_url': '',
        'size': 0,
        'published_at': '',
        'error': '',
    }
    try:
        data = _fetch_latest()
        tag = str(data.get('tag_name') or data.get('name') or '').lstrip('vV')
        assets = data.get('assets') or []
        installer = next(
            (
                a
                for a in assets
                if str(a.get('name', '')).lower().endswith('.exe')
                and 'setup' in str(a.get('name', '')).lower()
            ),
            next(
                (a for a in assets if str(a.get('name', '')).lower().endswith('.exe')),
                None,
            ),
        )
        result.update(
            {
                'available': bool(tag) and is_newer(tag, current_version),
                'version': tag,
                'notes': (data.get('body') or '')[:4000],
                'url': data.get('html_url') or '',
                'download_url': (installer or {}).get('browser_download_url', ''),
                'size': int((installer or {}).get('size') or 0),
                'published_at': data.get('published_at') or '',
            }
        )
    except Exception as exc:  # offline, rate-limited, no releases yet…
        result['error'] = str(exc)
        logger.debug('Update check failed: {}', exc)

    with _lock:
        _cache['result'] = result
        _cache['at'] = now
    return result


def download(
    url: str,
    dest_dir: Path,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> Path:
    """Download the installer, reporting 0-100 progress."""

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = url.rsplit('/', 1)[-1] or 'Dannify-Setup.exe'
    target = dest_dir / name
    partial = target.with_suffix(target.suffix + '.part')
    request = urllib.request.Request(url, headers={'User-Agent': _USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        total = int(response.headers.get('Content-Length') or 0)
        done = 0
        with open(partial, 'wb') as handle:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    progress_cb(min(99.0, done * 100.0 / total))
    partial.replace(target)
    if progress_cb:
        progress_cb(100.0)
    logger.info('Update downloaded to {}', target)
    return target
