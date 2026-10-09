"""AppKit, loaded once, and a way to run code on the main thread.

AppKit may only be touched from the main thread, which runs the app's event
loop. The bridge calls arrive on pywebview's worker threads, so everything
they do to a window goes through on_main.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

import AppKit  # noqa: F401  (re-exported for the other modules)
import Foundation  # noqa: F401
from loguru import logger
from PyObjCTools import AppHelper

__all__ = ['AppKit', 'Foundation', 'on_main', 'os_major', 'hex_color']


def on_main(fn: Callable[[], Any], wait: bool = False, timeout: float = 10.0) -> Optional[Any]:
    """Run *fn* on the main thread; with *wait*, return what it returned."""

    if threading.current_thread() is threading.main_thread():
        return fn()
    done = threading.Event()
    box: list[Any] = []

    def run() -> None:
        try:
            box.append(fn())
        except Exception:
            logger.opt(exception=True).debug('ui call failed')
        finally:
            done.set()

    AppHelper.callAfter(run)
    if wait:
        done.wait(timeout)
        return box[0] if box else None
    return None


def os_major() -> int:
    """The macOS major version (11 for Big Sur, 14 for Sonoma)."""

    try:
        return int(Foundation.NSProcessInfo.processInfo().operatingSystemVersion().majorVersion)
    except Exception:
        return 0


def hex_color(value: str):
    """An NSColor from '#rrggbb'."""

    value = value.lstrip('#')
    r, g, b = (int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0)
