"""Ways to support Dannify: Ko-fi, M-Pesa and PayPal.

Links opened in the user's browser, and an M-Pesa number to pay to from a
phone. No keys, no checkout page, no card details anywhere near the app.
Set them in one of these, last one wins:

* ``config/support.json`` next to the exe, shipped with the build;
* ``support.json`` in the data folder, per user;
* ``DANNIFY_SUPPORT_LINK`` / ``DANNIFY_SUPPORT_DISABLED`` in the environment.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from loguru import logger

_DEFAULTS: dict[str, Any] = {
    'enabled': True,
    'link': 'https://ko-fi.com/dkavangi',
    'message': '',
    # Lipa na M-Pesa: {'kind': 'till' | 'paybill', 'number': '...',
    # 'account': '...' (a paybill's account), 'name': '...' (as M-Pesa
    # shows it, so the payer knows they have the right one)}.
    'mpesa': {'kind': 'till', 'number': '8496746'},
    # A paypal.me name, or a PayPal payment link
    # (https://www.paypal.com/ncp/payment/...).
    'paypal': 'https://www.paypal.com/ncp/payment/PLB-BPX9BPVQNRG8',
}

_config: dict[str, Any] = dict(_DEFAULTS)


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


def configured() -> bool:
    link = str(_config.get('link') or '')
    return bool(_config.get('enabled') and link.startswith('https://'))


def _mpesa() -> dict[str, str]:
    """The M-Pesa way to pay, checked: digits only, a kind M-Pesa has."""

    raw = _config.get('mpesa') or {}
    if not isinstance(raw, dict) or not _config.get('enabled'):
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
    raw = str(_config.get('paypal') or '').strip()
    if not _config.get('enabled') or not raw:
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
        'link': _config.get('link', ''),
        'message': _config.get('message', ''),
        'mpesa': _mpesa(),
        'paypal_link': _paypal_link(),
    }
