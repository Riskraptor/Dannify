"""The Google sign-in window, as on Windows: a real browser view of
Google's own page, in a window of its own, with storage of its own.

Nothing is pasted by hand and the app never sees a password: once Google
lands on YouTube Music the session cookies are read from this window's
cookie jar and handed to account.sign_in. Its storage is apart from the
app's window (LOGIN_STORAGE), so "sign out" can wipe it completely and
nothing Google's page does can reach the main window.
"""

from __future__ import annotations

import shutil
import threading
from typing import Optional
from urllib.parse import urlsplit

from loguru import logger

from ..core import LOGIN_STORAGE, LOGIN_URL, ORIGIN, SIGNED_IN_HOSTS, THEME_BG
from .gtk import Gdk, GLib, Gtk, WebKit2, on_ui

TIMEOUT = 15 * 60

# The sign-in window's storage, while this run has one open: clearing the
# folder alone is not enough, WebKit writes what it holds in memory back.
_manager = None


class LoginWindow:
    def __init__(self, theme: str, icon: Optional[str] = None) -> None:
        self._theme = theme
        self._icon = icon
        self._done = threading.Event()
        self.cookies: dict[str, str] = {}
        self.error = ''
        self._window = None
        self._view = None
        self._reading = False
        self._timer = 0

    def run(self) -> dict[str, str]:
        """Show the window and block (on a worker thread) until it closes."""

        on_ui(self._open)
        self._done.wait(TIMEOUT)
        on_ui(self.close)
        return self.cookies

    def _open(self) -> None:
        from dannify import account

        try:
            LOGIN_STORAGE.mkdir(parents=True, exist_ok=True)
            manager = WebKit2.WebsiteDataManager(
                base_data_directory=str(LOGIN_STORAGE / 'data'),
                base_cache_directory=str(LOGIN_STORAGE / 'cache'),
            )
            global _manager
            _manager = manager
            context = WebKit2.WebContext.new_with_website_data_manager(manager)
            context.get_cookie_manager().set_persistent_storage(
                str(LOGIN_STORAGE / 'cookies.sqlite'), WebKit2.CookiePersistentStorage.SQLITE,
            )
            view = WebKit2.WebView.new_with_context(context)
            settings = view.get_settings()
            settings.set_user_agent(account.USER_AGENT)
            settings.set_enable_developer_extras(False)
            color = Gdk.RGBA()
            color.parse(THEME_BG[self._theme])
            view.set_background_color(color)
            # Google opens some steps in a new window; keep them in this one.
            view.connect('create', self._keep_in_window)
            view.connect('load-changed', lambda *_: self._check())

            window = Gtk.Window(title='Sign in with Google')
            window.set_default_size(520, 720)
            window.set_position(Gtk.WindowPosition.CENTER)
            if self._icon:
                try:
                    window.set_icon_from_file(self._icon)
                except Exception:
                    pass
            window.add(view)
            window.connect('destroy', lambda *_: self._done.set())
            window.show_all()
            self._window, self._view = window, view
            self._timer = GLib.timeout_add(400, self._tick)
            view.load_uri(LOGIN_URL)
        except Exception as exc:
            logger.opt(exception=True).info('the sign-in window could not open')
            self.error = str(exc)
            self._done.set()

    def _keep_in_window(self, view, action):  # noqa: ANN001
        try:
            uri = action.get_request().get_uri()
            if uri:
                view.load_uri(uri)
        except Exception:
            pass
        return None

    def _tick(self) -> bool:
        self._check()
        return self._window is not None and not self.cookies

    def _check(self) -> None:
        """Signed in yet? GTK thread."""

        view = self._view
        if view is None or self._reading or self.cookies:
            return
        host = urlsplit(view.get_uri() or '').hostname or ''
        if host not in SIGNED_IN_HOSTS:
            return
        self._reading = True
        jar = view.get_context().get_cookie_manager()
        jar.get_cookies(ORIGIN, None, self._collect, None)

    def _collect(self, jar, result, _data) -> None:  # noqa: ANN001
        self._reading = False
        try:
            found = {c.get_name(): c.get_value() for c in jar.get_cookies_finish(result) or []}
        except Exception:
            logger.opt(exception=True).debug('could not read the sign-in cookies')
            return
        found = {k: v for k, v in found.items() if v}
        if not (found.get('__Secure-3PAPISID') or found.get('SAPISID')):
            return  # the session is still settling; the next tick tries again
        self.cookies = found
        self.close()

    def close(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        window, self._window, self._view = self._window, None, None
        if window is not None:
            window.destroy()
        self._done.set()


def clear_session() -> bool:
    """Forget the Google session so the next sign-in starts clean."""

    if _manager is not None:
        done = threading.Event()

        def wipe() -> None:
            _manager.clear(WebKit2.WebsiteDataTypes.ALL, 0, None, lambda *_: done.set())

        on_ui(wipe)
        done.wait(10)
    try:
        shutil.rmtree(LOGIN_STORAGE, ignore_errors=True)
        return not LOGIN_STORAGE.exists()
    except Exception:
        logger.opt(exception=True).info('could not clear the sign-in storage')
        return False
