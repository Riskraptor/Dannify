"""Where this copy of Dannify lives, and what that means for updates.

From 4.0 an installed Dannify looks like this::

    <root>\\Dannify.exe     the launcher: shortcuts and .dnf files open this
    <root>\\app\\            this program (sys.executable is app\\Dannify.exe)
    <root>\\app-next\\       an update, waiting for the next start
    <root>\\app-old-*\\      the version before the last update, kept for going back

An update is downloaded into app-next while the app runs, and nothing in
app\\ is touched while it is open. The launcher swaps the two folders the next
time Dannify starts (or straight away, for "restart to update"). That is
the whole reason updates can no longer fail on a file Windows is holding:
no file that is in use is ever replaced.

Anything else (running from source, a folder copied somewhere by hand)
is "unmanaged": it cannot update itself in place and falls back to
downloading the installer.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

from loguru import logger

LAUNCHER = 'Dannify.exe'
STAGING = 'app-next'
READY = '.ready'
SKIP = '.skip-version'
# The launcher ships inside the app, so an update can bring a new one too.
BUNDLED_LAUNCHER = Path('runtime') / 'launcher.exe'


def app_dir() -> Optional[Path]:
    if not getattr(sys, 'frozen', False):
        return None
    return Path(sys.executable).resolve().parent


def root() -> Optional[Path]:
    """The installation folder, when this copy runs from <root>\\app."""

    here = app_dir()
    if here is None or here.name.lower() != 'app':
        return None
    parent = here.parent
    return parent if (parent / LAUNCHER).is_file() else None


def managed() -> bool:
    return root() is not None


def launcher() -> Optional[Path]:
    base = root()
    return base / LAUNCHER if base else None


def staging() -> Optional[Path]:
    base = root()
    return base / STAGING if base else None


def _read_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def pending() -> Optional[dict[str, Any]]:
    """The update waiting in app-next, if a complete one is there."""

    folder = staging()
    if folder is None or not (folder / LAUNCHER).is_file():
        return None
    return _read_json(folder / READY)


def just_updated() -> Optional[dict[str, Any]]:
    """Set once, right after an update: the marker travels with the folder."""

    here = app_dir()
    if here is None or not managed():
        return None
    return _read_json(here / READY)


def acknowledge_update() -> None:
    here = app_dir()
    if here is None:
        return
    try:
        (here / READY).unlink()
    except OSError:
        pass


def skipped_version() -> str:
    """A version that could not start here and was rolled back."""

    base = root()
    if base is None:
        if sys.platform != 'darwin' or not getattr(sys, 'frozen', False):
            return ''
        # A Mac app is put back by its own updater (shell/macos/updater.py),
        # which leaves the note in the data folder's updates.
        from . import osenv

        raw = os.getenv('DANNIFY_DATA_DIR')
        base = (Path(raw).expanduser() if raw else osenv.default_data_dir()) / 'updates'
    try:
        return (base / SKIP).read_text(encoding='utf-8').strip()
    except OSError:
        return ''


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _remove(path: Path) -> None:
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink()
    except OSError:
        pass


def tidy() -> None:
    """Leftovers the launcher or an interrupted run could not remove at the time.

    Keeps the newest app-old-* (the version to go back to) and removes the
    rest, broken or half-made folders, and what Dannify 3.x left in the root
    before it moved into app\\.
    """

    base = root()
    if base is None:
        return
    try:
        parked = sorted(base.glob('app-old-*'), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in parked[1:]:
            _remove(old)
        for pattern in ('app-broken-*', 'app.partial-*', 'app-next.tmp-*', 'runtime.old-*',
                        'config.old-*', 'Dannify.exe.old-*', 'Dannify.exe.new-*'):
            for leftover in base.glob(pattern):
                _remove(leftover)
        # Dannify 3.x's own files, if the move to app\ could not remove them then.
        for name in ('runtime', 'config'):
            _remove(base / name)
        for unins in base.glob('unins*.*'):
            _remove(unins)
    except OSError:
        logger.opt(exception=True).debug('tidy failed')


def refresh_launcher(patience: float = 120.0) -> None:
    """Put the launcher this version ships in place, if it differs.

    The launcher is only running for the moment it takes to start the app
    (or, after "restart to update", until the new window appears), so a
    replace that fails is tried again for a while.
    """

    here, target = app_dir(), launcher()
    if here is None or target is None:
        return
    source = here / BUNDLED_LAUNCHER
    if not source.is_file():
        return

    def run() -> None:
        try:
            if target.is_file() and target.stat().st_size == source.stat().st_size and _sha256(target) == _sha256(source):
                return
        except OSError:
            pass
        waited = 0.0
        while waited <= patience:
            tmp = target.with_name(LAUNCHER + '.new-' + os.urandom(4).hex())
            try:
                shutil.copyfile(source, tmp)
                if _sha256(tmp) != _sha256(source):
                    raise OSError('copy does not match')
                os.replace(tmp, target)
                logger.info('Launcher refreshed')
                return
            except OSError:
                try:
                    tmp.unlink()
                except OSError:
                    pass
            time.sleep(5.0)
            waited += 5.0
        logger.info('Launcher still in use; it will be refreshed next time')

    threading.Thread(target=run, name='dannify-launcher', daemon=True).start()


def refresh_registration(version: str) -> None:
    """Keep the version Settings > Apps shows in step with what runs."""

    base = root()
    if base is None or os.name != 'nt':
        return
    try:
        import winreg

        path = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\Dannify'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            location, _ = winreg.QueryValueEx(key, 'InstallLocation')
            if Path(str(location)).resolve() != base.resolve():
                return  # a sandboxed or second copy: not ours to describe
            try:
                current, _ = winreg.QueryValueEx(key, 'DisplayVersion')
            except OSError:
                current = ''
            if current != version:
                winreg.SetValueEx(key, 'DisplayVersion', 0, winreg.REG_SZ, version)
    except OSError:
        pass
    except Exception:
        logger.opt(exception=True).debug('could not refresh the Apps entry')
