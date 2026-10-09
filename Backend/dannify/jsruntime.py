"""The JavaScript runtime yt-dlp needs to play anything from YouTube.

Since mid-2026 YouTube ciphers every audio URL behind a "signature" and an
"n" challenge that can only be solved by running their player JavaScript.
Without a JS engine yt-dlp gets back storyboards and nothing else, and every
track fails with "Requested format is not available".

yt-dlp can drive deno, node, bun or quickjs, but only looks for deno by
default and none of them ship with Windows. So Dannify carries its own:
QuickJS is a single small executable (MIT), which is three orders of
magnitude smaller than bundling Node or Deno for the same job.

An engine already on the user's PATH is preferred when it is faster, but
only one new enough for yt-dlp: Ubuntu 24.04's Node is 18, which yt-dlp
refuses, and picking it meant nothing played there at all.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from .osenv import IS_WINDOWS, PLATFORM, exe_names

# The oldest of each that yt-dlp's challenge solver accepts.
_MINIMUM = {
    'deno': (2, 3, 0),
    'bun': (1, 2, 11),
    'node': (22, 0, 0),
}

# Fastest first. quickjs is last because it is ours and always present, so it
# only runs when the machine has nothing better.
_PATH_RUNTIMES = (
    ('deno', 'deno'),
    ('bun', 'bun'),
    ('node', 'node'),
    ('quickjs', 'qjs'),
)

_resolved: Optional[dict[str, Any]] = None
_cache_dir: Optional[Path] = None


def init(data_dir: Path) -> None:
    """Point yt-dlp's player cache somewhere that survives restarts."""
    global _cache_dir
    _cache_dir = Path(data_dir) / 'ytdlp-cache'
    try:
        _cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        _cache_dir = None


def _bundled(folder: str, *names: str) -> Optional[Path]:
    """Find one of *names* in a bundled folder, frozen or from source."""
    roots = []
    if getattr(sys, 'frozen', False):
        roots.append(Path(getattr(sys, '_MEIPASS', '.')) / folder)
        roots.append(Path(sys.executable).parent / folder)
    else:
        top = Path(__file__).resolve().parents[2]
        # The Linux package keeps its tools beside the app; a checkout keeps
        # the Windows ones in packaging/ and the others in packaging/<platform>.
        roots.append(top / folder)
        roots.append(top / 'packaging' / ('' if IS_WINDOWS else PLATFORM) / folder)
    for root in roots:
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return candidate
    return None


def bundled_qjs() -> Optional[Path]:
    """The JS engine we ship. Named for this app, not for the project it
    came from, so the install folder gives nothing away."""
    return _bundled('jsruntime', *exe_names('dnfjs', 'qjs'))


def media_tool() -> Optional[Path]:
    """The bundled media encoder (ffmpeg under our own name)."""
    return _bundled('media', *exe_names('dnfmedia', 'ffmpeg'))


def _version(path: str) -> Optional[tuple[int, ...]]:
    """What `<runtime> --version` says, as numbers, or None."""

    try:
        out = subprocess.run(
            [path, '--version'], capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    found = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', out or '')
    if not found:
        return None
    return tuple(int(g or 0) for g in found.groups())


def _new_enough(name: str, path: str) -> bool:
    need = _MINIMUM.get(name)
    if need is None:
        return True  # quickjs prints no version; any build since 2023 works
    have = _version(path)
    if have is None or have < need:
        logger.info('JS runtime: skipping {} {} at {} (yt-dlp needs {})',
                    name, '.'.join(map(str, have or ())) or '?', path, '.'.join(map(str, need)))
        return False
    return True


def _resolve() -> dict[str, Any]:
    """Pick a runtime once and remember it."""
    for name, executable in _PATH_RUNTIMES:
        found = shutil.which(executable)
        if found and _new_enough(name, found):
            logger.info('JS runtime: {} ({})', name, found)
            return {name: {'path': found}}
    qjs = bundled_qjs()
    if qjs is not None:
        logger.info('JS runtime: bundled quickjs ({})', qjs)
        return {'quickjs': {'path': str(qjs)}}
    logger.warning(
        'No JavaScript runtime found. YouTube playback and downloads will '
        'fail until one is available.'
    )
    return {}


def runtimes() -> dict[str, Any]:
    global _resolved
    if _resolved is None:
        _resolved = _resolve()
    return _resolved


def apply(opts: dict[str, Any]) -> dict[str, Any]:
    """Add the JS runtime, media tool and player cache to yt-dlp options."""
    found = runtimes()
    if found:
        opts['js_runtimes'] = found
    tool = media_tool()
    if tool is not None:
        # Point yt-dlp straight at our copy: it would otherwise hunt for a
        # file literally called ffmpeg.exe, which we no longer ship.
        opts.setdefault('ffmpeg_location', str(tool))
    if _cache_dir is not None:
        # Solving the player is the slow part of a cold extraction, and the
        # result is per player version, not per track: caching it on disk
        # means the cost is paid once per YouTube rollout, not once per song.
        opts['cachedir'] = str(_cache_dir)
    return opts
