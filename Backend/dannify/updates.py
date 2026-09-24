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
# Where About sends people: the page the builds are on. There is no separate
# product site, so pointing at one that does not exist would just be a dead
# button.
SITE_URL = 'https://github.com/DANIELMWENDWA9451/dannify-releases/releases'
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
        # The product page. About links here rather than at a repository:
        # nothing in the app should send anyone looking for source code.
        'site_url': SITE_URL,
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
        # A failure is not an answer. Caching one for the full six hours meant
        # a single bad moment on the network left the app believing it was
        # offline until tomorrow, with nothing the user could do about it.
        # Hold a failure for a minute, then let the next check actually try.
        _cache['at'] = now if not result['error'] else now - CHECK_TTL + 60
    return result


class Progress:
    """One honest 0 to 100 for a whole update, not one per stage.

    Each stage used to report its own percentage into the same bar, so the
    number ran to a hundred, dropped back to nothing and climbed again. Worse,
    the download stage only reported once a file had finished, and the app
    executable is twelve megabytes of a fourteen megabyte update: the bar sat
    at zero for the entire download and then jumped to ninety something.

    Stages get a slice of the bar here, sized roughly by how long they take.
    The number only ever goes up, and it is never sent more than a few times
    a second, because a thousand websocket messages help nobody.
    """

    def __init__(self, send: Optional[Callable[..., None]]) -> None:
        self._send = send
        self._low = 0.0
        self._high = 1.0
        self._label = ''
        self._last = -1.0

    def stage(self, label: str, low: float, high: float) -> None:
        self._label, self._low, self._high = label, low, high
        self(0.0)

    def __call__(self, fraction: float, detail: str = '') -> None:
        if self._send is None:
            return
        fraction = max(0.0, min(1.0, fraction))
        value = (self._low + (self._high - self._low) * fraction) * 100.0
        # Never backwards, and never more than one step of a fifth of a
        # percent: the bar animates between points on its own.
        if value < self._last + 0.2 and fraction < 1.0:
            return
        self._last = value
        self._send(round(value, 1), detail or self._label)

    def done(self) -> None:
        self._last = -1.0
        self.__call__(1.0)


def _megabytes(done: int, total: int) -> str:
    return f'{done / 1048576:.1f} of {total / 1048576:.1f} MB'


def download(
    url: str,
    dest_dir: Path,
    progress_cb: Optional[Callable[..., None]] = None,
) -> Path:
    """Download the installer, reporting 0-100 progress."""

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = url.rsplit('/', 1)[-1] or 'Dannify-Setup.exe'
    target = dest_dir / name
    partial = target.with_suffix(target.suffix + '.part')
    bar = Progress(progress_cb)
    bar.stage('Downloading the installer', 0.0, 0.98)
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
                if total:
                    bar(done / total, f'Downloading the installer, {_megabytes(done, total)}')
    bar.stage('Ready to install', 0.98, 1.0)
    partial.replace(target)
    bar.done()
    logger.info('Update downloaded to {}', target)
    return target


def prepare_delta(
    app_dir: Path,
    dest_dir: Path,
    info: dict[str, Any],
    progress: Optional[Callable[..., None]] = None,
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

    # Shares of the bar, sized by how long each part actually takes. Reading
    # the release is one small request; checking is a second of hashing; the
    # download is everything else.
    bar = Progress(progress)

    try:
        bar.stage('Reading the release', 0.0, 0.04)
        manifest = json.loads(_get_text(manifest_url))
        if not isinstance(manifest, dict) or not manifest.get('files'):
            return None

        bar.stage('Checking what changed', 0.04, 0.14)
        found = delta.plan(app_dir, manifest, bar)
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
        bar.stage('Downloading', 0.14, 0.93)
        delta.fetch(files_url, changed, staging, bar)

        bar.stage('Checking the download', 0.93, 1.0)
        if not delta.verify_staged(staging, changed, manifest):
            logger.warning('Partial update failed verification; using the installer')
            shutil.rmtree(staging, ignore_errors=True)
            return None

        delta.write_plan(staging, manifest, removed)
        bar.done()
        return staging
    except Exception as exc:
        logger.info('Partial update not possible ({}); using the installer', exc)
        return None


def _get_text(url: str) -> str:
    request = urllib.request.Request(url, headers={'User-Agent': _USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode('utf-8')
