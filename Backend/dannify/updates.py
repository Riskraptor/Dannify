"""Update checks against GitHub releases, and getting a new version ready.

An installed Dannify (see layout.py) updates without ever touching a file
that is in use. The new version is assembled next to the running one, in
app-next: every file that did not change is hard-linked from the running
copy (no download, no extra disk space), and only the files that changed are
pulled out of the release's package archive with HTTP range requests. Once
every file checks out against the release's list, a marker is written and
the folder is renamed into place in one step. The launcher swaps it in at
the next start, or straight away for "restart to update".

A copy that is not installed that way (run from source, or copied somewhere
by hand) cannot do that, and downloads the installer instead.

Point it at your repository with ``DANNIFY_UPDATE_REPO=owner/name`` (or edit
``DEFAULT_REPO``). Nothing here needs a token: public releases only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

from . import layout

# Releases live in their own public repository. The source repository is
# private, and a private one's releases need a token: shipping a token in
# the app would hand every copy read access to the source, which is worse
# than publishing it.
DEFAULT_REPO = 'DANIELMWENDWA9451/dannify-releases'
# Where About sends people: the page the builds are on.
SITE_URL = 'https://github.com/DANIELMWENDWA9451/dannify-releases/releases'
CHECK_TTL = 60 * 60 * 6  # re-check at most every 6 hours
_USER_AGENT = 'Dannify-Updater'

_lock = threading.Lock()
_cache: dict[str, Any] = {'at': 0.0, 'result': None}
_settings: dict[str, Any] = {'repo': '', 'channel': 'stable'}
_stage_lock = threading.Lock()


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
    # A shipped copy updates from where it was built to, and nowhere else: a
    # variable or a file pointing it at another repository would have it
    # install whatever that one offered.
    import sys

    if getattr(sys, 'frozen', False):
        return DEFAULT_REPO
    return (
        os.getenv('DANNIFY_UPDATE_REPO') or _settings['repo'] or DEFAULT_REPO
    ).strip('/ ')


def _api_base() -> str:
    # Tests point the updater at a release server on this machine. Nothing
    # else is accepted, so the variable cannot send a real copy anywhere.
    override = os.getenv('DANNIFY_UPDATE_API', '').strip().rstrip('/')
    if re.match(r'^http://(127\.0\.0\.1|localhost)(:\d+)?(/|$)', override):
        return override
    return 'https://api.github.com'


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


def _get_text(url: str) -> str:
    request = urllib.request.Request(url, headers={'User-Agent': _USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode('utf-8')


def _fetch_latest() -> dict[str, Any]:
    base = f'{_api_base()}/repos/{repo()}/releases'
    if _settings['channel'] == 'prerelease':
        # /latest skips pre-releases, so early adopters read the full list.
        for release in _get(f'{base}?per_page=10') or []:
            if isinstance(release, dict) and not release.get('draft'):
                return release
        return {}
    return _get(f'{base}/latest')


# Where a release's files may come from: GitHub's own download hosts, over
# TLS, or the stand-in release server a test runs on this machine. The
# interface used to be able to hand the updater any address at all, and the
# file it fetched was then offered to run as the installer.
_ASSET_HOSTS = (
    'github.com',
    'objects.githubusercontent.com',
    'release-assets.githubusercontent.com',
)


def trusted_asset(url: str) -> bool:
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(str(url or ''))
    except ValueError:
        return False
    if chr(92) in (parts.path or ''):  # a backslash: a second path, on Windows
        return False
    host = (parts.hostname or '').lower()
    if parts.scheme == 'https' and host in _ASSET_HOSTS:
        return True
    base = _api_base()
    return base.startswith('http://') and str(url).startswith(base + '/')


def _check_asset(url: str) -> str:
    if not trusted_asset(url):
        raise RuntimeError(f'refusing to fetch an update from {url!r}')
    return url


def _asset(assets: list, prefix: str, suffix: str) -> str:
    """Find a release asset by name shape."""

    for item in assets or []:
        name = str(item.get('name', ''))
        if name.startswith(prefix) and name.endswith(suffix):
            return item.get('browser_download_url', '')
    return ''


def check(current_version: str, force: bool = False) -> dict[str, Any]:
    """Return ``{available, version, notes, url, download_url, size, ...}``."""

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
        # What an installed copy updates from: every file's hash, and an
        # archive to take the changed ones out of.
        'package_manifest_url': '',
        'package_url': '',
        'managed': layout.managed(),
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
            None,
        )
        available = bool(tag) and is_newer(tag, current_version)
        # A version that could not start on this PC was rolled back by the
        # launcher; offering it again would only go round in circles.
        if available and tag == layout.skipped_version():
            available = False
        result.update(
            {
                'available': available,
                'version': tag,
                'notes': (data.get('body') or '')[:4000],
                'url': data.get('html_url') or '',
                'download_url': (installer or {}).get('browser_download_url', ''),
                'size': int((installer or {}).get('size') or 0),
                'published_at': data.get('published_at') or '',
                'package_manifest_url': _asset(assets, 'package-', '.json'),
                'package_url': _asset(assets, 'package-', '.zip'),
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

    Stages get a slice of the bar, sized roughly by how long they take. The
    number only ever goes up, and is never sent more often than it moves by a
    fifth of a percent: a thousand websocket messages help nobody. What is
    sent is a stage name, not a sentence, so the interface can say it in the
    user's language.
    """

    def __init__(self, send: Optional[Callable[..., None]]) -> None:
        self._send = send
        self._low = 0.0
        self._high = 1.0
        self._stage = ''
        self._last = -1.0

    def stage(self, name: str, low: float, high: float) -> None:
        self._stage, self._low, self._high = name, low, high
        self(0.0)

    def __call__(self, fraction: float, done: int = 0, total: int = 0) -> None:
        if self._send is None:
            return
        fraction = max(0.0, min(1.0, fraction))
        value = (self._low + (self._high - self._low) * fraction) * 100.0
        if value < self._last + 0.2 and fraction < 1.0:
            return
        self._last = value
        self._send(round(value, 1), self._stage, done, total)

    def done(self) -> None:
        self._last = -1.0
        self.__call__(1.0)


def download(
    url: str,
    dest_dir: Path,
    progress_cb: Optional[Callable[..., None]] = None,
) -> Path:
    """Download the installer (for a copy that cannot update in place)."""

    _check_asset(url)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    # The name comes from the address, so it is cut down to something that
    # can only ever be a file in this folder: no separators, no "..".
    from urllib.parse import unquote, urlsplit

    raw = unquote(urlsplit(url).path.rsplit('/', 1)[-1])
    name = re.sub(r'[^A-Za-z0-9._-]', '', raw).lstrip('.')
    if not name.lower().endswith('.exe'):
        name = 'Dannify-Setup.exe'
    target = dest_dir / name
    partial = target.with_suffix(target.suffix + '.part')
    # Which file the partial copy is of, as the server named it. A dropped
    # connection used to throw the whole download away and start again;
    # it carries on from where it stopped now, and only if the file on the
    # server is still the same one ("If-Range"), so two never get spliced.
    tag_file = partial.with_suffix(partial.suffix + '.tag')
    bar = Progress(progress_cb)
    bar.stage('downloading', 0.0, 0.98)

    have = partial.stat().st_size if partial.is_file() else 0
    tag = ''
    if have:
        try:
            tag = tag_file.read_text(encoding='utf-8').strip()
        except OSError:
            tag = ''
        if not tag:
            have = 0
    headers = {'User-Agent': _USER_AGENT}
    if have:
        headers['Range'] = f'bytes={have}-'
        headers['If-Range'] = tag
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        resumed = have > 0 and response.status == 206 and str(
            response.headers.get('Content-Range') or ''
        ).startswith(f'bytes {have}-')
        if not resumed:
            have = 0
        length = int(response.headers.get('Content-Length') or 0)
        total = have + length if length else 0
        etag = response.headers.get('ETag') or response.headers.get('Last-Modified') or ''
        try:
            if etag:
                tag_file.write_text(etag, encoding='utf-8')
            else:
                tag_file.unlink(missing_ok=True)
        except OSError:
            pass
        done = have
        with open(partial, 'ab' if resumed else 'wb') as handle:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if total:
                    bar(done / total, done, total)
    # A connection that closes early ends the loop just like a finished one
    # does. A setup that is short is no use to anyone: it stays as a partial
    # copy for the next try to finish, and is not handed over as ready.
    if total and done != total:
        raise RuntimeError(f'download stopped early ({done} of {total} bytes)')
    partial.replace(target)
    tag_file.unlink(missing_ok=True)
    bar.done()
    logger.info('Update downloaded to {}{}', target, ' (resumed)' if resumed else '')
    return target


# ---------------------------------------------------------------------------
# Getting the next version ready beside this one
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Same file, second name: no copy, no extra space. The running copy
        # never writes to its own files, so sharing them is safe.
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def stage(info: dict[str, Any], progress: Optional[Callable[..., None]] = None) -> Path:
    """Build the new version in <root>\\app-next and mark it ready.

    Raises on anything that goes wrong; a half-made folder is removed and
    nothing the running copy uses is ever touched.
    """

    from . import delta

    base, here = layout.root(), layout.app_dir()
    if base is None or here is None:
        raise RuntimeError('this copy cannot update in place')
    manifest_url = str(info.get('package_manifest_url') or '')
    zip_url = str(info.get('package_url') or '')
    if not manifest_url or not zip_url:
        raise RuntimeError('the release has no package')
    _check_asset(manifest_url)
    _check_asset(zip_url)

    with _stage_lock:
        bar = Progress(progress)
        bar.stage('reading', 0.0, 0.03)
        manifest = json.loads(_get_text(manifest_url))
        files: dict[str, Any] = manifest.get('files') or {}
        version = str(manifest.get('version') or info.get('version') or '')
        if not files or not version:
            raise RuntimeError('the release package list is empty')

        tmp = base / f'app-next.tmp-{os.urandom(4).hex()}'
        for rel in files:
            if not delta.inside(tmp, rel):
                raise ValueError(f'package entry outside the app folder: {rel!r}')

        try:
            bar.stage('checking', 0.03, 0.12)
            keep: list[str] = []
            fetch: list[str] = []
            total_bytes = sum(int(m.get('size') or 0) for m in files.values()) or 1
            seen = 0
            for rel, meta in files.items():
                local = here / rel
                seen += int(meta.get('size') or 0)
                bar(seen / total_bytes)
                try:
                    if local.is_file() and local.stat().st_size == meta['size'] and _sha256(local) == meta['sha256']:
                        keep.append(rel)
                        continue
                except OSError:
                    pass
                fetch.append(rel)

            fetch_bytes = sum(int(files[rel]['size']) for rel in fetch)
            logger.info(
                'Update {}: {} file(s) to fetch ({:.1f} MB), {} unchanged',
                version, len(fetch), fetch_bytes / 1048576, len(keep),
            )

            bar.stage('downloading', 0.12, 0.92)
            if fetch:
                delta.fetch(zip_url, fetch, tmp, bar)
            for rel in keep:
                _link_or_copy(here / rel, tmp / rel)

            bar.stage('verifying', 0.92, 0.99)
            for index, rel in enumerate(fetch):
                meta = files[rel]
                target = tmp / rel
                if not target.is_file() or target.stat().st_size != meta['size'] or _sha256(target) != meta['sha256']:
                    raise RuntimeError(f'downloaded file does not match: {rel}')
                bar((index + 1) / max(1, len(fetch)))
            for rel in keep:
                if (tmp / rel).stat().st_size != files[rel]['size']:
                    raise RuntimeError(f'kept file does not match: {rel}')

            (tmp / layout.READY).write_text(
                json.dumps(
                    {
                        'version': version,
                        'notes': str(info.get('notes') or '')[:4000],
                        'staged': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    }
                ),
                encoding='utf-8',
            )

            final = base / layout.STAGING
            if final.exists():
                # An older update that was waiting: this one replaces it.
                shutil.rmtree(final, ignore_errors=True)
                if final.exists():
                    raise RuntimeError('an older update could not be cleared away')
            os.replace(tmp, final)
            bar.done()
            logger.info('Update {} is ready for the next start', version)
            return final
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise


def discard_staged() -> None:
    folder = layout.staging()
    if folder is not None and folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


_DOWNLOADED = re.compile(r'^(?:delta-|Dannify-Setup-)(\d+(?:\.\d+)*)(?:\.exe)?(?:\.part(?:\.tag)?)?$')


def prune_downloads(dest_dir: Path, current: str) -> list[str]:
    """Remove update downloads for this version or older. Returns their names.

    An installer that had been run, and a partial update given up on in
    favour of one, stayed in the data folder for good: tens of megabytes an
    update, adding up. Anything for a version newer than the one running is
    left exactly where it is, because that is an update waiting for the app to
    close (or one that did not take, and will be tried again).
    """

    folder = Path(dest_dir)
    if not folder.is_dir():
        return []
    removed = []
    for item in folder.iterdir():
        match = _DOWNLOADED.match(item.name)
        if not match or is_newer(match.group(1), current):
            continue
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except OSError:
            continue  # still open (an installer that has not quit yet): next start
        removed.append(item.name)
    if removed:
        logger.info('Cleared old update downloads: {}', ', '.join(sorted(removed)))
    return removed
