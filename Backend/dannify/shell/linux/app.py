"""Starting and stopping Dannify on Linux."""

from __future__ import annotations

import os
import secrets
import sys
import threading
import time
from pathlib import Path

from loguru import logger

from .. import core, instance


def _icon() -> Path:
    here = Path(__file__).resolve().parents[3]  # the folder main.py is in
    for candidate in (here / 'assets' / 'android-chrome-512x512.png',
                      Path('/usr/share/icons/hicolor/512x512/apps/dannify.png')):
        if candidate.is_file():
            return candidate
    return here / 'assets' / 'android-chrome-512x512.png'


def _wait_for_previous() -> None:
    """A restart starts the new copy before the old one has gone: wait for it,
    or the new one would find it still running and hand itself over to it."""

    raw = os.environ.pop('DANNIFY_WAIT_PID', '')
    if not raw.isdigit():
        return
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            os.kill(int(raw), 0)
        except OSError:
            return
        time.sleep(0.1)


def _geometry(prefs: dict) -> tuple:
    def number(key: str, default: int) -> int:
        try:
            return int(prefs.get(key, default))
        except (TypeError, ValueError):
            return default

    w = max(core.MIN_W, number('w', core.DEFAULT_W))
    h = max(core.MIN_H, number('h', core.DEFAULT_H))
    x = prefs.get('x') if isinstance(prefs.get('x'), int) else None
    y = prefs.get('y') if isinstance(prefs.get('y'), int) else None
    return x, y, w, h, bool(prefs.get('maximized'))


def main() -> None:
    if '--quit' in sys.argv[1:]:
        # The package's maintainer scripts ask a running copy to go this way.
        instance.send({'cmd': 'quit'})
        sys.exit(0)
    _wait_for_previous()
    opening = core.file_argument()
    owner = instance.Instance()
    if not owner.claim():
        # Already running: bring that window forward (and play the file),
        # instead of a second server, or a browser tab with no session key.
        instance.send({'cmd': 'show', 'file': opening})
        sys.exit(0)

    import webview

    from .api import LinuxApi

    port = core.pick_port()
    token = secrets.token_urlsafe(24)
    server = core.start_server(port, token)
    core.write_instance_file(port)
    if opening:
        threading.Thread(target=core.open_when_connected, args=(opening,), daemon=True).start()

    prefs = core.read_prefs()
    api = LinuxApi(prefs, _icon(), port, token)
    theme = api._theme
    x, y, w, h, maximized = _geometry(prefs)
    window = webview.create_window(
        core.APP_TITLE,
        html=core.splash_html(theme),
        js_api=api,
        x=x, y=y, width=w, height=h,
        min_size=(core.MIN_W, core.MIN_H),
        background_color=core.THEME_BG[theme],
        frameless=not api._native_frame,
        easy_drag=False,
        text_select=False,
        zoomable=False,
        maximized=maximized,
        minimized='--minimized' in sys.argv[1:],
    )

    def on_message(message: dict) -> dict:
        command = message.get('cmd')
        if command == 'quit':
            api.app_quit()
        elif command == 'show':
            api.win_show()
            path = str(message.get('file') or '')
            if path and Path(path).is_file():
                import main as backend

                threading.Thread(target=backend.open_external, args=(path,), daemon=True).start()
        return {'ok': True}

    owner.handler = on_message

    def before_show(*_) -> None:  # GTK thread; GTK passes no window here
        api._attach(window)

    def swap_to_app() -> None:
        if core.wait_until_up(port, token, server):
            window.load_url(core.app_url(port, token))
        else:
            window.load_html(core.failed_html(theme))

    def on_closing():
        if api._close_to_tray and not api._quitting and api._hide_to_tray():
            return False  # hidden in the tray, still playing
        api._closing = True
        try:
            if not (api._mini or api._fullscreen or api._hidden):
                gx, gy = api._gtk.get_position()
                gw, gh = api._gtk.get_size()
                patch = {'maximized': api._maximized}
                if not api._maximized:
                    patch.update({'x': gx, 'y': gy, 'w': gw, 'h': gh})
                core.write_prefs(patch)
        except Exception:
            pass
        return True

    def on_closed() -> None:
        for stop in (api._tray.dispose, api._mpris.stop, api._hotkeys.unregister):
            try:
                stop()
            except Exception:
                pass
        server.should_exit = True

    window.events.before_show += before_show
    window.events.maximized += lambda: api._push_state()
    window.events.restored += lambda: api._push_state()
    window.events.minimized += lambda: api._push_state()
    window.events.closing += on_closing
    window.events.closed += on_closed

    storage = core.DATA_DIR / 'WebKit'
    storage.mkdir(parents=True, exist_ok=True)
    webview.start(
        swap_to_app,
        gui='gtk',
        debug=bool(os.environ.get('DANNIFY_DEVTOOLS')),
        private_mode=False,
        storage_path=str(storage),
    )
    owner.release()
    time.sleep(0.3)
    api._install_staged()
    try:
        logger.complete()
    except Exception:
        pass
    os._exit(0)


def run() -> None:
    """Start the Linux app (desktop.entry dispatches here)."""

    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        logger.opt(exception=True).critical('Dannify could not start')
        try:
            logger.complete()
        except Exception:
            pass
        sys.exit(3)
