"""The Google sign-in window, on a thread and message loop of its own."""

from __future__ import annotations

import threading

from .base import (
    ORIGIN,
    _LOGIN_STORAGE,
    _LOGIN_URL,
    _SIGNED_IN_HOSTS,
    _THEME_BG,
    _app_icon,
    logger_print,
)


class _LoginWindow:
    """The Google sign-in window, running its own WinForms message loop.

    pywebview builds extra windows with a blocking Invoke onto the main
    window's UI thread, and every cookie read afterwards steals that thread
    again. While it is busy the app stops pumping messages and Windows 11
    greys it out as "Not responding". So this does not use pywebview at all:
    it owns a WebView2 on a private STA thread, which means the app keeps
    painting and playing for the whole sign-in, and nothing Google's page
    does can reach the main window.
    """

    TIMEOUT = 15 * 60

    def __init__(self, theme: str):
        self._theme = theme
        self._done = threading.Event()
        self.cookies: dict[str, str] = {}
        self.error = ''
        self._form = None
        self._watcher = None
        self._reading = False

    def run(self) -> dict[str, str]:
        """Show the window and block (on a worker thread) until it closes."""
        try:
            from System.Threading import ApartmentState
            from System.Threading import Thread as ClrThread
            from System.Threading import ThreadStart

            # WinForms only works on a single-threaded-apartment thread, and
            # a plain Python thread is MTA on Windows. This is the same dance
            # pywebview does for its own window.
            thread = ClrThread(ThreadStart(self._pump))
            thread.SetApartmentState(ApartmentState.STA)
            thread.IsBackground = True
            thread.Start()
        except Exception as exc:
            logger_print('could not start the login thread:', exc)
            self.error = str(exc)
            return {}
        self._done.wait(self.TIMEOUT)
        self.close()
        return self.cookies

    def _stop_watcher(self) -> None:
        watcher, self._watcher = self._watcher, None
        if watcher is None:
            return
        try:
            watcher.Stop()
            watcher.Dispose()
        except Exception:
            pass

    def close(self) -> None:
        self._stop_watcher()
        form = self._form
        if form is None:
            return
        try:
            form.BeginInvoke(_action(form.Close))
        except Exception:
            pass

    # --- everything below runs on the login window's own thread ------------
    def _pump(self) -> None:
        try:
            from System.Drawing import ColorTranslator, Size
            from System.Threading.Tasks import TaskScheduler
            import System.Windows.Forms as WinForms
            from System.Windows.Forms import (
                Application,
                DockStyle,
                Form,
                FormStartPosition,
            )

            from Microsoft.Web.WebView2.WinForms import (
                CoreWebView2CreationProperties,
                WebView2,
            )
        except Exception as exc:
            self.error = f'WebView2 is unavailable: {exc}'
            self._done.set()
            return

        try:
            from dannify import account

            form = Form()
            form.Text = 'Sign in with Google'
            form.ClientSize = Size(520, 720)
            form.MinimumSize = Size(420, 560)
            form.StartPosition = FormStartPosition.CenterScreen
            form.BackColor = ColorTranslator.FromHtml(_THEME_BG[self._theme])
            try:
                form.Icon = _app_icon()
            except Exception:
                pass

            view = WebView2()
            view.Dock = DockStyle.Fill
            props = CoreWebView2CreationProperties()
            # Its own profile, deliberately. A WebView2 environment belongs to
            # the thread that made it, so the app's cannot be borrowed from
            # here; and nothing needs sharing anyway, because the session we
            # care about is saved as cookies in account.json. Keeping it on
            # disk means Google can still offer "choose an account" next time.
            _LOGIN_STORAGE.mkdir(parents=True, exist_ok=True)
            props.UserDataFolder = str(_LOGIN_STORAGE)
            view.CreationProperties = props

            def on_ready(sender, args):  # noqa: ANN001
                if not args.IsSuccess:
                    self.error = 'The sign-in browser could not start'
                    logger_print('login webview failed:', args.InitializationException)
                    form.Close()
                    return
                core = view.CoreWebView2
                # Google turns away anything that looks like an embedded view,
                # so report the same desktop Chrome that ytmusicapi does.
                core.Settings.UserAgent = account.USER_AGENT
                core.Settings.AreDefaultContextMenusEnabled = False
                core.Settings.IsStatusBarEnabled = False
                core.Settings.AreDevToolsEnabled = False
                scheduler = TaskScheduler.FromCurrentSynchronizationContext()

                def on_navigated(s2, a2):  # noqa: ANN001
                    self._check(core, scheduler, form)

                core.NavigationCompleted += on_navigated
                core.NewWindowRequested += _keep_in_window

                # YouTube Music is a single-page app: it finishes its
                # navigation and *then* fills the cookie jar over XHR. Waiting
                # only on NavigationCompleted leaves the user staring at the
                # YouTube Music page after a successful sign-in, so also poll
                # while we are on a signed-in host. This ticks on the login
                # window's own thread, never the app's, and stops the moment
                # the session appears.
                watcher = WinForms.Timer()
                watcher.Interval = 400
                watcher.Tick += lambda s3, a3: self._check(core, scheduler, form)
                self._watcher = watcher
                watcher.Start()
                core.Navigate(_LOGIN_URL)

            view.CoreWebView2InitializationCompleted += on_ready
            form.FormClosed += lambda s, e: self._done.set()
            form.Controls.Add(view)
            self._form = form
            view.EnsureCoreWebView2Async(None)
            Application.Run(form)
        except Exception as exc:
            logger_print('login window failed:', exc)
            self.error = str(exc)
        finally:
            self._done.set()

    def _check(self, core, scheduler, form) -> None:  # noqa: ANN001
        """Are we signed in yet? Runs on the login window's own thread."""
        if self._reading or self.cookies:
            return
        try:
            host = str(core.Source).split('/')[2]
        except Exception:
            return
        if host not in _SIGNED_IN_HOSTS:
            return

        def collect(task):  # noqa: ANN001  (marshalled back to this thread)
            self._reading = False
            try:
                jar = {c.Name: c.Value for c in task.Result if c.Value}
            except Exception as exc:
                logger_print('could not read login cookies:', exc)
                return
            if not (jar.get('__Secure-3PAPISID') or jar.get('SAPISID')):
                return  # session still settling; the next tick will retry
            self.cookies = jar
            self._stop_watcher()
            form.Close()

        self._reading = True

        try:
            core.CookieManager.GetCookiesAsync(ORIGIN).ContinueWith(
                _task_action(collect), scheduler
            )
        except Exception as exc:
            self._reading = False
            logger_print('cookie read failed:', exc)


def _keep_in_window(sender, args) -> None:  # noqa: ANN001
    """Google's popups load in the same window instead of a dead end."""
    try:
        args.NewWindow = sender
        args.Handled = True
    except Exception:
        pass


def _action(fn):  # noqa: ANN001
    from System import Action

    return Action(fn)


def _task_action(fn):  # noqa: ANN001
    from System import Action
    from System.Collections.Generic import List
    from System.Threading.Tasks import Task

    from Microsoft.Web.WebView2.Core import CoreWebView2Cookie

    return Action[Task[List[CoreWebView2Cookie]]](fn)
