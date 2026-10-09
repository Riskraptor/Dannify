"""The operating system's own secret store, for the one key that wraps ours.

Windows has DPAPI, and vault._protect uses it directly. Linux and macOS have
no such call, so there a random wrapping key is kept in the system's secret
store (the Secret Service that GNOME Keyring and KWallet answer, or the macOS
login Keychain), and everything _protect wraps is sealed with that key. A copy
of the data folder, or of the hidden store beside the music, is then useless
without this user's unlocked keyring, which is what DPAPI gives Windows.

Both are reached through their command-line tools (secret-tool, security):
no Python dependency to ship, and nothing that breaks when the app is updated
and its own code signature changes, which on macOS would otherwise ask for
the login password after every update.

When neither is there (a server, a desktop without a keyring daemon) the
wrapping key is kept in a file only this user can read. That is weaker, and
said plainly: it stops the store being readable as it sits and keeps a copied
music folder useless, not someone who can read this user's files.
"""

from __future__ import annotations

import base64
import os
import secrets
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

from loguru import logger

from .osenv import IS_MAC, IS_WINDOWS, default_data_dir

_SERVICE = 'Dannify'
_NAME = 'store-wrap'
_TIMEOUT = 20  # an unlock prompt may be on screen

_lock = threading.Lock()
_cached: dict[str, bytes] = {}


def _fallback_file() -> Path:
    override = os.getenv('DANNIFY_KEYWRAP_FILE')
    return Path(override) if override else default_data_dir() / '.keywrap'


def _backend() -> str:
    forced = os.getenv('DANNIFY_KEYSTORE', '').strip().lower()
    if forced in ('file', 'secret-service', 'keychain'):
        return forced
    if IS_MAC and shutil.which('security'):
        return 'keychain'
    if not IS_WINDOWS and not IS_MAC and shutil.which('secret-tool') and (
        os.getenv('DBUS_SESSION_BUS_ADDRESS') or os.getenv('XDG_RUNTIME_DIR')
    ):
        return 'secret-service'
    return 'file'


# ---------------------------------------------------------------------------
# Each store: read and write one base64 text value
# ---------------------------------------------------------------------------
def _run(args: list[str], stdin: str = '') -> Optional[str]:
    try:
        done = subprocess.run(
            args, input=stdin, capture_output=True, text=True, timeout=_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        logger.opt(exception=True).debug('{} did not run', args[0])
        return None
    if done.returncode != 0:
        return None
    return done.stdout


def _secret_service_get() -> Optional[str]:
    return _run(['secret-tool', 'lookup', 'application', 'dannify', 'name', _NAME])


def _secret_service_set(value: str) -> bool:
    # The secret goes in on stdin, never on the command line, where every
    # other process could read it.
    return _run(
        ['secret-tool', 'store', f'--label={_SERVICE} storage key',
         'application', 'dannify', 'name', _NAME],
        stdin=value,
    ) is not None


def _keychain_get() -> Optional[str]:
    return _run(['security', 'find-generic-password', '-s', _SERVICE, '-a', _NAME, '-w'])


def _keychain_set(value: str) -> bool:
    # `security -i` reads its command from stdin, so the value stays off the
    # process list too.
    return _run(
        ['security', '-i'],
        stdin=f'add-generic-password -U -s {_SERVICE} -a {_NAME} -l "{_SERVICE} storage key" -w {value}\n',
    ) is not None


def _file_get() -> Optional[str]:
    try:
        return _fallback_file().read_text(encoding='ascii')
    except OSError:
        return None


def _file_set(value: str) -> bool:
    path = _fallback_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='ascii') as f:
            f.write(value)
        os.chmod(path, 0o600)
        return True
    except OSError:
        logger.opt(exception=True).debug('could not keep the wrapping key')
        return False


_STORES = {
    'secret-service': (_secret_service_get, _secret_service_set),
    'keychain': (_keychain_get, _keychain_set),
    'file': (_file_get, _file_set),
}


def _decode(text: Optional[str]) -> Optional[bytes]:
    try:
        raw = base64.b64decode((text or '').strip(), validate=True)
    except ValueError:
        return None
    return raw if len(raw) == 32 else None


# ---------------------------------------------------------------------------
# The wrapping key
# ---------------------------------------------------------------------------
def wrapping_key(kind: str, create: bool = True) -> Optional[bytes]:
    """The key kept in store *kind*, made there the first time if *create*."""

    with _lock:
        if kind in _cached:
            return _cached[kind]
        get, put = _STORES[kind]
        key = _decode(get())
        if key is None and create:
            fresh = secrets.token_bytes(32)
            text = base64.b64encode(fresh).decode('ascii')
            # Only trusted once it reads back: a keyring that takes the value
            # and then loses it must not be the only place a key lives.
            if put(text) and _decode(get()) == fresh:
                key = fresh
        if key is not None:
            _cached[kind] = key
        return key


def preferred() -> str:
    """The store new wrappings use on this machine."""

    return _backend()


def forget_cache() -> None:
    with _lock:
        _cached.clear()
