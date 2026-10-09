"""Starting and stopping Dannify on Windows."""

from __future__ import annotations

import os
import secrets
import sys
import threading
import time
from loguru import logger

from .base import (
    APP_TITLE,
    _FROZEN,
    _THEME_BG,
    _WEBVIEW_STORAGE,
    _fatal,
    _install_crash_hooks,
    _purge_window_cache,
    _read_prefs,
    _refuse_tampered,
    _webview_untampered,
    _write_prefs,
    logger_print,
    state,
)
from .win32 import (
    SM_SHUTTINGDOWN,
    _WIN,
    user32,
)
from .places import (
    _current_placement,
    _load_window_state,
    _settle,
    _splash_html,
)
from .server import (
    _pick_port,
    _start_server,
    _wait_until_up,
    _write_instance_file,
)
from .identity import (
    _claim_app_identity,
    _schedule_media_identity,
)
from .instance import (
    _acquire_single_instance,
    _file_argument,
    _hand_file_to_running_instance,
    _quit_until_gone,
    _signal_quit_request,
    _watch_for_opened_files,
    _watch_for_quit_request,
)
from .api import DesktopApi


def _apply_staged_update() -> None:
    """Install a downloaded update now that the window is gone.

    Silent on purpose: the user closed the app, so putting a wizard on
    screen would be the opposite of helpful. The installer keeps settings
    and the library, and does not relaunch (its post-install step is
    skipped in silent mode).

    If this fails there is nothing to tell anyone, because nobody is
    looking. The next launch finds the same update still pending and offers
    it again, so a failure costs one more prompt rather than a broken
    install.
    """

    import subprocess

    installer = state.staged_update
    if installer is None or not _WIN:
        return

    try:
        if not installer.is_file():
            return
        logger.info('Applying staged update: {}', installer.name)
        # Launched directly. This used to go through `cmd /c ping ... &` to
        # wait for our own process to exit, which put a console window on
        # screen for a moment with 127.0.0.1 in it: CREATE_NO_WINDOW is
        # documented to be ignored when combined with DETACHED_PROCESS, so
        # the flags never suppressed it. The wait was not needed anyway,
        # because the installer waits for our mutex itself.
        subprocess.Popen(
            [str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            close_fds=True,
        )
    except Exception:
        logger.opt(exception=True).debug('could not apply the staged update')


def _after_start_housekeeping() -> None:
    """Once the app has settled: the launcher, the Apps entry, leftovers.

    An update can bring a new launcher; it is copied into place from here
    because the launcher is not running once the app is. Settings > Apps is
    told the version that actually runs. Folders earlier updates parked are
    cleared, keeping the one version there is to go back to.
    """

    time.sleep(20)
    try:
        from dannify import __version__, layout

        if not layout.managed():
            return
        layout.refresh_registration(__version__)
        layout.refresh_launcher()
        layout.tidy()
    except Exception:
        logger.opt(exception=True).debug('housekeeping failed')


def main() -> None:
    # `--quit` is how the installer asks a running copy to get out of the
    # way before it replaces the files. It is not a user-facing switch.
    if '--quit' in sys.argv[1:]:
        _signal_quit_request()
        sys.exit(0)

    _install_crash_hooks()
    _claim_app_identity()
    opening = _file_argument()
    if not _acquire_single_instance():
        # Already running, and it has just been brought forward. Explorer
        # started us only to open a file, so leave it where the running copy
        # will find it and get out of the way.
        if opening:
            _hand_file_to_running_instance(opening)
        sys.exit(0)

    port = _pick_port()
    session_key = secrets.token_urlsafe(24)
    server = _start_server(port, session_key)
    _write_instance_file(port)
    threading.Thread(
        target=_after_start_housekeeping, name='dannify-housekeeping', daemon=True,
    ).start()

    threading.Thread(
        target=_watch_for_opened_files, name='dannify-open', daemon=True,
    ).start()
    if opening:
        # We are the first copy: the window is not up yet and nothing is
        # listening on the websocket, so wait for it rather than shouting
        # into an empty room.
        def _open_when_ready(path: str = opening) -> None:
            import main as backend

            for _ in range(60):
                time.sleep(0.5)
                if getattr(backend.api.state.connections, 'connected', False):
                    break
            try:
                backend.open_external(path)
            except Exception:
                logger_print('could not open', path)

        threading.Thread(
            target=_open_when_ready, name='dannify-open-first', daemon=True,
        ).start()

    import webview

    prefs = _read_prefs()
    theme = 'light' if prefs.get('theme') == 'light' else 'dark'
    # Dannify draws its own title bar, always. The Windows caption used to be
    # optional, and turning it on left two title bars stacked: the system's
    # with the app name, then ours underneath with the logo and name again,
    # which reads as one app running inside another. The option is gone and
    # any saved copy of it is cleared, so an install that had it on fixes
    # itself on the next launch. A native caption can still appear if the
    # custom frame fails to install, and the interface drops its own brand
    # row in that case so there is never a second bar.
    if prefs.get('native_frame'):
        _write_prefs({'native_frame': False})
    native_frame = False
    x, y, w, h, maximized = _load_window_state(prefs)

    # Keep WebView data (localStorage: language, volume, layout, history)
    # between launches: pywebview defaults to a throw-away private profile.
    _WEBVIEW_STORAGE.mkdir(parents=True, exist_ok=True)

    # Browser flags. This environment variable replaces pywebview's own
    # argument string, so we repeat its overscroll fix. Hardware media keys
    # route through Windows' media controls (keyboard keys, volume flyout).
    browser_args = [
        # Translate/OptimizationHints phone home and cost memory for a UI that
        # ships its own translations; ElasticOverscroll is pywebview's fix for
        # rubber-banding, which a desktop app should not do.
        '--disable-features=ElasticOverscroll,Translate,OptimizationHints,MediaRouter',
        # Register with Windows' media controls: the play/pause/next keyboard
        # keys and the volume flyout drive playback, with artwork and title.
        '--enable-features=HardwareMediaKeyHandling,MediaSessionService,GlobalMediaControls',
        # One page, one renderer. Without this WebView2 keeps spare processes
        # around that cost 40-60 MB each and buy us nothing.
        '--renderer-process-limit=1',
        # A ceiling for the page's memory, not a target: V8 collects long
        # before it. It was 256 MB, and a library of a couple of hundred
        # thousand artists went past that while sorting; the page then died
        # and came back blank. The default is a share of the machine's RAM,
        # which lets a runaway page take far more than a music player should.
        '--js-flags=--max-old-space-size=1024',
        # A music player plays in the background. Chromium slows the timers
        # of a page it thinks nobody is looking at, and the change to the
        # next song (crossfade, gapless) is timed by one: minimized or in the
        # tray, it came late. And sound may start without a click first: it
        # is the user's own app, not a web page.
        '--disable-background-timer-throttling',
        '--disable-renderer-backgrounding',
        '--disable-backgrounding-occluded-windows',
        '--autoplay-policy=no-user-gesture-required',
    ]
    # Remote debugging is a development aid and a back door into the running
    # app, so a shipped build ignores the variable entirely.
    if _FROZEN and not _webview_untampered():
        _refuse_tampered()
        sys.exit(3)
    _purge_window_cache()
    devtools_port = '' if _FROZEN else os.environ.get('DANNIFY_DEVTOOLS_PORT', '').strip()
    if devtools_port.isdigit():
        browser_args.append(f'--remote-debugging-port={devtools_port}')
    os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = ' '.join(browser_args)

    api = DesktopApi(native_frame_pref=native_frame, prefs=prefs)
    state.api = api
    api._theme = theme
    # What we asked for. Windows reports back a slightly different rect once
    # the custom frame is installed, and saving *that* made the window creep
    # a little taller on every launch until the player bar fell off the
    # bottom of the screen. If the user never touched the window, we keep
    # exactly what they last chose.
    api._launch_geometry = (x, y, w, h)

    window = webview.create_window(
        APP_TITLE,
        html=_splash_html(theme, native_frame),  # instant paint: no waiting on the server
        js_api=api,
        x=x,
        y=y,
        width=w,
        height=h,
        min_size=state.min_fit,
        background_color=_THEME_BG[theme],
        text_select=False,
        # Ctrl with the scroll wheel zooming the whole interface is browser
        # behaviour and makes the app feel like a page in a window. Interface
        # size is a setting under Appearance instead.
        zoomable=False,
        maximized=maximized,
        # Started by Windows at sign-in: there, but out of the way.
        minimized='--minimized' in sys.argv[1:],
        shadow=False,  # the native frame already provides the DWM shadow
    )

    # pywebview hands the window only to a parameter literally named "window".
    def _before_show(window) -> None:  # noqa: ANN001  (UI thread, before first paint)
        api._attach(window)
        # Now that there is a real window, record it so a second launch can
        # bring it back even after it has been hidden into the tray.
        try:
            _write_instance_file(port, api._hwnd)
        except Exception:
            pass

    def _swap_to_app() -> None:
        # Give the media flyout something to call us other than "Unknown app".
        _schedule_media_identity()
        if _wait_until_up(port, token=session_key, server=server):
            # Edge WebView2 sometimes deadlocks on load_url() called from a
            # background thread; navigating via JS sidesteps it. The query
            # flag tells the frontend it runs inside the desktop shell.
            target = f'http://127.0.0.1:{port}/?shell=desktop&k={session_key}'
            try:
                window.evaluate_js(f"window.location.replace('{target}')")
            except Exception:
                window.load_url(target)
        else:
            window.load_html(
                _splash_html(
                    theme,
                    api._native_frame,
                    # Nothing about files or folders here. Someone looking at
                    # this screen wants to know what to do, not where we keep
                    # our notes.
                    '<h2>Dannify could not start</h2>'
                    '<p>Close it from the notification area if a copy is '
                    'still running, then open it again.</p>',
                )
            )

    def _on_state_change() -> None:
        api._push_state()

    def _on_minimized() -> None:
        api._push_state()

    def _on_closing():
        # Runs on the UI thread before the window goes away. Returning False
        # cancels the close, which is how "keep playing in the tray" works.
        #
        # Except when Windows itself is going down: an app that answers a
        # shutdown by hiding is an app that blocks the shutdown.
        shutting_down = False
        try:
            shutting_down = bool(user32.GetSystemMetrics(SM_SHUTTINGDOWN))
        except Exception:
            pass
        if (
            api._close_to_tray
            and not api._quitting
            and not shutting_down
            and api._hide_to_tray()
        ):
            return False
        # Really going, so take the tray icon down now, here on the UI thread.
        # It used to be left to the closed event, which pywebview runs on a
        # thread of its own while this process is already on its way to
        # os._exit a moment later; lose that race and the icon stays in the
        # notification area, dead, until someone moves the mouse over it.
        # Not while Windows is shutting down: this runs on its "may I?", which
        # another program can still refuse, and the shell is taking every
        # icon down with it anyway.
        if api._tray is not None and not shutting_down:
            try:
                api._tray.dispose()
            except Exception:
                pass
        # Remember the restored geometry (and whether it was maximized).
        api._closing = True
        try:
            hwnd = api._hwnd
            if hwnd and not api._fullscreen:
                placement = api._pre_mini if api._mini and api._pre_mini else _current_placement(hwnd)
                placement = _settle(placement, api._launch_geometry)
                if placement['w'] >= state.min_fit[0] and placement['h'] >= state.min_fit[1]:
                    _write_prefs(placement)
        except Exception:
            pass

    def _on_closed() -> None:
        for part in (api._taskbar, api._tray):
            try:
                if part is not None:
                    part.dispose()
            except Exception:
                pass
        try:
            server.should_exit = True
        except Exception:
            pass

    window.events.before_show += _before_show
    window.events.maximized += _on_state_change
    window.events.restored += _on_state_change
    window.events.minimized += _on_minimized
    window.events.closing += _on_closing
    window.events.closed += _on_closed

    # Let the installer (or anything else) ask us to close properly rather
    # than hide into the tray.
    _watch_for_quit_request(lambda: _quit_until_gone(api))

    # gui='edgechromium' = Edge WebView2 (ships with Windows 10/11).
    webview.start(
        _swap_to_app,
        gui='edgechromium',
        debug=False,
        private_mode=False,
        storage_path=str(_WEBVIEW_STORAGE),
    )

    # Window closed → give uvicorn a moment to drain, then exit.
    time.sleep(0.3)
    _apply_staged_update()

    # Straight out, without running interpreter shutdown. Shutdown joins every
    # live thread pool worker, and a download still running holds one for as
    # long as it takes: yt-dlp alone waits thirty seconds on a socket. The
    # update helper is already waiting on this process, and a parent that
    # takes minutes to die is a parent the helper gives up on.
    try:
        logger.complete()  # the log is written from a queue; let it drain
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.flush()
        except Exception:
            pass
    os._exit(0)


def run() -> None:
    """Start the Windows app (desktop.entry dispatches here)."""

    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        _fatal()
        # Not zero. The update helper relaunches the app and reads the exit
        # code to tell a working launch from a broken one, and zero is the
        # single-instance path: "something is already running, all is well".
        # A crash reporting itself as success made the helper stop retrying
        # and declare the update finished, with nothing on screen.
        sys.exit(3)
