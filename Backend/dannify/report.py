"""Problem reports, sent from inside the app.

Somebody whose app misbehaves says what happened in a few words; the app adds
what the developer needs to see it (its logs, the errors the window ran into,
versions and settings) and sends the lot. Nothing is saved for the person to
find and attach: the report goes, or waits in the app's own data folder and
goes when the connection is back.

What never goes: anything that signs in. Cookie, token and password values are
blanked in the logs as they are packed, and settings are listed without them.

Reporting opens when there is somewhere for reports to go: the developer's
email, by way of Web3Forms (``WEB3FORMS_KEY``, the form's public access key;
the address itself is never in the app), or a server of its own
(``REPORT_ENDPOINT``). Until then the window shows the option as coming soon,
and nothing is sent.

By email, the diagnostics are written into the message (a free form has no
attachments): what ``about.txt`` says, the window's errors, and the newest end
of the log, all scrubbed like the zip. A free Web3Forms form takes
submissions from a browser only, so the app puts the email together here and
its window sends it (``prepare``); one that cannot go yet waits in the outbox
(``hold``) and the window sends it later.

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
# The Web3Forms form that emails reports to the developer. Public by design:
# it names the form, not the inbox, and a form only ever emails its owner.
WEB3FORMS_KEY = ''
WEB3FORMS_URL = 'https://api.web3forms.com/submit'

CATEGORIES = ('playback', 'downloads', 'lyrics', 'looks', 'crash', 'idea', 'other')
# At most this many reports a day from one copy: a stuck button, or someone
# leaning on it, must not fill the developer's inbox.
DAILY_LIMIT = 5
# By email, how much of the diagnostics goes in the message.
EMAIL_DIAGNOSTICS_MAX = 60_000
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


def web3forms_key() -> str:
    """The Web3Forms access key reports are emailed with, or ''.

    A development run may set ``DANNIFY_WEB3FORMS_KEY``; a shipped copy uses
    the one built in, so no setting can send anyone's report elsewhere.
    """

    override = os.getenv('DANNIFY_WEB3FORMS_KEY', '').strip()
    if override and not getattr(sys, 'frozen', False):
        return override
    return WEB3FORMS_KEY


def enabled() -> bool:
    return bool(endpoint() or web3forms_key())


def mode() -> str:
    """'server' when reports go to a server of their own, 'email' when the
    window emails them, '' while reporting is closed."""

    if endpoint():
        return 'server'
    return 'email' if web3forms_key() else ''


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
    used: set[str] = set()
    for log in _logs(Path(data_dir), log_file):
        try:
            text = scrub(_tail(log))
        except OSError:
            continue
        # Two folders can each hold a dannify.log: both go in, under names
        # of their own, not one written over the other in the zip.
        name, n = log.name, 2
        while name in used:
            name = f'{log.stem}-{n}{log.suffix}'
            n += 1
        used.add(name)
        logs.append((name, text))

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
    """Reporting has nowhere to go yet."""


class TooMany(RuntimeError):
    """This copy has sent its reports for today."""


def email_text(report: dict[str, Any]) -> str:
    """The report as the developer reads it in their inbox."""

    lines = [
        str(report.get('description') or '').strip(),
        '',
        '---',
        f"Report {report.get('id', '')} · Dannify {report.get('version', '')} · {report.get('category', '')}",
        f"Reply to: {report.get('contact') or 'not given'}",
    ]
    zipped = report.get('diagnostics')
    if zipped:
        lines += ['', '=== Diagnostics ===', '']
        lines.append(_diagnostics_text(zipped, EMAIL_DIAGNOSTICS_MAX))
    return '\n'.join(lines)


def _diagnostics_text(zipped: bytes, limit: int) -> str:
    """What the diagnostics zip says, as text: everything about the app and
    its window errors, then the newest end of the logs, in *limit* characters."""

    parts: list[str] = []
    logs: list[tuple[str, str]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(zipped)) as z:
            for name in z.namelist():
                text = z.read(name).decode('utf-8', errors='replace')
                if name.startswith('logs/'):
                    logs.append((name, text))
                else:
                    parts.append(f'--- {name} ---\n{text.strip()}')
    except zipfile.BadZipFile:
        return '(diagnostics could not be read)'
    head = '\n\n'.join(parts)[:limit]
    room = limit - len(head)
    # The newest log last in the zip; its end matters most, so what is let go
    # to fit is always the oldest end, never the last lines.
    tail_parts: list[str] = []
    for name, text in reversed(logs):
        title = f'--- {name} (newest end) ---\n'
        fits = room - len(title) - 2  # and the blank line before it
        if fits <= 200:
            break
        text = text.strip()
        piece = text[-fits:]
        if len(piece) < len(text):
            piece = piece[piece.find('\n') + 1:]
        tail_parts.insert(0, title + piece)
        room -= len(title) + len(piece) + 2
    return '\n\n'.join([head, *tail_parts])


def email_body(report: dict[str, Any], key: str) -> dict[str, Any]:
    """What Web3Forms is sent for one report."""

    body = {
        'access_key': key,
        'subject': f"Dannify {report.get('version', '')}: {report.get('category', 'other')} ({report.get('id', '')})",
        'from_name': 'Dannify',
        'message': email_text(report),
        'report_id': str(report.get('id') or ''),
        'version': str(report.get('version') or ''),
        'category': str(report.get('category') or ''),
        'botcheck': False,
    }
    if report.get('contact'):
        body['email'] = str(report['contact'])  # the inbox's Reply goes to them
    return body


def post_email(report: dict[str, Any], key: str, timeout: float = 30.0) -> None:
    """Email one report through Web3Forms. Raises when it did not arrive."""

    import requests

    body = email_body(report, key)
    response = requests.post(
        WEB3FORMS_URL,
        json=body,
        timeout=timeout,
        headers={'Accept': 'application/json', 'User-Agent': f"Dannify/{report.get('version', '')}"},
    )
    try:
        answer = response.json()
    except ValueError:
        answer = {}
    if not (200 <= response.status_code < 300 and answer.get('success')):
        raise RuntimeError(f"Web3Forms answered {response.status_code}: {str(answer.get('message', ''))[:200]}")


def deliver(report: dict[str, Any]) -> None:
    """Send one report wherever reports go: its own server, else by email."""

    url = endpoint()
    if url:
        return post(report, url)
    key = web3forms_key()
    if key:
        return post_email(report, key)
    raise NotOpen('reporting is not open yet')


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
    if not box.is_dir():
        return 0
    emails = _held(data_dir)
    return len(list(box.glob('*.json'))) + (len(list(emails.glob('*.json'))) if emails.is_dir() else 0)


def flush(data_dir: Path) -> tuple[int, int]:
    """Send what is waiting. Returns (sent, still waiting)."""

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
        if not enabled():
            continue
        zipped = meta.with_suffix('.zip')
        report = {**fields, 'diagnostics': zipped.read_bytes() if zipped.is_file() else None}
        try:
            deliver(report)
        except Exception:
            logger.opt(exception=True).debug('waiting report {} still not sent', fields.get('id'))
            break  # the connection is the likely reason; the rest can wait too
        _drop(meta)
        sent += 1
    return sent, pending(data_dir)


def _sent_log(data_dir: Path) -> Path:
    return Path(data_dir) / 'reports' / 'sent.json'


def _sent_today(data_dir: Path) -> list[float]:
    try:
        times = json.loads(_sent_log(data_dir).read_text(encoding='utf-8'))
        return [float(t) for t in times if time.time() - float(t) < 86400]
    except (OSError, ValueError, TypeError):
        return []


def _note_sent(data_dir: Path) -> None:
    times = _sent_today(data_dir) + [time.time()]
    path = _sent_log(data_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(times[-DAILY_LIMIT * 2:]), encoding='utf-8')
    except OSError:
        pass


def prepare(data_dir: Path, report: dict[str, Any]) -> dict[str, Any]:
    """The email for one report, for the window to send (see the module
    notes). Counts towards the day's reports like a send."""

    key = web3forms_key()
    if not key:
        raise NotOpen('reporting is not open yet')
    if len(_sent_today(data_dir)) >= DAILY_LIMIT:
        raise TooMany('enough reports for today')
    _note_sent(data_dir)
    return email_body(report, key)


def _held(data_dir: Path) -> Path:
    return _outbox(data_dir) / 'email'


def hold(data_dir: Path, email: dict[str, Any]) -> None:
    """Keep an email the window could not send, for it to send later."""

    rid = re.sub(r'[^A-Z0-9]', '', str(email.get('report_id') or ''))[:16]
    if not rid or not email.get('message'):
        return
    box = _held(data_dir)
    box.mkdir(parents=True, exist_ok=True)
    (box / f'{rid}.json').write_text(json.dumps({**email, 'held': time.time()}, ensure_ascii=False), encoding='utf-8')
    waiting = sorted(box.glob('*.json'), key=lambda p: p.stat().st_mtime)
    for old in waiting[:-OUTBOX_KEEP]:
        old.unlink(missing_ok=True)


def held(data_dir: Path) -> list[dict[str, Any]]:
    """The emails waiting for the window to send, oldest first. Each gets
    the access key the app has now, which may be newer than when it was kept."""

    box = _held(data_dir)
    out: list[dict[str, Any]] = []
    key = web3forms_key()
    for path in sorted(box.glob('*.json'), key=lambda p: p.stat().st_mtime) if box.is_dir() else ():
        try:
            email = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            continue
        if time.time() - float(email.pop('held', 0) or 0) > OUTBOX_DAYS * 86400:
            path.unlink(missing_ok=True)
            continue
        if key:
            email['access_key'] = key
        out.append(email)
    return out


def done(data_dir: Path, report_id: str) -> None:
    """The window sent it: it waits no more."""

    rid = re.sub(r'[^A-Z0-9]', '', str(report_id or ''))[:16]
    if rid:
        (_held(data_dir) / f'{rid}.json').unlink(missing_ok=True)


def send(data_dir: Path, report: dict[str, Any]) -> str:
    """Send a report now, or keep it to send later. Returns 'sent' or 'queued'."""

    if not enabled():
        raise NotOpen('reporting is not open yet')
    if len(_sent_today(data_dir)) >= DAILY_LIMIT:
        raise TooMany('enough reports for today')
    _note_sent(data_dir)
    try:
        deliver(report)
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
