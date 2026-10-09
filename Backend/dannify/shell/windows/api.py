"""The bridge calls the interface makes (frontend/src/desktop/bridge.js)."""

from __future__ import annotations

import json
import os
import threading
import time
from loguru import logger

from .base import _app_icon, _lock_view_settings, _write_prefs, logger_print
from .win32 import MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, _HOTKEYS, _WIN, user32
from .frame import _CustomFrame
from .taskbar import (
    BTN_NEXT,
    BTN_PLAY,
    BTN_PREV,
    _Taskbar,
)
from .tray import _Tray
from .places import _set_autostart


# ---------------------------------------------------------------------------
# JS API: exposed to the page as window.pywebview.api.*
# (Attributes starting with "_" are private and not exposed.)
# ---------------------------------------------------------------------------

from .actions import ActionsMixin
from .window import WindowMixin
class DesktopApi(WindowMixin, ActionsMixin):
    def __init__(self, native_frame_pref: bool, prefs: dict | None = None):
        prefs = prefs or {}
        self._window = None
        self._form = None
        self._hwnd = 0
        self._frame: _CustomFrame | None = None
        self._taskbar: _Taskbar | None = None
        self._tray: _Tray | None = None
        self._native_frame_pref = native_frame_pref
        self._native_frame = native_frame_pref
        self._fullscreen = False
        self._mini = False
        self._pre_mini: dict | None = None
        self._on_top = False
        self._theme = 'dark'
        # On by default: closing the window on a music player is
        # 'get out of my way', not 'stop the music'. Settings can turn
        # it off, and that choice is remembered.
        self._close_to_tray = bool(prefs.get('close_to_tray', True))
        # Minimising minimises. The close button is what sends the app to
        # the tray, and a switch that made minimise do the same thing just
        # meant people turned it on once and then could not work out why
        # their window kept disappearing. The switch is gone; this clears it
        # for anyone who had it on.
        if prefs.get('minimize_to_tray'):
            _write_prefs({'minimize_to_tray': False})
        # The "still running here" notice has been seen before, on any launch.
        self._tray_hint_shown = bool(prefs.get('tray_hint_shown'))
        self._global_hotkeys = bool(prefs.get('global_hotkeys', False))
        # Shortcuts another program already holds: said in Settings.
        self._hotkeys_taken: list[str] = []
        self._hidden = False
        # When the browser engine's renderer last died, so a reload loop
        # cannot get going.
        self._renderer_failures: list[float] = []
        # Set while the user is genuinely quitting, so close-to-tray steps aside.
        self._quitting = False
        self._login = None  # the Google sign-in window, while it is open
        self._launch_geometry: tuple[int, int, int, int] | None = None
        # Once the window starts closing, calling into it (Invoke/evaluate_js)
        # raises from a destroyed handle: stop talking to it.
        self._closing = False

    # --- wiring (called from Python, not JS) -------------------------------
    def _attach(self, window) -> None:  # noqa: ANN001
        """Runs on the UI thread from pywebview's before_show event."""
        self._window = window
        self._form = window.native
        try:
            self._hwnd = int(self._form.Handle.ToInt64())
        except Exception:
            self._hwnd = 0
        try:
            self._form.Icon = _app_icon()
        except Exception:
            pass
        if not (_WIN and self._hwnd):
            return
        self._taskbar = _Taskbar(self._hwnd)
        self._tray = _Tray(self, hint_shown=self._tray_hint_shown)
        if self._close_to_tray:
            self._tray.install()
        self._frame = _CustomFrame(
            self._hwnd,
            on_command=self._on_thumb_button,
            on_taskbar_created=self._on_taskbar_created,
            on_maximize=self.win_toggle_maximize,
            on_max_hover=self._on_max_hover,
            on_hotkey=self._on_hotkey,
        )
        if self._native_frame_pref:
            # Keep the Windows caption; the subclass is still needed for the
            # taskbar buttons, so install it without reclaiming the caption.
            self._frame._nccalcsize = lambda hwnd, msg, w, l: self._frame._comctl.DefSubclassProc(hwnd, msg, w, l)  # noqa: E731
        ok = self._frame.install()
        self._native_frame = self._native_frame_pref or not ok
        if self._global_hotkeys:
            self._register_hotkeys()
        self._guard_renderer()

    def _ui(self, fn, wait: bool = False):  # noqa: ANN001
        """Run *fn* on the window's UI thread."""
        form = self._form
        if form is None or self._closing:
            return None
        from System import Action

        result = []

        def run():
            try:
                result.append(fn())
            except Exception as exc:  # never let an exception cross into .NET
                logger_print('ui call failed:', exc)

        try:
            if not form.InvokeRequired:
                run()
            elif wait:
                form.Invoke(Action(run))
            else:
                form.BeginInvoke(Action(run))
        except Exception as exc:
            logger_print('invoke failed:', exc)
        return result[0] if result else None

    def _push_state(self) -> None:
        if self._window is None or self._closing:
            return
        state = json.dumps(self.win_state())
        threading.Thread(
            target=self._eval,
            args=(f'window.__dannifyWindowState && window.__dannifyWindowState({state})',),
            daemon=True,
        ).start()

    def _eval(self, script: str) -> None:
        if self._closing:
            return
        try:
            self._window.evaluate_js(script)
        except Exception:
            pass

    def _media(self, cmd: str) -> None:
        """Drive playback from a native control (taskbar button, tray menu)."""
        # Never evaluate_js on the UI thread: it waits for the UI thread.
        threading.Thread(
            target=self._eval,
            args=(f"window.__dannifyMedia && window.__dannifyMedia('{cmd}')",),
            daemon=True,
        ).start()

    # --- system-wide shortcuts ------------------------------------------------
    def _register_hotkeys(self) -> None:
        """UI thread (the window's own): RegisterHotKey belongs to it."""

        self._hotkeys_taken = []
        if not (_WIN and self._hwnd):
            return
        for hid, (vk, _cmd, label) in _HOTKEYS.items():
            if not user32.RegisterHotKey(self._hwnd, hid, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, vk):
                self._hotkeys_taken.append(label)
        if self._hotkeys_taken:
            logger.info('Shortcuts already taken by another program: {}', ', '.join(self._hotkeys_taken))

    def _unregister_hotkeys(self) -> None:
        if not (_WIN and self._hwnd):
            return
        for hid in _HOTKEYS:
            user32.UnregisterHotKey(self._hwnd, hid)
        self._hotkeys_taken = []

    def _on_hotkey(self, hotkey_id: int) -> None:
        entry = _HOTKEYS.get(hotkey_id)
        if entry:
            self._media(entry[1])

    def app_set_global_hotkeys(self, on: bool) -> dict:
        self._global_hotkeys = bool(on)
        _write_prefs({'global_hotkeys': self._global_hotkeys})
        if self._form is not None:
            self._ui(self._register_hotkeys if self._global_hotkeys else self._unregister_hotkeys, wait=True)
        self._push_state()
        return self.win_state()

    # --- start with Windows ----------------------------------------------------
    def app_set_autostart(self, on: bool) -> dict:
        _set_autostart(bool(on))
        self._push_state()
        return self.win_state()

    def shell_open_sound_settings(self) -> bool:
        """Windows' own page for which speakers each app plays through.

        The window cannot offer a list of outputs itself: the browser engine
        names them only for a page allowed to use the microphone, and a music
        player has no business asking for that.
        """

        if not _WIN:
            return False
        try:
            os.startfile('ms-settings:apps-volume')  # noqa: S606  (a fixed address)
            return True
        except OSError:
            return False

    def _on_thumb_button(self, button_id: int) -> None:
        cmd = {BTN_PREV: 'prev', BTN_PLAY: 'toggle', BTN_NEXT: 'next'}.get(button_id)
        if cmd:
            self._media(cmd)

    def _on_max_hover(self, on: bool) -> None:
        """Windows owns the mouse over the maximize button; the page does not
        get :hover there, so tell it to light the button itself."""
        flag = 'true' if on else 'false'
        threading.Thread(
            target=self._eval,
            args=(f'window.__dannifyMaxHover && window.__dannifyMaxHover({flag})',),
            daemon=True,
        ).start()

    def _guard_renderer(self) -> None:
        """Never let the browser engine show its own crash page.

        Lose the renderer, whether to Task Manager, a graphics driver reset or
        plain memory pressure, and WebView2 paints "This page is having a
        problem" with a blue Refresh button under it. That is a browser
        telling somebody their tab died, in the middle of what is meant to be
        an application: it is the single most website-like thing the window
        can do. Take the event and put the interface back instead.
        """

        if not _WIN:
            return

        def attach():
            try:
                view = self._form.browser.webview
            except Exception:
                return

            def on_failed(_sender, args):  # noqa: ANN001
                try:
                    kind = str(args.ProcessFailedKind)
                except Exception:
                    kind = '?'
                logger_print('renderer failed:', kind)
                # The browser process itself going is not survivable in place;
                # everything else is a reload.
                if 'Browser' in kind:
                    return
                self._recover_renderer()

            def subscribe(core) -> bool:
                if core is None:
                    return False
                _lock_view_settings(core)
                try:
                    core.ProcessFailed += on_failed
                    return True
                except Exception:
                    return False

            try:
                if subscribe(view.CoreWebView2):
                    return
            except Exception:
                pass

            def on_ready(_sender, _args):  # noqa: ANN001
                try:
                    subscribe(view.CoreWebView2)
                except Exception:
                    pass

            try:
                view.CoreWebView2InitializationCompleted += on_ready
            except Exception:
                pass

        self._ui(attach)

    def _recover_renderer(self) -> None:
        """Reload after a renderer died, without spinning on it."""

        now = time.time()
        recent = [t for t in self._renderer_failures if now - t < 60]
        recent.append(now)
        self._renderer_failures = recent
        if len(recent) > 3:
            # Something is wrong that reloading will not mend. Stop trying
            # rather than flickering at the user for ever.
            logger_print('renderer keeps failing; leaving it alone')
            return

        def go():
            try:
                self._form.browser.webview.CoreWebView2.Reload()
            except Exception as exc:
                logger_print('could not reload after a renderer failure:', exc)

        self._ui(go)

    def _on_taskbar_created(self) -> None:
        if self._taskbar is not None:
            try:
                self._taskbar.reset()
                self._taskbar.add_buttons()
            except Exception as exc:
                logger_print('taskbar buttons unavailable:', exc)
