"""The window's own title bar on a native Windows frame (see _CustomFrame)."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from .base import logger_print
from .win32 import (
    GWL_STYLE,
    HTCLIENT,
    HTMAXBUTTON,
    HWND,
    LPARAM,
    LRESULT,
    POINT,
    RECT,
    SWP_FRAMECHANGED,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_NOZORDER,
    THBN_CLICKED,
    TME_LEAVE,
    TME_NONCLIENT,
    TRACKMOUSEEVENT,
    UINT,
    WM_COMMAND,
    WM_HOTKEY,
    WM_NCCALCSIZE,
    WM_NCDESTROY,
    WM_NCHITTEST,
    WM_NCLBUTTONDOWN,
    WM_NCLBUTTONUP,
    WM_NCMOUSELEAVE,
    WM_NCMOUSEMOVE,
    WPARAM,
    WS_CAPTION,
    _frame_thickness,
    _hiword,
    _loword,
    _proto,
    user32,
)


# ---------------------------------------------------------------------------
# Custom frame: remove the Windows caption, keep everything else native.
#
# The window keeps WS_OVERLAPPEDWINDOW, so Windows still treats it as a
# normal resizable window (Aero Snap, Win+arrows, min/max animations,
# taskbar click-to-minimize, DWM shadow, Win11 rounded corners). We only
# answer WM_NCCALCSIZE so the client area starts at the very top of the
# window: the caption strip is reclaimed for the web UI's own title bar,
# while the left/right/bottom resize borders stay native (and invisible).
# ---------------------------------------------------------------------------
class _CustomFrame:
    def __init__(
        self,
        hwnd: int,
        on_command=None,
        on_taskbar_created=None,
        on_maximize=None,
        on_max_hover=None,
        on_hotkey=None,
    ):
        self.hwnd = hwnd
        self._on_hotkey = on_hotkey
        self.installed = False
        self._on_command = on_command
        self._on_taskbar_created = on_taskbar_created
        self._on_maximize = on_maximize
        self._on_max_hover = on_max_hover
        self._taskbar_msg = 0
        self._proc = None
        self._comctl = None
        # Where the page draws its maximize button, in device pixels relative
        # to the client area. None until the interface reports it.
        self._max_rect: tuple[int, int, int, int] | None = None
        self._max_hover = False

    def install(self) -> bool:
        """Must run on the window's UI thread."""
        try:
            comctl = ctypes.WinDLL('comctl32')
            SUBCLASSPROC = ctypes.WINFUNCTYPE(
                LRESULT, HWND, UINT, WPARAM, LPARAM, ctypes.c_size_t, ctypes.c_size_t
            )
            _proto(comctl.SetWindowSubclass, wintypes.BOOL, HWND, SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t)
            _proto(comctl.DefSubclassProc, LRESULT, HWND, UINT, WPARAM, LPARAM)
            _proto(comctl.RemoveWindowSubclass, wintypes.BOOL, HWND, SUBCLASSPROC, ctypes.c_size_t)
            self._comctl = comctl
            self._taskbar_msg = user32.RegisterWindowMessageW('TaskbarButtonCreated')

            def proc(hwnd, msg, wparam, lparam, uid, ref):  # noqa: ANN001
                try:
                    if msg == WM_NCCALCSIZE and wparam:
                        return self._nccalcsize(hwnd, msg, wparam, lparam)
                    if msg == WM_NCHITTEST:
                        return self._hittest(hwnd, msg, wparam, lparam)
                    # Having told Windows the button is part of the frame, we
                    # own what happens there: the page never sees the mouse.
                    if msg == WM_NCMOUSEMOVE and wparam == HTMAXBUTTON:
                        self._set_hover(True)
                        return 0
                    if msg in (WM_NCMOUSEMOVE, WM_NCMOUSELEAVE):
                        self._set_hover(False)
                    if msg == WM_NCLBUTTONDOWN and wparam == HTMAXBUTTON:
                        return 0
                    if msg == WM_NCLBUTTONUP and wparam == HTMAXBUTTON:
                        if self._on_maximize:
                            self._on_maximize()
                        return 0
                    if msg == WM_COMMAND and (wparam >> 16) & 0xFFFF == THBN_CLICKED:
                        if self._on_command:
                            self._on_command(wparam & 0xFFFF)
                        return 0
                    if msg == WM_HOTKEY:
                        if self._on_hotkey:
                            self._on_hotkey(int(wparam))
                        return 0
                    if self._taskbar_msg and msg == self._taskbar_msg:
                        if self._on_taskbar_created:
                            self._on_taskbar_created()
                    if msg == WM_NCDESTROY:
                        comctl.RemoveWindowSubclass(hwnd, self._proc, 1)
                except Exception:
                    pass
                return comctl.DefSubclassProc(hwnd, msg, wparam, lparam)

            # Keep a reference: if the callback is garbage-collected the
            # process crashes on the next window message.
            self._proc = SUBCLASSPROC(proc)
            if not comctl.SetWindowSubclass(self.hwnd, self._proc, 1, 0):
                return False
            self.installed = True
            # Re-run WM_NCCALCSIZE now so the caption disappears before the
            # window is ever painted.
            user32.SetWindowPos(
                self.hwnd,
                None,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )
            return True
        except Exception as exc:
            logger_print('custom frame unavailable:', exc)
            return False

    def _nccalcsize(self, hwnd, msg, wparam, lparam):  # noqa: ANN001
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        rect = RECT.from_address(lparam)
        original_top = rect.top
        # Let Windows compute the standard frame (keeps the side/bottom
        # resize borders), then give the caption strip back to the client.
        self._comctl.DefSubclassProc(hwnd, msg, wparam, lparam)
        if not style & WS_CAPTION:
            return 0  # borderless (e.g. fullscreen): nothing to reclaim
        rect = RECT.from_address(lparam)
        rect.top = original_top
        if user32.IsZoomed(hwnd):
            # Maximized windows hang over the monitor edge by the frame
            # width; keep the top of our UI on-screen.
            rect.top += _frame_thickness(hwnd)[1]
        return 0

    # --- Windows 11 snap layouts -------------------------------------------
    # The maximize button is drawn by the page, so as far as Windows is
    # concerned this window has no maximize button and the hover flyout with
    # the snap layouts never appears. That flyout is how a lot of people put
    # two windows side by side, and its absence is exactly what made the app
    # feel unlike everything else on the desktop.
    #
    # Getting it back is one message: report HTMAXBUTTON from WM_NCHITTEST
    # over the rectangle the page tells us about. The shell does the rest,
    # including the flyout's timing and its keyboard handling. The cost is
    # that Windows then treats that rectangle as frame, so the hover state
    # and the click have to be handed back to the page by hand.

    def set_max_button(self, rect: tuple[int, int, int, int] | None) -> None:
        self._max_rect = rect
        if rect is None:
            self._set_hover(False)

    def _hittest(self, hwnd, msg, wparam, lparam):  # noqa: ANN001
        where = self._comctl.DefSubclassProc(hwnd, msg, wparam, lparam)
        # Only ever claim ordinary client space: the invisible resize borders
        # win, so dragging the top edge above the button still resizes.
        if where != HTCLIENT or not self._max_rect:
            return where
        left, top, right, bottom = self._max_rect
        pt = POINT(_loword(lparam), _hiword(lparam))
        if not user32.ScreenToClient(hwnd, ctypes.byref(pt)):
            return where
        if left <= pt.x < right and top <= pt.y < bottom:
            return HTMAXBUTTON
        return where

    def _set_hover(self, on: bool) -> None:
        if on == self._max_hover:
            return
        self._max_hover = on
        if on:
            # Nothing else asks for it, and without it the mouse leaving the
            # button never gets reported, so it stays lit forever.
            self._track_leave()
        if self._on_max_hover:
            self._on_max_hover(on)

    def _track_leave(self) -> None:
        try:
            event = TRACKMOUSEEVENT()
            event.cbSize = ctypes.sizeof(TRACKMOUSEEVENT)
            event.dwFlags = TME_LEAVE | TME_NONCLIENT
            event.hwndTrack = self.hwnd
            event.dwHoverTime = 0
            user32.TrackMouseEvent(ctypes.byref(event))
        except Exception:
            pass
