"""Problem reports, sent from inside the app.

Somebody whose app misbehaves says what happened in a few words; the app adds
what the developer needs to see it (its logs, the errors the window ran into,
versions and settings) and sends the lot. Nothing is saved for the person to
find and attach: the report goes, or waits in the app's own data folder and
goes when the connection is back.

What never goes: anything that signs in. Cookie, token and password values are
blanked in the logs as they are packed, and settings are listed without them.

Reporting opens when ``REPORT_ENDPOINT`` names the server that takes them.
Until then the window shows the option as coming soon, and nothing is sent.

The server's side, for whoever writes it: an HTTPS ``POST`` of
``multipart/form-data`` with the fields ``id``, ``version``, ``category``,
``description`` and ``contact`` (may be empty), and, when the person chose to
include it, a file field ``diagnostics`` holding a zip (``about.txt``,
``logs/*``, ``window-errors.json``). Any 2xx answer means received.
"""

from __future__ import annotations

import io
import json
import os
import platform
import re
import secrets
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Iterable, Optional

from loguru import logger

# Where reports go. Empty: not open yet (see the module notes).
REPORT_ENDPOINT = ''

CATEGORIES = ('playback', 'downloads', 'lyrics', 'looks', 'crash', 'other')
DESCRIPTION_MIN = 10
DESCRIPTION_MAX = 5000
CONTACT_MAX = 200

MAX_LOG_BYTES = 2 * 1024 * 1024  # per file, newest end kept
MAX_DIAGNOSTICS = 6 * 1024 * 1024  # the packed zip, at most
OUTBOX_KEEP = 5  # reports waiting to go, at most
OUTBOX_DAYS = 14  # one that has not gone by then is let go

# key = value, key: value, "key": "value", with the value blanked.
_SECRET = re.compile(
    r'(?i)(["\']?(?:cookie|set-cookie|authorization|auth|token|access_token|refresh_token|'
    r'password|passwd|secret|sapisid|apisid|hsid|ssid|sid|__secure-[\w-]+|session_key|api_key)'
    r'["\']?\s*[:=]\s*)("[^"]*"|\'[^\']*\'|[^\s,;&]+)'
)
_BEARER = re.compile(r'(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}')
_SECRET_SETTING = re.compile(r'(?i)cookie|token|secret|password|key|auth|session')
_EMAIL = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$')


def scrub(text: str) -> str:
    """The text with anything that signs in blanked out."""

    text = _SECRET.sub(lambda m: m.group(1) + '<removed>', text)
    return _BEARER.sub(lambda m: m.group(1) + ' <removed>', text)


# ---------------------------------------------------------------------------
# Where to, and whether at all
# ---------------------------------------------------------------------------


def endpoint() -> str:
    """The server reports go to, or '' while reporting is not open.

    A development run may point it anywhere with ``DANNIFY_REPORT_URL``; a
    shipped copy only at this machine (the tests' stand-in server), so the
    variable cannot send anyone's logs somewhere else.
    """

    override = os.getenv('DANNIFY_REPORT_URL', '').strip()
    if override:
        local = re.match(r'^http://(127\.0\.0\.1|localhost)(:\d+)?(/|$)', override)
        if local or not getattr(sys, 'frozen', False):
            return override
    return REPORT_ENDPOINT


def enabled() -> bool:
    return bool(endpoint())


# ---------------------------------------------------------------------------
# What goes in it
# ---------------------------------------------------------------------------


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
    folders = {Path(data_dir)}
    if log_file is not None:
        folders.add(Path(log_file).parent)
    for folder in folders:
        for pattern in ('dannify*.log*', 'crash.log'):
            for p in folder.glob(pattern):
                if p.is_file() and p.stat().st_size > 0 and p not in found:
                    found.append(p)
    # Newest last, so when the zip has to stay small the oldest go first.
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


def pack(
    data_dir: Path,
    version: str,
    *,
    settings: Optional[dict[str, Any]] = None,
    facts: Optional[dict[str, Any]] = None,
    window_errors: Iterable[Any] = (),
    log_file: Optional[Path] = None,
    limit: int = MAX_DIAGNOSTICS,
) -> bytes:
    """The diagnostics, as a zip in memory. Logs are dropped oldest first
    when the whole would be bigger than ``limit``."""

    about = scrub(_about(version, settings or {}, facts or {}))
    errors = [e for e in window_errors if e]
    error_text = scrub(json.dumps(errors, ensure_ascii=False, indent=2, default=str)) if errors else ''
    logs = []
    for log in _logs(Path(data_dir), log_file):
        try:
            logs.append((log.name, scrub(_tail(log))))
        except OSError:
            continue

    while True:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('about.txt', about)
            if error_text:
                z.writestr('window-errors.json', error_text)
            for name, text in logs:
                z.writestr(f'logs/{name}', text)
        data = buffer.getvalue()
        if len(data) <= limit or not logs:
            return data
        logs.pop(0)


def new_id() -> str:
    """Short enough to read out to someone: 8 letters and digits."""

    return secrets.token_hex(4).upper()


def clean_fields(description: Any, category: Any, contact: Any) -> dict[str, str]:
    """What the person typed, checked. Raises ValueError with a reason."""

    text = str(description or '').strip()
    if len(text) < DESCRIPTION_MIN:
        raise ValueError('description too short')
    text = text[:DESCRIPTION_MAX]
    kind = str(category or 'other').strip().lower()
    if kind not in CATEGORIES:
        kind = 'other'
    who = str(contact or '').strip()[:CONTACT_MAX]
    if who and not _EMAIL.match(who):
        raise ValueError('contact is not an email address')
    return {'description': text, 'category': kind, 'contact': who}


# ---------------------------------------------------------------------------
# Sending, and waiting to send
# ---------------------------------------------------------------------------


class NotOpen(RuntimeError):
    """Reporting has no server yet."""


def post(report: dict[str, Any], url: str, timeout: float = 30.0) -> None:
    """Send one report. Raises when it did not arrive."""

    import requests

    fields = {k: str(report.get(k) or '') for k in ('id', 'version', 'category', 'description', 'contact')}
    files = None
    if report.get('diagnostics'):
        files = {'diagnostics': (f'dannify-{fields["id"]}.zip', report['diagnostics'], 'application/zip')}
    response = requests.post(
        url,
        data=fields,
        files=files,
        timeout=timeout,
        headers={'User-Agent': f'Dannify/{fields["version"]}'},
    )
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f'report server answered {response.status_code}')


def _outbox(data_dir: Path) -> Path:
    return Path(data_dir) / 'reports' / 'outbox'


def queue(data_dir: Path, report: dict[str, Any]) -> None:
    """Keep a report to send later, in the app's data folder."""

    box = _outbox(data_dir)
    box.mkdir(parents=True, exist_ok=True)
    rid = re.sub(r'[^A-Z0-9]', '', str(report['id']))[:16] or new_id()
    fields = {k: report.get(k, '') for k in ('id', 'version', 'category', 'description', 'contact')}
    fields['queued'] = time.time()
    if report.get('diagnostics'):
        (box / f'{rid}.zip').write_bytes(report['diagnostics'])
    (box / f'{rid}.json').write_text(json.dumps(fields, ensure_ascii=False), encoding='utf-8')
    waiting = sorted(box.glob('*.json'), key=lambda p: p.stat().st_mtime)
    for old in waiting[:-OUTBOX_KEEP]:
        _drop(old)


def _drop(meta: Path) -> None:
    meta.unlink(missing_ok=True)
    meta.with_suffix('.zip').unlink(missing_ok=True)


def pending(data_dir: Path) -> int:
    box = _outbox(data_dir)
    return len(list(box.glob('*.json'))) if box.is_dir() else 0


def flush(data_dir: Path) -> tuple[int, int]:
    """Send what is waiting. Returns (sent, still waiting)."""

    url = endpoint()
    box = _outbox(data_dir)
    if not box.is_dir():
        return 0, 0
    sent = 0
    for meta in sorted(box.glob('*.json'), key=lambda p: p.stat().st_mtime):
        try:
            fields = json.loads(meta.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            _drop(meta)
            continue
        if time.time() - float(fields.get('queued') or 0) > OUTBOX_DAYS * 86400:
            _drop(meta)
            continue
        if not url:
            continue
        zipped = meta.with_suffix('.zip')
        report = {**fields, 'diagnostics': zipped.read_bytes() if zipped.is_file() else None}
        try:
            post(report, url)
        except Exception:
            logger.opt(exception=True).debug('waiting report {} still not sent', fields.get('id'))
            break  # the connection is the likely reason; the rest can wait too
        _drop(meta)
        sent += 1
    return sent, pending(data_dir)


def send(data_dir: Path, report: dict[str, Any]) -> str:
    """Send a report now, or keep it to send later. Returns 'sent' or 'queued'."""

    url = endpoint()
    if not url:
        raise NotOpen('reporting is not open yet')
    try:
        post(report, url)
        return 'sent'
    except Exception:
        logger.opt(exception=True).info('report {} could not be sent now; it will go later', report.get('id'))
        queue(data_dir, report)
        return 'queued'


def tidy_old_exports(data_dir: Path) -> int:
    """Remove the zip files 4.3 and 4.4 saved for people to send by hand."""

    removed = 0
    folder = Path(data_dir) / 'reports'
    for old in folder.glob('Dannify-report-*.zip*') if folder.is_dir() else ():
        try:
            old.unlink()
            removed += 1
        except OSError:
            pass
    return removed
