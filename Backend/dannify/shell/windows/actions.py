"""Everything else the interface asks of the shell: the tray, updates, the
Google sign-in, the theme, Explorer, the clipboard, the taskbar button."""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Optional
from loguru import logger

from .base import (
    APP_TITLE,
    _BACKEND,
    _DATA_DIR,
    _FROZEN,
    _LOGIN_STORAGE,
    _THEME_BG,
    _read_prefs,
    _reveal_in_explorer,
    _write_prefs,
    logger_print,
    state,
)
from .win32 import DWMWA_USE_IMMERSIVE_DARK_MODE, _WIN, dwmapi, kernel32, user32
from .login import _LoginWindow
from .places import _library_path


# ---------------------------------------------------------------------------
# JS API: exposed to the page as window.pywebview.api.*
# (Attributes starting with "_" are private and not exposed.)
# ---------------------------------------------------------------------------


class ActionsMixin:
    """DesktopApi's shell calls (see api.py)."""

    # --- tray ---------------------------------------------------------------
    def tray_set(self, options: dict) -> dict:
        """Enable or disable close-to-tray."""
        if not isinstance(options, dict):
            return self.win_state()
        if 'closeToTray' in options:
            self._close_to_tray = bool(options['closeToTray'])
            _write_prefs({'close_to_tray': self._close_to_tray})
        if self._tray is not None:
            wanted = self._close_to_tray
            if wanted and not self._tray.available:
                self._ui(self._tray.install, wait=True)
            elif not wanted and self._tray.available and not self._hidden:
                self._ui(self._tray.dispose, wait=True)
        self._push_state()
        return self.win_state()

    def tray_labels(self, labels: dict) -> None:
        """Localized strings for the tray menu (pushed by the frontend)."""
        if self._tray is not None and isinstance(labels, dict):
            self._ui(lambda: self._tray.apply_labels(labels))

    def app_restart(self) -> bool:
        """Relaunch Dannify (used by "restart to update").

        An installed copy hands this to its launcher: it waits for this
        process to finish, puts a waiting update in place, and opens the new
        version, showing a small window of its own in between.
        """
        from dannify import layout

        launcher = layout.launcher()
        if launcher is not None and _WIN:
            try:
                import subprocess

                subprocess.Popen(
                    [str(launcher), '--after', str(os.getpid())],
                    cwd=str(launcher.parent),
                    close_fds=True,
                )
            except Exception as exc:
                logger_print('restart failed:', exc)
                return False
            threading.Timer(0.25, self._quit).start()
            return True
        try:
            import subprocess

            env = dict(os.environ)
            env['DANNIFY_WAIT_PID'] = str(os.getpid())
            if _FROZEN:
                cmd = [sys.executable, *sys.argv[1:]]
            else:
                cmd = [sys.executable, str(_BACKEND / 'desktop.py'), *sys.argv[1:]]
            subprocess.Popen(cmd, env=env, close_fds=True, cwd=os.getcwd())
        except Exception as exc:
            logger_print('restart failed:', exc)
            return False
        threading.Timer(0.25, self._quit).start()
        return True

    @staticmethod
    def _vetted_installer(installer: str) -> Optional[Path]:
        """The path, but only if it is an installer we put there ourselves.

        Nothing outside our own updates folder is ever run, whatever the UI
        asks for: this is a path arriving from JavaScript.
        """

        try:
            path = Path(str(installer or '')).resolve()
            path.relative_to((_DATA_DIR / 'updates').resolve())
            if path.suffix.lower() != '.exe' or not path.is_file():
                return None
            return path
        except Exception:
            return None

    def app_install_update(self, installer: str) -> bool:
        """Run a downloaded installer and step out of its way."""
        path = self._vetted_installer(installer)
        if path is None:
            return False
        # Running it now is instead of running it on the way out, not as
        # well: two copies of setup at once is what 3.18 did here.
        state.staged_update = None
        try:
            os.startfile(str(path))  # noqa: S606
        except Exception as exc:
            logger_print('could not launch installer:', exc)
            return False
        threading.Timer(0.4, self._quit).start()
        return True

    def app_stage_update(self, installer: str) -> bool:
        """Hold an installer to apply when the app next closes.

        The point of this is that nobody has to decide anything. An update
        downloads quietly, the user is told it is ready, and if they never
        press restart it goes in the next time they close the window: the
        way a browser does it.
        """

        path = self._vetted_installer(installer)
        if path is None:
            return False
        state.staged_update = path
        logger.info('Update staged for the next exit: {}', path.name)
        return True

    def app_clear_staged_update(self) -> bool:
        state.staged_update = None
        return True

    # --- YouTube Music account ----------------------------------------------
    def account_sign_in(self) -> dict:
        """Show the Google sign-in window and keep the resulting session.

        Runs on the JS-bridge worker thread, so blocking here is fine: the
        window has its own UI thread (see _LoginWindow) and the app stays
        responsive throughout.
        """
        if not _WIN:
            return {'signed_in': False, 'error': 'Sign-in needs the desktop app'}
        if self._login is not None:
            return {'signed_in': False, 'error': ''}

        from dannify import account

        login = _LoginWindow(self._theme)
        self._login = login
        try:
            cookies = login.run()
        finally:
            self._login = None
        if not cookies:
            # No cookies means the user closed the window, or WebView2 failed.
            return {'signed_in': False, 'error': login.error}
        try:
            return account.sign_in(cookies)
        except Exception as exc:
            logger_print('sign-in rejected:', exc)
            return {'signed_in': False, 'error': str(exc)}

    def account_clear_session(self) -> bool:
        """Forget the Google session so the next sign-in starts clean."""
        import shutil

        try:
            shutil.rmtree(_LOGIN_STORAGE, ignore_errors=True)
            return True
        except Exception as exc:
            logger_print('could not clear the sign-in profile:', exc)
            return False

    # --- app / shell --------------------------------------------------------
    def app_set_theme(self, theme: str) -> None:
        theme = 'light' if theme == 'light' else 'dark'
        if theme == self._theme and _read_prefs().get('theme') == theme:
            return
        self._theme = theme
        _write_prefs({'theme': theme})
        hwnd = self._hwnd
        bg = _THEME_BG[theme]

        def apply():
            from System.Drawing import ColorTranslator

            color = ColorTranslator.FromHtml(bg)
            self._form.BackColor = color
            try:
                self._form.browser.webview.DefaultBackgroundColor = color
            except Exception:
                pass
            if hwnd:
                value = ctypes.c_int(1 if theme == 'dark' else 0)
                dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
                )

        self._ui(apply)

    def shell_reveal(self, rel_path: str) -> bool:
        """Open Explorer with the file selected (paths confined to the library)."""
        target = _library_path(rel_path)
        if target is None or not target.exists():
            return False
        return _reveal_in_explorer(target)

    def shell_open_library(self) -> bool:
        base = _library_path('')
        if base is None:
            return False
        try:
            os.startfile(str(base))  # noqa: S606
            return True
        except Exception:
            return False

    def shell_open_external(self, url: str) -> bool:
        url = str(url or '')
        if not url.startswith(('https://', 'http://')):
            return False
        return bool(webbrowser.open(url))

    def clipboard_read(self) -> str:
        if not _WIN or not user32.OpenClipboard(None):
            return ''
        try:
            handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
            if not handle:
                return ''
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ''
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    # --- taskbar ------------------------------------------------------------
    def taskbar_progress(self, value: float, mode: str = 'normal') -> None:
        if self._taskbar is None:
            return
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        self._ui(lambda: self._taskbar.set_progress(value, str(mode)))

    def taskbar_playback(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        playing = bool(payload.get('playing'))
        has_track = bool(payload.get('hasTrack'))
        title = str(payload.get('title') or '')[:120]
        artist = str(payload.get('artist') or '')[:120]
        labels = payload.get('labels')

        def apply():
            tb = self._taskbar
            if tb is not None:
                if isinstance(labels, dict):
                    tb.labels.update({k: str(v)[:60] for k, v in labels.items() if k in tb.labels})
                tb.playing = playing
                tb.has_track = has_track
                tb.update_buttons()
            if self._tray is not None:
                self._tray.set_track(title, artist, playing, has_track)
            # The window is called Dannify, full stop. Putting the track in
            # the title made the caption, the taskbar and alt-tab all read
            # like a browser tab retitling itself. What is playing belongs in
            # the player bar and the tray tooltip, which both already show it.
            if self._form is not None and self._form.Text != APP_TITLE:
                self._form.Text = APP_TITLE

        self._ui(apply)
