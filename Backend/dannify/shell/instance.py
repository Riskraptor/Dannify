"""One running copy per user, on Linux and macOS.

The first copy listens on a Unix socket in its data folder. A second launch
connects instead of starting: it hands over what it was asked to do (show the
window, play a file, quit) and exits. It used to open a browser tab without
the window's session key, which the server rightly refused with a 404.

A socket left behind by a copy that crashed answers nothing; it is replaced.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

from .core import DATA_DIR


def _path() -> Path:
    name = 'instance{}.sock'.format(os.environ.get('DANNIFY_INSTANCE', ''))
    path = DATA_DIR / name
    # sun_path is about a hundred bytes; a long data folder would not fit.
    if len(str(path).encode()) > 100:
        path = Path(os.environ.get('XDG_RUNTIME_DIR') or '/tmp') / f'dannify-{os.getuid()}-{name}'
    return path


def send(message: dict, timeout: float = 3.0) -> Optional[dict]:
    """Hand *message* to the running copy. Its answer, or None if none runs."""

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(_path()))
            s.sendall(json.dumps(message).encode('utf-8') + b'\n')
            reply = s.makefile('rb').readline()
        return json.loads(reply or b'{}')
    except (OSError, ValueError):
        return None


class Instance:
    """The listening end, held by the copy that runs."""

    def __init__(self) -> None:
        self._sock: Optional[socket.socket] = None
        self.handler: Callable[[dict], dict] = lambda message: {'ok': False}

    def claim(self) -> bool:
        """True if this is the only copy; False if another one answered."""

        path = _path()
        if send({'cmd': 'ping'}, timeout=1.0) is not None:
            return False
        try:
            path.unlink(missing_ok=True)  # left by a copy that did not exit cleanly
        except OSError:
            pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.bind(str(path))
            os.chmod(path, 0o600)  # this user only
            s.listen(4)
        except OSError:
            s.close()
            # Two launches at the same instant: whoever bound first runs.
            return send({'cmd': 'ping'}, timeout=1.0) is None
        self._sock = s
        threading.Thread(target=self._serve, name='dannify-instance', daemon=True).start()
        return True

    def _serve(self) -> None:
        while self._sock is not None:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                try:
                    conn.settimeout(3.0)
                    line = conn.makefile('rb').readline()
                    message = json.loads(line or b'{}')
                    reply = {'ok': True} if message.get('cmd') == 'ping' else self.handler(message)
                    conn.sendall(json.dumps(reply or {'ok': True}).encode('utf-8') + b'\n')
                except Exception:
                    logger.opt(exception=True).debug('instance message failed')

    def release(self) -> None:
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
                _path().unlink(missing_ok=True)
            except OSError:
                pass
