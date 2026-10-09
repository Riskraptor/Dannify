"""What each platform's release files are called, and what each is signed as.

One release carries every platform's files, so the names decide who takes
what. Copies of 4.7.0 on Windows pick their update by name shape: anything
starting with ``package-``, and the first ``.exe`` with "setup" in its name.
So no other platform's file may ever look like either. Linux and macOS files
start with their platform's name instead.

Each kind of file is also signed as its own kind (see signing.statement),
platform and processor included, so a signature made for one file can never
be passed off for another platform's: the Windows kinds stay exactly
'installer' and 'package', which is what 4.7.0 checks.
"""

from __future__ import annotations

import platform as _platform
import re
from typing import Optional

from .osenv import IS_MAC, IS_WINDOWS

WINDOWS_INSTALLER = 'installer'
WINDOWS_PACKAGE = 'package'


def linux_arch() -> str:
    machine = _platform.machine().lower()
    return 'arm64' if machine in ('aarch64', 'arm64') else 'amd64'


def macos_arch() -> str:
    machine = _platform.machine().lower()
    return 'arm64' if machine in ('arm64', 'aarch64') else 'x64'


def linux_deb(version: str, arch: str) -> str:
    return f'linux-dannify_{version}_{arch}.deb'


def macos_zip(version: str, arch: str) -> str:
    return f'macos-Dannify-{version}-{arch}.zip'


def macos_dmg(version: str, arch: str) -> str:
    return f'macos-Dannify-{version}-{arch}.dmg'


_SHAPES = (
    (re.compile(r'^Dannify-Setup-(?P<v>[0-9][0-9A-Za-z.+-]*)\.exe$'), lambda m: WINDOWS_INSTALLER),
    (re.compile(r'^package-(?P<v>[0-9][0-9A-Za-z.+-]*)\.json$'), lambda m: WINDOWS_PACKAGE),
    (re.compile(r'^linux-dannify_(?P<v>[0-9][0-9A-Za-z.+-]*)_(?P<a>amd64|arm64)\.deb$'),
     lambda m: f"installer-linux-deb-{m['a']}"),
    (re.compile(r'^macos-Dannify-(?P<v>[0-9][0-9A-Za-z.+]*)-(?P<a>arm64|x64)\.zip$'),
     lambda m: f"app-macos-zip-{m['a']}"),
    (re.compile(r'^macos-Dannify-(?P<v>[0-9][0-9A-Za-z.+]*)-(?P<a>arm64|x64)\.dmg$'),
     lambda m: f"installer-macos-dmg-{m['a']}"),
)


def describe(name: str) -> Optional[tuple[str, str]]:
    """(kind, version) a release file is signed as, or None if it is not one."""

    for shape, kind in _SHAPES:
        found = shape.match(name)
        if found:
            return kind(found), found['v']
    return None


def own_update(version: str) -> Optional[tuple[str, str]]:
    """(file name, signed kind) of this platform's whole-app update, if the
    platform takes one (Windows updates through its package instead)."""

    if IS_WINDOWS:
        return None
    if IS_MAC:
        arch = macos_arch()
        return macos_zip(version, arch), f'app-macos-zip-{arch}'
    arch = linux_arch()
    return linux_deb(version, arch), f'installer-linux-deb-{arch}'
