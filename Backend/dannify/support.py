"""The "buy me a coffee" link, and nothing more.

One URL, opened in the user's browser. No keys, no checkout page, no card
details anywhere near the app. Set it in one of these, last one wins:

* ``config/support.json`` next to the exe, shipped with the build;
* ``support.json`` in the data folder, per user;
* ``DANNIFY_SUPPORT_LINK`` / ``DANNIFY_SUPPORT_DISABLED`` in the environment.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from loguru import logger

_DEFAULTS: dict[str, Any] = {
    'enabled': True,
    'link': 'https://ko-fi.com/dkavangi',
    'message': '',
}

_config: dict[str, Any] = dict(_DEFAULTS)


def config_paths(data_dir: Path, name: str) -> list[Path]:
    """Where a drop-in config file may live, lowest precedence first.

    ``<install dir>/config/<name>`` lets whoever packages the build ship
    settings for every user; ``<data dir>/<name>`` is the per-user override.
    """

    import sys

    paths: list[Path] = []
    if getattr(sys, 'frozen', False):
        paths.append(Path(sys.executable).parent / 'config' / name)
    else:
        paths.append(Path(__file__).resolve().parents[2] / 'packaging' / 'config' / name)
    paths.append(Path(data_dir) / name)
    return paths


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


def config() -> dict[str, Any]:
    return {
        'enabled': bool(_config.get('enabled')),
        'configured': configured(),
        'link': _config.get('link', ''),
        'message': _config.get('message', ''),
    }
