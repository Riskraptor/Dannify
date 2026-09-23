"""The JavaScript runtime yt-dlp needs to play anything from YouTube.

Since mid-2026 YouTube ciphers every audio URL behind a "signature" and an
"n" challenge that can only be solved by running their player JavaScript.
Without a JS engine yt-dlp gets back storyboards and nothing else, and every
track fails with "Requested format is not available".

yt-dlp can drive deno, node, bun or quickjs, but only looks for deno by
default and none of them ship with Windows. So Dannify carries its own:
quickjs-ng is a single 2 MB executable (MIT), which is three orders of
magnitude smaller than bundling Node or Deno for the same job.

An engine already on the user's PATH is preferred when it is faster.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

from loguru import logger

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
        roots.append(Path(__file__).resolve().parents[2] / 'packaging' / folder)
    for root in roots:
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return candidate
    return None


def bundled_qjs() -> Optional[Path]:
    """The JS engine we ship. Named for this app, not for the project it
    came from, so the install folder gives nothing away."""
    return _bundled('jsruntime', 'dnfjs.exe', 'qjs.exe', 'dnfjs', 'qjs')


def media_tool() -> Optional[Path]:
    """The bundled media encoder (ffmpeg under our own name)."""
    return _bundled('media', 'dnfmedia.exe', 'ffmpeg.exe', 'dnfmedia', 'ffmpeg')


def _resolve() -> dict[str, Any]:
    """Pick a runtime once and remember it."""
    for name, executable in _PATH_RUNTIMES:
        found = shutil.which(executable)
        if found:
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
