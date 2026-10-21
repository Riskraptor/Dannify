"""Pictures the app makes to share: Your Soundtrack's card, as a PNG.

Saved where pictures go (the Pictures folder, in a Dannify folder of its own)
and shown there, so it can be dropped into WhatsApp, Instagram or an email.
Only a PNG the window drew is taken: checked for what it is and how big it
is, and named by the app, never by a path from outside.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

PNG = b'\x89PNG\r\n\x1a\n'
MAX_BYTES = 12 * 1024 * 1024


def pictures_dir() -> Path:
    """The user's Pictures folder, wherever the system keeps it."""

    if sys.platform == 'win32':
        found = _windows_pictures()
        if found:
            return found
    elif sys.platform.startswith('linux'):
        try:
            out = subprocess.run(['xdg-user-dir', 'PICTURES'], capture_output=True, text=True, timeout=3)
            path = out.stdout.strip()
            if out.returncode == 0 and path and Path(path) != Path.home():
                return Path(path)
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / 'Pictures'


def _windows_pictures() -> Optional[Path]:
    # FOLDERID_Pictures, which follows the folder when it is moved (OneDrive).
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [('a', wintypes.DWORD), ('b', wintypes.WORD), ('c', wintypes.WORD), ('d', ctypes.c_ubyte * 8)]

        folder = GUID(0x33E28130, 0x4E1E, 0x4676, (ctypes.c_ubyte * 8)(0x83, 0x5A, 0x98, 0x39, 0x5C, 0x3B, 0xC3, 0xBB))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folder), 0, None, ctypes.byref(out)) != 0:
            return None
        try:
            return Path(out.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    except Exception:
        return None


def safe_name(name: str) -> str:
    cleaned = re.sub(r'[^\w \-().,\']+', '', str(name or ''), flags=re.UNICODE).strip(' .')
    return cleaned[:80] or 'Dannify'


def save_png(name: str, data: bytes, folder: Optional[Path] = None) -> Path:
    """Write *data* as ``<name>.png`` in the Dannify pictures folder, never
    over a picture already there. Raises ValueError for anything not a PNG."""

    if not data.startswith(PNG) or len(data) > MAX_BYTES:
        raise ValueError('not a picture Dannify made')
    folder = folder or (pictures_dir() / 'Dannify')
    folder.mkdir(parents=True, exist_ok=True)
    base = safe_name(name)
    path = folder / f'{base}.png'
    n = 2
    while path.exists():
        path = folder / f'{base} ({n}).png'
        n += 1
    path.write_bytes(data)
    return path


def reveal(path: Path) -> bool:
    """Show the picture in the file manager, selected where it can be."""

    try:
        if sys.platform == 'win32':
            subprocess.Popen(['explorer', f'/select,{path}'])  # noqa: S603, S607
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', '-R', str(path)])  # noqa: S603, S607
        else:
            subprocess.Popen(['xdg-open', str(path.parent)])  # noqa: S603, S607
        return True
    except OSError:
        logger.opt(exception=True).debug('could not show {}', path)
        return False
