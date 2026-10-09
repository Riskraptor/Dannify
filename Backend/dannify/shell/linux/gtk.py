"""GTK, loaded once, and a way to run code on its thread.

GTK may only be touched from the thread running its main loop. The bridge
calls arrive on pywebview's worker threads, so everything they do to the
window goes through on_ui.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
try:
    gi.require_version('WebKit2', '4.1')
except ValueError:
    gi.require_version('WebKit2', '4.0')

from gi.repository import Gdk, Gio, GLib, Gtk, WebKit2  # noqa: E402

__all__ = ['Gdk', 'Gio', 'GLib', 'Gtk', 'WebKit2', 'on_ui', 'find_webview']


def on_ui(fn: Callable[[], Any], wait: bool = False, timeout: float = 10.0) -> Optional[Any]:
    """Run *fn* on the GTK thread; with *wait*, return what it returned."""

    if threading.current_thread() is threading.main_thread():
        return fn()
    done = threading.Event()
    box: list[Any] = []

    def run() -> bool:
        try:
            box.append(fn())
        except Exception:
            from loguru import logger

            logger.opt(exception=True).debug('ui call failed')
        finally:
            done.set()
        return False  # once, not again on every idle

    GLib.idle_add(run)
    if wait:
        done.wait(timeout)
        return box[0] if box else None
    return None


def find_webview(widget: Any) -> Optional[Any]:
    """The WebKit view inside pywebview's window, wherever it nests it."""

    if isinstance(widget, WebKit2.WebView):
        return widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found = find_webview(child)
            if found is not None:
                return found
    return None
