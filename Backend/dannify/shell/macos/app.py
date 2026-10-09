"""Starting and stopping Dannify on macOS."""

from __future__ import annotations

import os
import secrets
import sys
import threading
import time
from pathlib import Path

from loguru import logger

from .. import core, instance
from . import desktop, updater


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


def _int(value, default: int) -> int:  # noqa: ANN001
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _size(prefs: dict) -> tuple[int, int]:
    """The window's size last time (its place is restored once it exists)."""

    frame = prefs.get('mac_frame')
    if isinstance(frame, list) and len(frame) == 4:
        w, h = frame[2], frame[3]
    else:
        w, h = prefs.get('w'), prefs.get('h')
    return max(core.MIN_W, _int(w, core.DEFAULT_W)), max(core.MIN_H, _int(h, core.DEFAULT_H))


class _Exit:
    """What has to happen exactly once on the way out, whichever way out it is:
    the window closed, Quit from the menu or the Dock, or logging out."""

    def __init__(self, api, owner, server) -> None:  # noqa: ANN001
        self._api, self._owner, self._server = api, owner, server
        self._done = False

    def run(self) -> None:
        if self._done:
            return
        self._done = True
        api = self._api
        try:
            api._save_geometry()
        except Exception:
            pass
        api._shutdown()
        self._owner.release()
        self._server.should_exit = True
        time.sleep(0.3)
        try:
            api._install_staged()
        except Exception:
            logger.opt(exception=True).warning('the waiting update could not be started')
        try:
            logger.complete()
        except Exception:
            pass


def _app_delegate(api, leave: _Exit, open_file):  # noqa: ANN001
    """pywebview's application delegate, taught the rest of what a Mac app
    is asked: reopen from the Dock, the Dock menu, documents, and quitting."""

    from webview.platforms.cocoa import BrowserView

    from .cocoa import AppKit

    class DannifyAppDelegate(BrowserView.AppDelegate):
        def applicationShouldTerminate_(self, _app):  # noqa: ANN001
            # Quit from the menu, the Dock, Cmd+Q or logging out: for real,
            # never into the menu bar.
            api._quitting = True
            leave.run()
            return AppKit.NSTerminateNow

        def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, _visible) -> bool:  # noqa: ANN001
            api.win_show()
            return True

        def applicationDockMenu_(self, _app):  # noqa: ANN001
            return api._tray.dock_menu()

        def application_openFiles_(self, app, names) -> None:  # noqa: ANN001
            for name in names or []:
                open_file(str(name))
            app.replyToOpenOrPrint_(AppKit.NSApplicationDelegateReplySuccess)

    return DannifyAppDelegate.alloc().init()


def main() -> None:
    if '--quit' in sys.argv[1:]:
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

    from .api import MacApi

    port = core.pick_port()
    token = secrets.token_urlsafe(24)
    server = core.start_server(port, token)
    core.write_instance_file(port)
    started = threading.Event()

    def open_file(path: str) -> None:
        if not (path and Path(path).is_file()):
            return
        if started.is_set():
            import main as backend

            threading.Thread(target=backend.open_external, args=(path,), daemon=True).start()
        else:
            threading.Thread(target=core.open_when_connected, args=(path,), daemon=True).start()

    if opening:
        open_file(opening)

    prefs = core.read_prefs()
    app_path = desktop.bundle_path()
    api = MacApi(prefs, port, token, app_path)
    theme = api._theme
    hidden = '--minimized' in sys.argv[1:]
    w, h = _size(prefs)
    window = webview.create_window(
        core.APP_TITLE,
        html=core.splash_html(theme),
        js_api=api,
        width=w, height=h,
        min_size=(core.MIN_W, core.MIN_H),
        background_color=core.THEME_BG[theme],
        # Frameless to pywebview means a full-size page under a transparent
        # title bar; the shell puts macOS's own buttons back on top of it.
        frameless=True,
        easy_drag=False,
        text_select=False,
        zoomable=False,
        hidden=hidden,
    )
    leave = _Exit(api, owner, server)
    delegate = None

    def on_message(message: dict) -> dict:
        command = message.get('cmd')
        if command == 'quit':
            api.app_quit()
        elif command == 'show':
            api.win_show()
            open_file(str(message.get('file') or ''))
        return {'ok': True}

    owner.handler = on_message

    def before_show(*_) -> None:  # main thread
        nonlocal delegate
        from .cocoa import AppKit

        api._attach(window, hidden, prefs.get('mac_frame'))
        delegate = _app_delegate(api, leave, open_file)
        AppKit.NSApp().setDelegate_(delegate)

    def swap_to_app() -> None:
        if core.wait_until_up(port, token, server):
            window.load_url(core.app_url(port, token))
            started.set()
            # Up: an updater waiting on this version can stop waiting, and
            # the version this one replaced is not needed any more.
            updater.started(app_path, core.DATA_DIR)
        else:
            window.load_html(core.failed_html(theme))

    def on_closing():
        if api._close_to_tray and not api._quitting and api._hide_to_tray():
            return False  # hidden, still playing; the Dock icon brings it back
        api._save_geometry()
        api._closing = True
        return True

    window.events.before_show += before_show
    window.events.closing += on_closing

    webview.start(
        swap_to_app,
        gui='cocoa',
        debug=bool(os.environ.get('DANNIFY_DEVTOOLS')),
        private_mode=False,
    )
    leave.run()
    os._exit(0)


def run() -> None:
    """Start the macOS app (desktop.entry dispatches here)."""

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
