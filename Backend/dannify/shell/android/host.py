"""Starting the backend inside the Android app, and what the app asks of it.

The app (android/app/.../Backend.kt) calls ``start`` once, on a thread of its
own, with the folders Android gave it. Everything else the backend reads at
import time (where its data is, where the music goes) comes from the
environment, so it is set here first, before anything of the backend's is
imported.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from typing import Any

_lock = threading.Lock()
_started: dict[str, Any] = {}


def _environment(config: dict[str, Any]) -> None:
    """The folders and the locale the app passes, as the backend reads them."""

    plain = {
        # Settings, keys, caches: the app's private storage.
        'DANNIFY_DATA_DIR': config.get('data_dir'),
        # Saved music: the app's own folder on the phone's storage.
        'DOWNLOAD_DIR': config.get('music_dir'),
        # The packed interface, unpacked by the app on each new version.
        'DANNIFY_BUNDLE_DIR': config.get('bundle_dir'),
        # Where Android put the programs the app carries (lib<name>.so).
        'DANNIFY_NATIVE_DIR': config.get('native_dir'),
        # Python's own temporary files: Android has no /tmp.
        'TMPDIR': config.get('cache_dir'),
        # Special days and the week's first day follow where the phone is.
        'TZ': config.get('time_zone'),
        'LANG': config.get('locale'),
    }
    for key, value in plain.items():
        if value:
            os.environ[key] = str(value)
    for key in ('data_dir', 'music_dir', 'cache_dir'):
        if config.get(key):
            os.makedirs(str(config[key]), exist_ok=True)


def start(config_json: str) -> str:
    """Start the backend once; return where the interface is, as JSON:
    ``{ok, port, token, url}``. A second call returns the first answer."""

    with _lock:
        if _started:
            return json.dumps(_started)
        config = json.loads(config_json or '{}')
        _environment(config)

        # Only now: these read the folders above as they are imported.
        from loguru import logger  # noqa: PLC0415

        from .. import core  # noqa: PLC0415

        port = core.pick_port()
        token = secrets.token_urlsafe(32)
        server = core.start_server(port, token)
        ok = core.wait_until_up(port, token, server, timeout=90)
        if not ok:
            logger.error('the backend did not come up on the phone')
        _started.update({
            'ok': ok,
            'port': port,
            'token': token,
            'url': f'http://127.0.0.1:{port}/?shell=android&k={token}',
        })
        return json.dumps(_started)


def sign_in(cookies_json: str) -> str:
    """The cookies the app's sign-in screen read from Google's page, kept as
    the desktop keeps them (account.sign_in). JSON in, JSON out."""

    from loguru import logger  # noqa: PLC0415

    from ... import account  # noqa: PLC0415

    try:
        cookies = json.loads(cookies_json or '{}')
        result = account.sign_in(cookies if isinstance(cookies, dict) else {})
    except Exception as exc:  # noqa: BLE001
        logger.opt(exception=True).info('sign-in rejected')
        result = {'signed_in': False, 'error': str(exc)}
    return json.dumps(result, default=str)
