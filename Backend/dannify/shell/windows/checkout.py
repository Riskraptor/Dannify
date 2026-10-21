"""PayPal's checkout in a window of Dannify's own, for supporting the app.

Giving should not mean leaving: the Support Dannify checkout made in PayPal
opens here, in a window titled for it, on a thread and message loop of its
own as the sign-in window is (see login.py), so the music keeps playing while
someone pays. PayPal's own pages do the paying; Dannify never sees a card or
an account. When PayPal sends the person on to the "thank you" address after
paying, the window closes and the app says thank you.
"""

from __future__ import annotations

import re
import threading

from .base import _DATA_DIR, _THEME_BG, _app_icon, logger_print

# Only PayPal's own checkout pages open here: a URL from the page is checked
# before anything is shown.
_ALLOWED = re.compile(
    r'^https://www\.paypal\.com/(ncp/payment/[A-Z0-9][A-Z0-9-]{5,40}|paypalme/[A-Za-z0-9_-]{2,40})/?$'
)
# Where PayPal sends someone once they have paid (the return address the
# payment link was made with): seeing it means the payment went through.
RETURN_PREFIX = 'https://github.com/Riskraptor/Dannify'
_STORAGE = _DATA_DIR / 'Checkout'


def allowed(url: str) -> bool:
    return bool(_ALLOWED.match(str(url or '')))


class _CheckoutWindow:
    """The checkout window, running its own WinForms message loop."""

    TIMEOUT = 30 * 60

    def __init__(self, theme: str, url: str, title: str):
        self._theme = theme
        self._url = url
        self._title = title or 'Support Dannify'
        self._done = threading.Event()
        self._form = None
        self.paid = False
        self.error = ''

    def run(self) -> dict:
        """Show the window and block (on a worker thread) until it closes."""
        try:
            from System.Threading import ApartmentState
            from System.Threading import Thread as ClrThread
            from System.Threading import ThreadStart

            thread = ClrThread(ThreadStart(self._pump))
            thread.SetApartmentState(ApartmentState.STA)
            thread.IsBackground = True
            thread.Start()
        except Exception as exc:
            logger_print('could not start the checkout thread:', exc)
            self.error = str(exc)
            return {'opened': False, 'paid': False, 'error': self.error}
        self._done.wait(self.TIMEOUT)
        self.close()
        return {'opened': not self.error, 'paid': self.paid, 'error': self.error}

    def focus(self) -> None:
        form = self._form
        if form is None:
            return
        try:
            from System import Action

            form.BeginInvoke(Action(form.Activate))
        except Exception:
            pass

    def close(self) -> None:
        form = self._form
        if form is None:
            return
        try:
            from System import Action

            form.BeginInvoke(Action(form.Close))
        except Exception:
            pass

    # --- everything below runs on the checkout window's own thread ----------
    def _pump(self) -> None:
        try:
            from System.Drawing import ColorTranslator, Size
            from System.Windows.Forms import Application, DockStyle, Form, FormStartPosition

            from Microsoft.Web.WebView2.WinForms import CoreWebView2CreationProperties, WebView2
        except Exception as exc:
            self.error = f'WebView2 is unavailable: {exc}'
            self._done.set()
            return

        try:
            form = Form()
            form.Text = self._title
            form.ClientSize = Size(540, 780)
            form.MinimumSize = Size(440, 600)
            form.StartPosition = FormStartPosition.CenterScreen
            form.BackColor = ColorTranslator.FromHtml(_THEME_BG.get(self._theme, _THEME_BG['dark']))
            try:
                form.Icon = _app_icon()
            except Exception:
                pass

            view = WebView2()
            view.Dock = DockStyle.Fill
            props = CoreWebView2CreationProperties()
            # A profile of its own: nothing of the app's, and the app's
            # nothing of PayPal's.
            _STORAGE.mkdir(parents=True, exist_ok=True)
            props.UserDataFolder = str(_STORAGE)
            view.CreationProperties = props

            def on_ready(sender, args):  # noqa: ANN001
                if not args.IsSuccess:
                    self.error = 'The checkout could not start'
                    logger_print('checkout webview failed:', args.InitializationException)
                    form.Close()
                    return
                core = view.CoreWebView2
                core.Settings.AreDevToolsEnabled = False
                core.Settings.IsStatusBarEnabled = False

                def on_navigating(s2, a2):  # noqa: ANN001
                    # Paid: PayPal is sending them to the thank-you address.
                    try:
                        uri = str(a2.Uri)
                    except Exception:
                        return
                    if uri.startswith(RETURN_PREFIX):
                        a2.Cancel = True
                        self.paid = True
                        form.Close()

                core.NavigationStarting += on_navigating
                core.Navigate(self._url)

            view.CoreWebView2InitializationCompleted += on_ready
            form.FormClosed += lambda s, e: self._done.set()
            form.Controls.Add(view)
            self._form = form
            view.EnsureCoreWebView2Async(None)
            Application.Run(form)
        except Exception as exc:
            logger_print('checkout window failed:', exc)
            self.error = str(exc)
        finally:
            self._done.set()
