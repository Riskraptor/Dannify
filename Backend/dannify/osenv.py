"""What differs between Windows, Linux and macOS, in one place.

The rest of the backend asks here instead of testing ``os.name`` itself, so a
new platform is a change to this file and not a hunt through every module.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

from loguru import logger

IS_WINDOWS = os.name == 'nt'
IS_MAC = sys.platform == 'darwin'
IS_LINUX = sys.platform.startswith('linux')

# The name every platform knows this platform by in release files and in the
# signed update statements ('windows', 'linux', 'macos').
PLATFORM = 'windows' if IS_WINDOWS else 'macos' if IS_MAC else 'linux'


def packaged() -> bool:
    """True when this is an installed copy rather than a source checkout.

    A Windows or macOS build is frozen by PyInstaller. The Linux package runs
    from source inside its own virtual environment, so its launcher says so
    with DANNIFY_PACKAGED; it needs the same per-user folders a frozen build
    uses, not the checkout's own data folder (which, under /opt, nobody can
    write to).
    """

    return bool(getattr(sys, 'frozen', False)) or os.getenv('DANNIFY_PACKAGED') == '1'


def default_data_dir() -> Path:
    """Where an installed copy keeps its settings, caches and keys."""

    home = Path.home()
    if IS_WINDOWS:
        return Path(os.getenv('LOCALAPPDATA') or str(home / 'AppData' / 'Local')) / 'Dannify'
    if IS_MAC:
        return home / 'Library' / 'Application Support' / 'Dannify'
    return Path(os.getenv('XDG_DATA_HOME') or str(home / '.local' / 'share')) / 'Dannify'


def default_music_dir() -> Path:
    """The folder new downloads go to unless the user picked another."""

    home = Path.home()
    if IS_LINUX:
        # The desktop's own idea of "Music", which is translated on
        # non-English systems (~/Musique, ~/Musik).
        try:
            out = subprocess.run(
                ['xdg-user-dir', 'MUSIC'], capture_output=True, text=True, timeout=3,
            ).stdout.strip()
            if out and Path(out) != home:
                return Path(out) / 'Dannify'
        except (OSError, subprocess.SubprocessError):
            pass
    return home / 'Music' / 'Dannify'


def exe_names(*bases: str) -> tuple[str, ...]:
    """File names a bundled tool has here: name.exe on Windows only.

    Looking for both everywhere let a Linux checkout pick up the Windows
    build of the media tool, and yt-dlp was then pointed at a .exe.
    """

    return tuple(f'{b}.exe' for b in bases) if IS_WINDOWS else bases


# ---------------------------------------------------------------------------
# The Trash
# ---------------------------------------------------------------------------
def trash(paths: list[Path]) -> bool:
    """Move files to the Recycle Bin / Trash. False when that could not be
    done, and the caller decides whether to delete instead."""

    paths = [Path(p) for p in paths]
    if not paths:
        return False
    try:
        if IS_WINDOWS:
            ok = _trash_windows(paths)
        elif IS_MAC:
            ok = _trash_macos(paths)
        else:
            ok = _trash_linux(paths)
    except Exception:
        logger.opt(exception=True).debug('could not use the Trash')
        return False
    return ok and not any(p.exists() for p in paths)


def _trash_windows(paths: list[Path]) -> bool:
    # SHFileOperation with FOF_ALLOWUNDO is what Explorer's own Delete does.
    # On a drive with no Recycle Bin it deletes outright, which is what the
    # caller would have done anyway.
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ('hwnd', wintypes.HWND),
            ('wFunc', wintypes.UINT),
            ('pFrom', wintypes.LPCWSTR),
            ('pTo', wintypes.LPCWSTR),
            ('fFlags', ctypes.c_ushort),
            ('fAnyOperationsAborted', wintypes.BOOL),
            ('hNameMappings', ctypes.c_void_p),
            ('lpszProgressTitle', wintypes.LPCWSTR),
        ]

    fo_delete = 3
    flags = 0x40 | 0x10 | 0x4 | 0x400  # ALLOWUNDO, NOCONFIRMATION, SILENT, NOERRORUI
    # A list of paths, each ending in a nul, the whole ending in another.
    names = ctypes.create_unicode_buffer('\0'.join(str(p) for p in paths) + '\0\0')
    op = SHFILEOPSTRUCTW(
        None, fo_delete, ctypes.cast(names, wintypes.LPCWSTR), None,
        flags, False, None, None,
    )
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return result == 0 and not op.fAnyOperationsAborted


def _trash_macos(paths: list[Path]) -> bool:
    # NSFileManager's trashItemAtURL is what Finder's Move to Trash does,
    # "Put Back" included, and asks for no automation permission.
    from Foundation import NSFileManager, NSURL  # type: ignore[import-not-found]

    manager = NSFileManager.defaultManager()
    for p in paths:
        ok, _, _ = manager.trashItemAtURL_resultingItemURL_error_(
            NSURL.fileURLWithPath_(str(p)), None, None,
        )
        if not ok:
            return False
    return True


def _trash_linux(paths: list[Path]) -> bool:
    # gio knows every mount's own trash folder; without it, files on the
    # home partition still go to the freedesktop.org Trash by hand.
    gio = shutil.which('gio')
    if gio:
        done = subprocess.run(
            [gio, 'trash', '--', *map(str, paths)], capture_output=True, timeout=30,
        )
        if done.returncode == 0:
            return True
    return all(_trash_home(p) for p in paths)


def _trash_home(path: Path) -> bool:
    """The freedesktop.org Trash spec, for a file on the home partition."""

    base = Path(os.getenv('XDG_DATA_HOME') or str(Path.home() / '.local' / 'share')) / 'Trash'
    files, info = base / 'files', base / 'info'
    files.mkdir(parents=True, exist_ok=True)
    info.mkdir(parents=True, exist_ok=True)
    if os.stat(path).st_dev != os.stat(files).st_dev:
        return False  # another disk: moving would copy the whole file
    name, n = path.name, 1
    while (files / name).exists() or (info / f'{name}.trashinfo').exists():
        n += 1
        name = f'{path.stem}.{n}{path.suffix}'
    stamp = time.strftime('%Y-%m-%dT%H:%M:%S')
    (info / f'{name}.trashinfo').write_text(
        '[Trash Info]\n'
        f'Path={urllib.parse.quote(str(path.resolve()))}\n'
        f'DeletionDate={stamp}\n',
        encoding='utf-8',
    )
    os.rename(path, files / name)
    return True


def which_any(*names: str) -> Optional[str]:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None
