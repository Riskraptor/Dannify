"""The local server the window talks to: its port, start-up and readiness."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.request
from loguru import logger

from .base import (
    BIND_HOST,
    PREFERRED_PORT,
    _DATA_DIR,
    _INSTANCE_FILE,
)


# ---------------------------------------------------------------------------
# Collision-proof port selection
# ---------------------------------------------------------------------------
def _port_is_free(port: int, host: str = BIND_HOST) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            s.bind((host, port))
        return True
    except OSError:
        return False


_PORT_FILE = _DATA_DIR / 'port.json'


def _pick_port() -> int:
    """The same port this installation used last time, if it is still free.

    It used to take whatever the kernel handed out, which meant a different
    port on every launch. The page is served from that port, so the browser
    engine saw a different origin each time and handed the app an empty
    localStorage: volume, language, zoom, the home cache, the playing
    position, half-written lyrics, all gone every single start. Everything
    the app thought it remembered between launches, it did not.

    Still not a fixed number, and still not a well-known one. It is chosen
    once per installation and kept, so the origin stops moving.
    """

    if PREFERRED_PORT and _port_is_free(PREFERRED_PORT):
        return PREFERRED_PORT

    try:
        saved = int(json.loads(_PORT_FILE.read_text(encoding='utf-8'))['port'])
        if 1024 < saved < 65536 and _port_is_free(saved):
            return saved
    except Exception:
        pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((BIND_HOST, 0))  # the OS hands us a port nobody owns
        port = int(s.getsockname()[1])
    try:
        _PORT_FILE.write_text(json.dumps({'port': port}), encoding='utf-8')
    except OSError:
        pass  # a moving port is a nuisance, not a reason to fail to start
    return port


# ---------------------------------------------------------------------------
# Server thread
# ---------------------------------------------------------------------------
def _start_server(port: int, token: str):
    """Boot uvicorn on a daemon thread; return the Server for shutdown."""
    import asyncio

    import main as backend
    from uvicorn import Config, Server

    # DANNIFY_LOG_LEVEL=debug turns on the detail needed to diagnose a
    # packaged build, where there is no console and no devtools.
    backend._setup_logging(os.environ.get('DANNIFY_LOG_LEVEL', 'info'))
    # Only this window knows the key, so nothing else on the machine can
    # reach the API (see the _require_key middleware in main.py).
    backend.api.state.auth_token = token
    backend._fix_mime_types()
    app = backend.build_app()

    config = Config(
        app=app,
        host=BIND_HOST,  # loopback unless DANNIFY_LAN=1 opts into sharing
        port=port,
        log_level='info',
        log_config=None,
        workers=1,
        # Nothing on this socket should introduce itself. A `server:` header
        # naming the web stack is the clearest possible sign that a desktop
        # app is a web app wearing a window.
        server_header=False,
        date_header=False,
    )
    server = Server(config)

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        _benign = (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)

        def _quiet(loop, context):  # noqa: ANN001
            exc = context.get('exception')
            msg = context.get('message', '')
            if isinstance(exc, _benign) or '_call_connection_lost' in msg:
                return

        loop.set_exception_handler(_quiet)
        try:
            loop.run_until_complete(server.serve())
        except BaseException:
            # uvicorn says it could not start (a port taken, a bind refused)
            # by raising SystemExit. It used to vanish with this thread, and
            # the window waited out its whole half minute before saying
            # anything at all.
            logger.opt(exception=True).error('The server stopped or could not start')
        finally:
            server.dannify_stopped = True
            try:
                loop.close()
            except Exception:
                pass

    server.dannify_stopped = False
    thread = threading.Thread(target=_run, name='dannify-server', daemon=True)
    thread.start()
    return server


def _wait_until_up(port: int, timeout: float = 30.0, token: str = '', server=None) -> bool:
    """Poll until the API answers us.

    Carries the session key like any other request. It used to hit an
    endpoint left open to everyone, which meant a browser pointed at the
    port got a version number back and knew exactly what it had found.
    Nothing is open now, so the probe has to identify itself too.
    """
    url = f'http://127.0.0.1:{port}/api/version'
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # A server that has stopped is not going to answer: say so now.
        if server is not None and getattr(server, 'dannify_stopped', False):
            return False
        try:
            request = urllib.request.Request(url)
            if token:
                request.add_header('X-Dannify-Key', token)
            with urllib.request.urlopen(request, timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.05)
    return False


def _write_instance_file(port: int, hwnd: int = 0) -> None:
    """Leave a note for a second launch: how to reach us, and which window
    to bring forward.

    The handle matters. Finding the window by title does not work (the title
    is whatever is playing) and finding it by enumerating visible windows
    does not work either, because a window hidden in the tray is not
    visible. Writing the handle down removes the guessing.
    """

    try:
        payload = {'port': port, 'pid': os.getpid()}
        if hwnd:
            payload['hwnd'] = int(hwnd)
        _INSTANCE_FILE.write_text(json.dumps(payload), encoding='utf-8')
    except Exception:
        pass
