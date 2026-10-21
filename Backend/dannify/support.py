"""Ways to support Dannify: GitHub Sponsors first, M-Pesa in Kenya, and
Ko-fi and PayPal when they are set.

Links opened in the user's browser, and an M-Pesa number to pay to from a
phone. No keys, no checkout page, no card details anywhere near the app.
Set them in one of these, last one wins:

* ``config/support.json`` next to the exe, shipped with the build;
* ``support.json`` in the data folder, per user;
* ``DANNIFY_SUPPORT_LINK`` / ``DANNIFY_SUPPORT_DISABLED`` in the environment.

The PayPal link, the M-Pesa number, the Ko-fi page and the message can also
change between releases: ``config/support-live.json`` on the repository's main
branch, signed with the release key (see ``accept_live`` and
``packaging/support_details.py``).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

from loguru import logger

_DEFAULTS: dict[str, Any] = {
    'enabled': True,
    # GitHub Sponsors: the GitHub account to sponsor. Monthly or one time,
    # any amount, by card from anywhere; GitHub keeps no fee.
    'github': 'Riskraptor',
    # A page to give on (Ko-fi was the first): none since 4.14.1.
    'link': '',
    'message': '',
    # Lipa na M-Pesa: {'kind': 'till' | 'paybill', 'number': '...',
    # 'account': '...' (a paybill's account), 'name': '...' (as M-Pesa
    # shows it, so the payer knows they have the right one)}.
    'mpesa': {'kind': 'till', 'number': '8496746'},
    # A paypal.me name, or a PayPal payment link
    # (https://www.paypal.com/ncp/payment/...): none since 4.14.1.
    'paypal': '',
}

_config: dict[str, Any] = dict(_DEFAULTS)

# ---------------------------------------------------------------------------
# Changed without a release
# ---------------------------------------------------------------------------
# A signed file on the repository's main branch says what the PayPal link,
# the M-Pesa number and the message are now. It is believed only when it
# verifies against the release key's public half (updates.PUBLIC_KEY) and is
# no older than the one already kept: neither a changed file nor an old one
# put back can send anyone's money somewhere else. Kept in the data folder,
# signature and all, so it holds offline and is checked again at every start.
LIVE_NAME = 'support-live.json'
LIVE_KIND = 'support'
LIVE_FIELDS = ('paypal', 'mpesa', 'link', 'message', 'github')
LIVE_EVERY = 12 * 3600
_live: dict[str, Any] = {}
_live_dir: Optional[Path] = None
_live_lock = threading.Lock()


def accept_live(raw: bytes, signature: str, public_hex: str, newer_than: int = 0) -> Optional[dict[str, Any]]:
    """The details in *raw*, if *signature* is the release key's over them and
    their version is not older than *newer_than*; else None."""

    from . import signing

    try:
        data = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    version = data.get('version')
    if not isinstance(version, int) or isinstance(version, bool) or version < max(1, newer_than):
        return None
    digest = hashlib.sha256(raw).hexdigest()
    if not signing.verify_release(public_hex, LIVE_KIND, str(version), digest, signature):
        return None
    out = {k: data[k] for k in LIVE_FIELDS if k in data}
    out['version'] = version
    return out


def _live_files() -> tuple[Optional[Path], Optional[Path]]:
    if _live_dir is None:
        return None, None
    from . import signing

    path = _live_dir / LIVE_NAME
    return path, path.with_name(path.name + signing.SIGNATURE_SUFFIX)


def _load_kept_live() -> None:
    from . import updates

    path, sig = _live_files()
    if path is None:
        return
    try:
        raw, signature = path.read_bytes(), sig.read_text(encoding='utf-8')
    except OSError:
        return
    found = accept_live(raw, signature, updates.PUBLIC_KEY)
    with _live_lock:
        _live.clear()
        if found:
            _live.update(found)


def refresh_live() -> bool:
    """Fetch the signed details from the repository; keep them if they are
    good and at least as new as what is kept. Whether they changed."""

    from . import signing, updates

    path, sig = _live_files()
    if path is None or not updates.PUBLIC_KEY:
        return False
    base = f'https://raw.githubusercontent.com/{updates.repo()}/main/config/{LIVE_NAME}'

    def get(url: str) -> bytes:
        request = urllib.request.Request(url, headers={'User-Agent': 'Dannify', 'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read(64 * 1024)

    try:
        raw = get(base)
        signature = get(base + signing.SIGNATURE_SUFFIX).decode('utf-8', 'replace')
    except Exception as exc:
        logger.debug('support details not fetched: {}', exc)
        return False
    with _live_lock:
        kept = int(_live.get('version') or 0)
    found = accept_live(raw, signature, updates.PUBLIC_KEY, newer_than=kept)
    if not found:
        logger.warning('support details on {} were not accepted', base)
        return False
    if found == {k: v for k, v in _live.items()}:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        sig.write_text(signature, encoding='utf-8')
    except OSError:
        logger.opt(exception=True).debug('support details not kept')
    with _live_lock:
        _live.clear()
        _live.update(found)
    logger.info('support details {} in use', found['version'])
    return True


def start_live_refresh() -> None:
    """Look for new details now and twice a day, in the background."""

    def loop() -> None:
        while True:
            try:
                refresh_live()
            except Exception:
                logger.opt(exception=True).debug('support details check failed')
            time.sleep(LIVE_EVERY)

    threading.Thread(target=loop, name='support-live', daemon=True).start()


def _current() -> dict[str, Any]:
    """The settings in force: the built-in ones, the signed details over them."""

    with _live_lock:
        live = {k: v for k, v in _live.items() if k in LIVE_FIELDS}
    return {**_config, **live}


def config_paths(data_dir: Path, name: str) -> list[Path]:
    """Where a drop-in config file may live, lowest precedence first.

    ``<install dir>/config/<name>`` lets whoever packages the build ship
    settings for every user; ``<data dir>/<name>`` is the per-user override.
    """

    import sys

    # A shipped copy reads none: what it updates from and where it sends
    # people is built in, not a file anyone can edit to point it somewhere
    # else. The files are for development and packaging tests.
    if getattr(sys, 'frozen', False):
        return []
    return [
        Path(__file__).resolve().parents[2] / 'packaging' / 'config' / name,
        Path(data_dir) / name,
    ]


def init(data_dir: Path) -> None:
    config = dict(_DEFAULTS)
    for path in config_paths(data_dir, 'support.json'):
        try:
            stored = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(stored, dict):
                config.update({k: v for k, v in stored.items() if k in _DEFAULTS})
        except FileNotFoundError:
            continue
        except Exception:
            logger.opt(exception=True).debug('Could not read {}', path)

    import sys

    if not getattr(sys, 'frozen', False):
        link = os.getenv('DANNIFY_SUPPORT_LINK', '').strip()
        if link:
            config['link'] = link
        if os.getenv('DANNIFY_SUPPORT_DISABLED', '').strip().lower() in ('1', 'true', 'yes'):
            config['enabled'] = False

    _config.clear()
    _config.update(config)
    global _live_dir
    _live_dir = Path(data_dir)
    _load_kept_live()


def _link() -> str:
    """The Ko-fi (or any other) page to give on: an https address, or none."""

    link = str(_current().get('link') or '').strip()
    return link if re.fullmatch(r'https://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/[^\s]*)?', link) else ''


def _sponsors_link() -> str:
    """The GitHub Sponsors page of the account named, checked as GitHub names
    accounts: letters, digits and single hyphens, at most 39."""

    current = _current()
    login = str(current.get('github') or '').strip()
    if not current.get('enabled') or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}', login):
        return ''
    return f'https://github.com/sponsors/{login}'


def configured() -> bool:
    """Whether there is any way to give from anywhere (M-Pesa is Kenya only)."""

    return bool(_config.get('enabled') and (_sponsors_link() or _link() or _paypal_link()))


def _mpesa() -> dict[str, str]:
    """The M-Pesa way to pay, checked: digits only, a kind M-Pesa has."""

    current = _current()
    raw = current.get('mpesa') or {}
    if not isinstance(raw, dict) or not current.get('enabled'):
        return {}
    kind = str(raw.get('kind') or '').strip().lower()
    number = re.sub(r'\D', '', str(raw.get('number') or ''))
    if kind not in ('till', 'paybill') or not 5 <= len(number) <= 10:
        return {}
    out = {'kind': kind, 'number': number, 'name': str(raw.get('name') or '').strip()[:60]}
    if kind == 'paybill':
        out['account'] = re.sub(r'[^0-9A-Za-z -]', '', str(raw.get('account') or '')).strip()[:30]
    return out


def _paypal_link() -> str:
    current = _current()
    raw = str(current.get('paypal') or '').strip()
    if not current.get('enabled') or not raw:
        return ''
    # A payment link made in PayPal: a checkout of its own, kept as it is.
    link = re.fullmatch(r'https://www\.paypal\.com/ncp/payment/([A-Z0-9][A-Z0-9-]{5,40})/?', raw)
    if link:
        return f'https://www.paypal.com/ncp/payment/{link.group(1)}'
    # A paypal.me name, alone or as its whole address; any other address is
    # not taken, however it ends.
    me = re.fullmatch(r'(?:https?://(?:www\.)?paypal\.me/|https://www\.paypal\.com/paypalme/)?([A-Za-z0-9_-]{2,40})/?', raw)
    if not me:
        return ''
    name = me.group(1)
    return f'https://www.paypal.com/paypalme/{name}'


def config() -> dict[str, Any]:
    return {
        'enabled': bool(_config.get('enabled')),
        'configured': configured(),
        'link': _link(),
        'sponsors_link': _sponsors_link(),
        'message': str(_current().get('message') or '')[:300],
        'mpesa': _mpesa(),
        'paypal_link': _paypal_link(),
    }
