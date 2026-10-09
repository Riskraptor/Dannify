"""The Google sign-in window, as on Windows and Linux: a real browser view of
Google's own page, in a window of its own, with storage of its own.

Nothing is pasted by hand and the app never sees a password: once Google
lands on YouTube Music the session cookies are read from this window's
cookie store and handed to account.sign_in. Its storage is apart from the
app's window, so "sign out" can wipe it completely and nothing Google's page
does can reach the main window. From macOS 14 that storage is a persistent
store of its own (WKWebsiteDataStore by identifier); before that it lives in
memory only, for as long as the app runs.
"""

from __future__ import annotations

import shutil
import threading
import time
import uuid
from typing import Optional
from urllib.parse import urlsplit

import WebKit
from loguru import logger

from ..core import LOGIN_STORAGE, LOGIN_URL, SIGNED_IN_HOSTS, THEME_BG
from .cocoa import AppKit, Foundation, hex_color, on_main, os_major

TIMEOUT = 15 * 60
_ID_FILE = LOGIN_STORAGE / 'store-id'
_SITE = 'music.youtube.com'

# Before macOS 14 the store is in memory: kept here so "sign out" can still
# empty it while the app runs.
_memory_store = None
_delegate_class = None


def _persistent() -> bool:
    return os_major() >= 14


def _store_id(create: bool) -> Optional[str]:
    try:
        value = _ID_FILE.read_text(encoding='utf-8').strip()
        uuid.UUID(value)
        return value
    except (OSError, ValueError):
        if not create:
            return None
    value = str(uuid.uuid4()).upper()
    LOGIN_STORAGE.mkdir(parents=True, exist_ok=True)
    _ID_FILE.write_text(value, encoding='utf-8')
    return value


def _store():
    """Main thread. The sign-in window's own website data store."""

    global _memory_store
    if _persistent():
        ident = Foundation.NSUUID.alloc().initWithUUIDString_(_store_id(create=True))
        return WebKit.WKWebsiteDataStore.dataStoreForIdentifier_(ident)
    if _memory_store is None:
        _memory_store = WebKit.WKWebsiteDataStore.nonPersistentDataStore()
    return _memory_store


def _delegate():
    global _delegate_class
    if _delegate_class is None:
        class DannifySignInDelegate(Foundation.NSObject):
            # Google opens some steps in a new window; keep them in this one.
            def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(
                    self, webview, _config, action, _features):  # noqa: ANN001
                request = action.request()
                if request is not None:
                    webview.loadRequest_(request)
                return None

            def webView_didFinishNavigation_(self, _webview, _navigation) -> None:  # noqa: ANN001
                owner = getattr(self, 'owner', None)
                if owner is not None:
                    owner._check()

            def windowWillClose_(self, _notification) -> None:  # noqa: ANN001
                owner = getattr(self, 'owner', None)
                if owner is not None:
                    owner._done.set()

        _delegate_class = DannifySignInDelegate
    return _delegate_class.alloc().init()


def _for_site(domain: str) -> bool:
    """Whether a cookie for *domain* is one music.youtube.com is sent."""

    domain = domain.lstrip('.').lower()
    return bool(domain) and (_SITE == domain or _SITE.endswith('.' + domain))


class LoginWindow:
    def __init__(self, theme: str) -> None:
        self._theme = theme
        self._done = threading.Event()
        self.cookies: dict[str, str] = {}
        self.error = ''
        self._window = None
        self._view = None
        self._delegate = None
        self._store = None
        self._reading = False

    def run(self) -> dict[str, str]:
        """Show the window and block (on a worker thread) until it closes."""

        on_main(self._open)
        deadline = time.monotonic() + TIMEOUT
        # Polled as well as checked after each page: Google moves on by
        # script and history changes too, which finish no navigation.
        while not self._done.wait(0.4) and time.monotonic() < deadline:
            on_main(self._check)
        on_main(self.close, wait=True)
        return self.cookies

    def _open(self) -> None:
        from dannify import account

        try:
            store = _store()
            config = WebKit.WKWebViewConfiguration.alloc().init()
            config.setWebsiteDataStore_(store)
            frame = AppKit.NSMakeRect(0, 0, 520, 720)
            view = WebKit.WKWebView.alloc().initWithFrame_configuration_(frame, config)
            view.setCustomUserAgent_(account.USER_AGENT)
            delegate = _delegate()
            delegate.owner = self
            view.setNavigationDelegate_(delegate)
            view.setUIDelegate_(delegate)

            style = (AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable
                     | AppKit.NSWindowStyleMaskMiniaturizable | AppKit.NSWindowStyleMaskResizable)
            window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                frame, style, AppKit.NSBackingStoreBuffered, False)
            window.setReleasedWhenClosed_(False)
            window.setTitle_('Sign in with Google')
            window.setBackgroundColor_(hex_color(THEME_BG[self._theme]))
            window.setContentView_(view)
            window.setDelegate_(delegate)
            window.center()
            window.makeKeyAndOrderFront_(None)
            AppKit.NSApp().activateIgnoringOtherApps_(True)
            self._window, self._view, self._delegate, self._store = window, view, delegate, store
            view.loadRequest_(Foundation.NSURLRequest.requestWithURL_(
                Foundation.NSURL.URLWithString_(LOGIN_URL)))
        except Exception as exc:
            logger.opt(exception=True).info('the sign-in window could not open')
            self.error = str(exc)
            self._done.set()

    def _check(self) -> None:
        """Signed in yet? Main thread."""

        view = self._view
        if view is None or self._reading or self.cookies:
            return
        url = view.URL()
        host = urlsplit(str(url.absoluteString()) if url is not None else '').hostname or ''
        if host not in SIGNED_IN_HOSTS:
            return
        self._reading = True
        self._store.httpCookieStore().getAllCookies_(self._collect)

    def _collect(self, cookies) -> None:  # noqa: ANN001
        self._reading = False
        found = {}
        try:
            for cookie in cookies or []:
                if _for_site(str(cookie.domain() or '')) and cookie.value():
                    found[str(cookie.name())] = str(cookie.value())
        except Exception:
            logger.opt(exception=True).debug('could not read the sign-in cookies')
            return
        if not (found.get('__Secure-3PAPISID') or found.get('SAPISID')):
            return  # the session is still settling; the next tick tries again
        self.cookies = found
        self.close()

    def close(self) -> None:
        window, view = self._window, self._view
        self._window = self._view = None
        if view is not None:
            view.stopLoading()
            view.setNavigationDelegate_(None)
            view.setUIDelegate_(None)
        if window is not None:
            window.setDelegate_(None)
            window.close()
        if self._delegate is not None:
            self._delegate.owner = None
            self._delegate = None
        self._store = None
        self._done.set()


def _wait(start, with_error: bool = False) -> bool:  # noqa: ANN001
    """Run *start(done)* on the main thread and wait for it to call done.

    WebKit's completion blocks take no argument or an NSError, and PyObjC
    wants the Python side to take exactly as many.
    """

    finished = threading.Event()
    done = (lambda _error: finished.set()) if with_error else (lambda: finished.set())
    on_main(lambda: start(done))
    return finished.wait(10)


def clear_session() -> bool:
    """Forget the Google session so the next sign-in starts clean."""

    ident = _store_id(create=False)
    every = WebKit.WKWebsiteDataStore.allWebsiteDataTypes()
    since = Foundation.NSDate.distantPast()
    if ident and _persistent():
        uid = Foundation.NSUUID.alloc().initWithUUIDString_(ident)
        # Emptied first, which works even while something still holds the
        # store; then the store itself goes.
        _wait(lambda done: WebKit.WKWebsiteDataStore.dataStoreForIdentifier_(uid)
              .removeDataOfTypes_modifiedSince_completionHandler_(every, since, done))
        _wait(lambda done: WebKit.WKWebsiteDataStore
              .removeDataStoreForIdentifier_completionHandler_(uid, done), with_error=True)
    elif _memory_store is not None:
        _wait(lambda done: _memory_store.removeDataOfTypes_modifiedSince_completionHandler_(
            every, since, done))
    try:
        # A new identifier next time: nothing of the old store is reused.
        shutil.rmtree(LOGIN_STORAGE, ignore_errors=True)
        return not LOGIN_STORAGE.exists()
    except Exception:
        logger.opt(exception=True).info('could not clear the sign-in storage')
        return False
