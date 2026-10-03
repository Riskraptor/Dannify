"""A problem report: the app's logs and what it runs on, in one zip file.

Somebody whose app misbehaves can send one file instead of being walked
through finding a log in a hidden folder. What goes in: the logs (rotated
ones too), a crash trace if Python ever died hard, the errors the window
reported, and a short note of versions and settings. What stays out:
anything that signs in. Cookie, token and password values are blanked in
the logs as they are copied, and settings are listed without them.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Iterable, Optional

KEEP_REPORTS = 5
MAX_LOG_BYTES = 8 * 1024 * 1024  # per file, newest end kept

# key = value, key: value, "key": "value", with the value blanked.
_SECRET = re.compile(
    r'(?i)(["\']?(?:cookie|set-cookie|authorization|auth|token|access_token|refresh_token|'
    r'password|passwd|secret|sapisid|apisid|hsid|ssid|sid|__secure-[\w-]+|session_key|api_key)'
    r'["\']?\s*[:=]\s*)("[^"]*"|\'[^\']*\'|[^\s,;&]+)'
)
_BEARER = re.compile(r'(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}')

_SECRET_SETTING = re.compile(r'(?i)cookie|token|secret|password|key|auth|session')


def scrub(text: str) -> str:
    """The text with anything that signs in blanked out."""

    text = _SECRET.sub(lambda m: m.group(1) + '<removed>', text)
    return _BEARER.sub(lambda m: m.group(1) + ' <removed>', text)


def _tail(path: Path, limit: int = MAX_LOG_BYTES) -> str:
    size = path.stat().st_size
    with open(path, 'rb') as f:
        if size > limit:
            f.seek(size - limit)
            f.readline()  # start on a whole line
        data = f.read()
    return data.decode('utf-8', errors='replace')


def _logs(data_dir: Path, log_file: Optional[Path]) -> list[Path]:
    found: list[Path] = []
    folders = {data_dir}
    if log_file is not None:
        folders.add(log_file.parent)
    for folder in folders:
        for pattern in ('dannify*.log*', 'crash.log'):
            for p in folder.glob(pattern):
                if p.is_file() and p.stat().st_size > 0 and p not in found:
                    found.append(p)
    return sorted(found, key=lambda p: p.stat().st_mtime)


def _about(version: str, settings: dict[str, Any], facts: dict[str, Any]) -> str:
    lines = [
        f'Dannify {version}',
        f'Made {time.strftime("%Y-%m-%d %H:%M:%S %z")}',
        f'Windows: {platform.platform()} ({platform.machine()})',
        f'Python: {sys.version.split()[0]}, packaged: {bool(getattr(sys, "frozen", False))}',
        '',
    ]
    for key, value in facts.items():
        lines.append(f'{key}: {value}')
    lines += ['', 'Settings:']
    for key in sorted(settings):
        if _SECRET_SETTING.search(key):
            continue
        lines.append(f'  {key}: {json.dumps(settings[key], ensure_ascii=False, default=str)[:300]}')
    return '\n'.join(lines) + '\n'


def build(
    data_dir: Path,
    version: str,
    *,
    settings: Optional[dict[str, Any]] = None,
    facts: Optional[dict[str, Any]] = None,
    window_errors: Iterable[Any] = (),
    log_file: Optional[Path] = None,
) -> Path:
    """Write a report into ``<data_dir>/reports`` and return its path."""

    folder = Path(data_dir) / 'reports'
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    path = folder / f'Dannify-report-{stamp}.zip'
    part = path.with_name(path.name + '.part')

    with zipfile.ZipFile(part, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('about.txt', scrub(_about(version, settings or {}, facts or {})))
        for log in _logs(Path(data_dir), log_file):
            try:
                z.writestr(f'logs/{log.name}', scrub(_tail(log)))
            except OSError:
                continue
        errors = [e for e in window_errors if e]
        if errors:
            z.writestr(
                'window-errors.json',
                scrub(json.dumps(errors, ensure_ascii=False, indent=2, default=str)),
            )
    os.replace(part, path)

    # Only the last few: each one holds the whole log.
    old = sorted(folder.glob('Dannify-report-*.zip'), key=lambda p: p.stat().st_mtime)
    for stale in old[:-KEEP_REPORTS]:
        try:
            stale.unlink()
        except OSError:
            pass
    return path
