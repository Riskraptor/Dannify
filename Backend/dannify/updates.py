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
import shutil
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

# Releases live in their own public repository. The source repository is
# private, and a private one's releases need a token: shipping a token in
# the app would hand every copy read access to the source, which is worse
# than publishing it.
DEFAULT_REPO = 'DANIELMWENDWA9451/dannify-releases'
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


def _asset(assets: list, prefix: str, suffix: str) -> str:
    """Find a release asset by name shape."""

    for item in assets or []:
        name = str(item.get('name', ''))
        if name.startswith(prefix) and name.endswith(suffix):
            return item.get('browser_download_url', '')
    return ''


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
        # Where this build's releases come from. The UI links to it rather
        # than hard-coding a URL, so a fork only edits updates.json.
        'repo_url': f'https://github.com/{repo()}',
        # The pieces a partial update needs. Absent on older releases, in
        # which case the installer is the only route and that is fine.
        'manifest_url': '',
        'files_url': '',
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
                'manifest_url': _asset(assets, 'manifest-', '.json'),
                'files_url': _asset(assets, 'files-', '.zip'),
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


def prepare_delta(
    app_dir: Path,
    dest_dir: Path,
    info: dict[str, Any],
    progress: Optional[Callable[[float], None]] = None,
) -> Optional[Path]:
    """Try to assemble this update from just the files that changed.

    Returns the staging folder when it worked, or None to say "use the
    installer". Every failure returns None rather than raising: a partial
    update is an optimisation, and the full path is always there.
    """

    from . import delta

    manifest_url = str(info.get('manifest_url') or '')
    files_url = str(info.get('files_url') or '')
    if not manifest_url or not files_url:
        logger.debug('release has no update assets; using the installer')
        return None

    try:
        manifest = json.loads(_get_text(manifest_url))
        if not isinstance(manifest, dict) or not manifest.get('files'):
            return None

        found = delta.plan(app_dir, manifest)
        changed, removed, size = found['changed'], found['removed'], found['bytes']
        if not changed and not removed:
            logger.debug('nothing to fetch; already up to date on disk')
            return None
        if size > delta.MAX_DELTA_BYTES:
            logger.info(
                'Partial update would be {:.0f} MB; taking the installer instead',
                size / 1048576,
            )
            return None

        logger.info(
            'Partial update: {} file(s), {:.1f} MB of {:.1f} MB total',
            len(changed),
            size / 1048576,
            sum(f['size'] for f in manifest['files'].values()) / 1048576,
        )

        staging = Path(dest_dir) / f'delta-{manifest.get("version", "next")}'
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        delta.fetch(files_url, changed, staging, progress)

        if not delta.verify_staged(staging, changed, manifest):
            logger.warning('Partial update failed verification; using the installer')
            shutil.rmtree(staging, ignore_errors=True)
            return None

        delta.write_plan(staging, manifest, removed)
        return staging
    except Exception as exc:
        logger.info('Partial update not possible ({}); using the installer', exc)
        return None


def _get_text(url: str) -> str:
    request = urllib.request.Request(url, headers={'User-Agent': _USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode('utf-8')
