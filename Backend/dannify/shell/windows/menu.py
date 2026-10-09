"""Native popup menus (tray and window menus), dark when the app is."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from loguru import logger

from .base import _system_uses_light_theme
from .win32 import (
    POINT,
    _WIN,
    user32,
)


# ---------------------------------------------------------------------------
# Notification-area icon.
#
# Dannify keeps playing when its window is gone, so the tray icon is a real
# control surface, not a decoration: it shows what's playing, exposes
# transport controls, and is the only way back to a window that was closed
# to tray. A click restores, middle-click plays/pauses, right-click is the menu.
# ---------------------------------------------------------------------------
# --- The tray menu, drawn by Windows ---------------------------------------
#
# WinForms cannot draw a Windows 11 menu. Whatever colours you hand a
# ContextMenuStrip you still get the old metrics, the old shadow, square
# corners and no acrylic, which is why it kept reading as something from a
# much older program next to every other tray icon on the taskbar.
#
# So this stops trying to imitate one and asks Windows for the real thing:
# CreatePopupMenu plus TrackPopupMenuEx. The menu is then drawn by the shell,
# which means it matches the system exactly and follows it when it changes.
#
# Dark mode needs one nudge. The APIs for it are exported by uxtheme as
# ordinals with no names, which is undocumented but is what every Windows
# application using native menus in dark mode does; if a future Windows drops
# them the calls fail and the menu is simply light.

MF_STRING = 0x0000


MF_SEPARATOR = 0x0800


MF_GRAYED = 0x0001


MF_DISABLED = 0x0002


MFS_DEFAULT = 0x1000


TPM_RIGHTBUTTON = 0x0002


TPM_RETURNCMD = 0x0100


TPM_NONOTIFY = 0x0080


_dark_menus_ready = False


def _enable_dark_menus() -> None:
    """Ask Windows to draw menus dark when the system is dark."""

    global _dark_menus_ready
    if _dark_menus_ready or not _WIN:
        return
    _dark_menus_ready = True
    if _system_uses_light_theme():
        return
    try:
        uxtheme = ctypes.WinDLL('uxtheme')
        # 135 = SetPreferredAppMode, 136 = FlushMenuThemes. Ordinals, because
        # Microsoft never gave them names.
        set_mode = uxtheme[135]
        set_mode.restype = ctypes.c_int
        set_mode.argtypes = [ctypes.c_int]
        set_mode(2)  # ForceDark
        try:
            uxtheme[136]()
        except Exception:
            pass
    except Exception:
        logger.opt(exception=True).debug('dark menus unavailable')


class _NativeMenu:
    """A Win32 popup menu. Items are (label, callback, flags)."""

    def __init__(self) -> None:
        self._items: list = []

    def add(self, label: str, action=None, *, enabled: bool = True,
            default: bool = False) -> None:
        self._items.append((label, action, enabled, default))

    def add_separator(self) -> None:
        self._items.append((None, None, False, False))

    def show(self, hwnd: int) -> None:
        """Pop the menu at the cursor and run whatever was chosen."""

        _enable_dark_menus()
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        actions: dict[int, object] = {}
        try:
            for index, (label, action, enabled, default) in enumerate(self._items, 1):
                if label is None:
                    user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                    continue
                flags = MF_STRING
                if not enabled:
                    flags |= MF_GRAYED | MF_DISABLED
                user32.AppendMenuW(menu, flags, index, label)
                if default:
                    user32.SetMenuDefaultItem(menu, index, 0)
                actions[index] = action

            point = POINT()
            user32.GetCursorPos(ctypes.byref(point))
            # The documented dance: a popup menu will not dismiss on an
            # outside click unless its owner window is in the foreground,
            # and the trailing null message clears the menu state.
            user32.SetForegroundWindow(wintypes.HWND(hwnd))
            chosen = user32.TrackPopupMenuEx(
                menu,
                TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                point.x,
                point.y,
                wintypes.HWND(hwnd),
                None,
            )
            user32.PostMessageW(wintypes.HWND(hwnd), 0x0000, 0, 0)
        finally:
            user32.DestroyMenu(menu)

        action = actions.get(int(chosen or 0))
        if callable(action):
            try:
                action()
            except Exception:
                logger.opt(exception=True).debug('tray menu action failed')
