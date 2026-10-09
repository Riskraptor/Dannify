"""The window itself: state, caption buttons, dragging, sizes, mini player,
zoom, the tray hide and show, quitting."""

from __future__ import annotations

import ctypes

from .base import MINI_H, MINI_MAX_H, MINI_W, _read_prefs, _write_prefs, logger_print, state
from .win32 import (
    HTCAPTION,
    MF_ENABLED,
    MF_GRAYED,
    POINT,
    RECT,
    SC_CLOSE,
    SC_MAXIMIZE,
    SC_MINIMIZE,
    SC_MOVE,
    SC_RESTORE,
    SC_SIZE,
    SM_SWAPBUTTON,
    SWP_NOACTIVATE,
    SWP_NOZORDER,
    TPM_RETURNCMD,
    TPM_RIGHTBUTTON,
    VK_LBUTTON,
    VK_RBUTTON,
    WM_NCLBUTTONDOWN,
    WM_SYSCOMMAND,
    _HT_EDGES,
    _frame_thickness,
    _window_scale,
    _work_area_for,
    user32,
)
from .places import _autostart_state, _current_placement


# ---------------------------------------------------------------------------
# JS API: exposed to the page as window.pywebview.api.*
# (Attributes starting with "_" are private and not exposed.)
# ---------------------------------------------------------------------------


class WindowMixin:
    """DesktopApi's window calls (see api.py)."""

    def _button_down(self) -> bool:
        vk = VK_RBUTTON if user32.GetSystemMetrics(SM_SWAPBUTTON) else VK_LBUTTON
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)

    def _post(self, msg: int, wparam: int = 0, lparam: int = 0) -> None:
        if self._hwnd:
            user32.PostMessageW(self._hwnd, msg, wparam, lparam)

    # --- window -------------------------------------------------------------
    def win_state(self) -> dict:
        hwnd = self._hwnd
        return {
            'platform': 'windows',
            'maximized': bool(hwnd and user32.IsZoomed(hwnd)) and not self._fullscreen,
            'minimized': bool(hwnd and user32.IsIconic(hwnd)),
            'fullscreen': self._fullscreen,
            'mini': self._mini,
            'onTop': self._on_top,
            'nativeFrame': self._native_frame,
            'nativeFramePref': self._native_frame_pref,
            'closeToTray': self._close_to_tray,
            'globalHotkeys': self._global_hotkeys,
            'hotkeysTaken': list(self._hotkeys_taken),
            'autostart': _autostart_state(),
        }

    def win_minimize(self) -> None:
        self._post(WM_SYSCOMMAND, SC_MINIMIZE)

    def win_toggle_maximize(self) -> None:
        if self._fullscreen or self._mini or not self._hwnd:
            return
        self._post(WM_SYSCOMMAND, SC_RESTORE if user32.IsZoomed(self._hwnd) else SC_MAXIMIZE)

    def win_close(self) -> None:
        self._post(WM_SYSCOMMAND, SC_CLOSE)

    def win_set_max_button(self, rect: dict | None = None) -> None:
        """Where the page draws its maximize button, in device pixels.

        Windows needs to know this to offer the snap layouts on hover. Pass
        nothing to take the claim back, which the page does whenever the
        button is not there to be hovered.
        """
        if self._frame is None:
            return
        try:
            if not rect or self._fullscreen or self._mini:
                self._frame.set_max_button(None)
                return
            box = (
                int(rect['left']),
                int(rect['top']),
                int(rect['right']),
                int(rect['bottom']),
            )
        except (KeyError, TypeError, ValueError):
            return
        self._frame.set_max_button(box if box[2] > box[0] and box[3] > box[1] else None)

    def win_start_drag(self) -> None:
        """Hand the drag to Windows' move loop (Aero Snap, drag-to-restore)."""
        if not self._hwnd or self._fullscreen or not self._button_down():
            return
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        lparam = ((pt.y & 0xFFFF) << 16) | (pt.x & 0xFFFF)

        def go():
            user32.ReleaseCapture()
            user32.PostMessageW(self._hwnd, WM_NCLBUTTONDOWN, HTCAPTION, lparam)

        self._ui(go)

    def win_start_resize(self, edge: str) -> None:
        code = _HT_EDGES.get(str(edge))
        if not code or not self._hwnd or self._fullscreen or self._mini:
            return
        if not self._button_down() or user32.IsZoomed(self._hwnd):
            return
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        lparam = ((pt.y & 0xFFFF) << 16) | (pt.x & 0xFFFF)

        def go():
            user32.ReleaseCapture()
            user32.PostMessageW(self._hwnd, WM_NCLBUTTONDOWN, code, lparam)

        self._ui(go)

    def win_system_menu(self) -> None:
        """Right-click on the title bar: the real Windows system menu."""
        hwnd = self._hwnd
        if not hwnd:
            return

        def show():
            menu = user32.GetSystemMenu(hwnd, False)
            if not menu:
                return
            zoomed = bool(user32.IsZoomed(hwnd))
            fixed = self._fullscreen or self._mini
            user32.EnableMenuItem(menu, SC_RESTORE, MF_ENABLED if zoomed else MF_GRAYED)
            user32.EnableMenuItem(menu, SC_MOVE, MF_GRAYED if zoomed or self._fullscreen else MF_ENABLED)
            user32.EnableMenuItem(menu, SC_SIZE, MF_GRAYED if zoomed or fixed else MF_ENABLED)
            user32.EnableMenuItem(menu, SC_MAXIMIZE, MF_GRAYED if zoomed or fixed else MF_ENABLED)
            user32.SetMenuDefaultItem(menu, SC_CLOSE, 0)
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            cmd = user32.TrackPopupMenu(
                menu, TPM_RETURNCMD | TPM_RIGHTBUTTON, pt.x, pt.y, 0, hwnd, None
            )
            if cmd:
                user32.PostMessageW(hwnd, WM_SYSCOMMAND, cmd, 0)

        self._ui(show)

    def win_toggle_fullscreen(self) -> dict:
        if self._window is None or self._mini:
            return self.win_state()
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            self.win_set_max_button(None)  # no caption buttons to snap from
        try:
            self._window.toggle_fullscreen()
        except Exception as exc:
            self._fullscreen = not self._fullscreen
            logger_print('fullscreen failed:', exc)
        self._push_state()
        return self.win_state()

    def win_set_on_top(self, on: bool) -> dict:
        self._on_top = bool(on)
        form = self._form

        def apply():
            form.TopMost = self._on_top

        self._ui(apply, wait=True)
        self._push_state()
        return self.win_state()

    def win_set_mini(self, on: bool) -> dict:
        """Compact always-on-top player (same window, reshaped)."""
        on = bool(on)
        if on == self._mini or self._form is None or not self._hwnd:
            return self.win_state()
        if on and self._fullscreen:
            self.win_toggle_fullscreen()
        if on:
            self.win_set_max_button(None)
        from System.Drawing import Rectangle, Size
        from System.Windows.Forms import FormWindowState

        form = self._form
        hwnd = self._hwnd
        scale = _window_scale(hwnd)
        fx, fy = _frame_thickness(hwnd)

        if on:
            self._pre_mini = _current_placement(hwnd)
            prefs = _read_prefs()

            def enter():
                if form.WindowState != FormWindowState.Normal:
                    form.WindowState = FormWindowState.Normal
                w = int(MINI_W * scale) + 2 * fx
                h = int(MINI_H * scale) + fy
                form.MinimumSize = Size(w, h)
                left, top, right, bottom = _work_area_for(hwnd)
                pos = prefs.get('mini_pos')
                if isinstance(pos, list) and len(pos) == 2:
                    x = max(left, min(int(pos[0] * scale), right - w))
                    y = max(top, min(int(pos[1] * scale), bottom - h))
                else:
                    margin = int(24 * scale)
                    x = right - w - margin + fx
                    y = bottom - h - margin + fy
                form.Bounds = Rectangle(x, y, w, h)
                form.TopMost = True

            self._mini = True
            self._on_top = True
            self._ui(enter, wait=True)
        else:
            restore = self._pre_mini or {}

            def leave():
                rect = RECT()
                if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    # Remember where the *bar* was, not where the window
                    # happens to end. With a panel open the window has grown
                    # upwards, and saving that top would walk the compact
                    # player a little further up the screen every time.
                    top = rect.bottom - (int(MINI_H * scale) + fy)
                    _write_prefs(
                        {'mini_pos': [round(rect.left / scale), round(top / scale)]}
                    )
                form.TopMost = False
                form.MinimumSize = Size(int(state.min_fit[0] * scale), int(state.min_fit[1] * scale))
                if restore:
                    form.Bounds = Rectangle(
                        int(restore['x'] * scale),
                        int(restore['y'] * scale),
                        int(restore['w'] * scale),
                        int(restore['h'] * scale),
                    )
                    if restore.get('maximized'):
                        form.WindowState = FormWindowState.Maximized

            self._mini = False
            self._on_top = False
            self._ui(leave, wait=True)
        self._push_state()
        return self.win_state()

    def win_set_mini_size(self, height: float) -> None:
        """Grow or shrink the compact player when its panel opens or closes.

        The bottom edge stays put, so the window unfolds upwards: it is
        usually parked in the bottom-right corner, and growing downwards
        would push it off the screen.
        """
        if not self._mini or self._form is None or not self._hwnd:
            return
        from System.Drawing import Rectangle, Size

        form = self._form
        hwnd = self._hwnd
        scale = _window_scale(hwnd)
        fy = _frame_thickness(hwnd)[1]
        want = int(max(MINI_H, min(float(height or MINI_H), MINI_MAX_H)) * scale) + fy

        def resize():
            rect = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return
            width = rect.right - rect.left
            _, work_top, _, work_bottom = _work_area_for(hwnd)
            y = rect.bottom - want
            if y < work_top:
                # Not enough room above: fall back to growing downwards.
                y = min(rect.top, max(work_top, work_bottom - want))
            # The minimum has to come off first or the shrink is ignored.
            form.MinimumSize = Size(0, 0)
            form.Bounds = Rectangle(rect.left, y, width, want)
            form.MinimumSize = Size(width, want)

        self._ui(resize, wait=True)

    def win_set_zoom(self, factor: float) -> None:
        """Interface size, and the smallest window that size still fits in.

        Zoom divides the room the interface has: at 125 per cent a 760 pixel
        window gives it 608, which is under the width the desktop layout needs
        and drops it into the narrow one meant for a phone browser. Things
        overlapped and the whole thing stopped looking like an application.

        So the minimum grows with the zoom, and a window already smaller than
        the new minimum is nudged up to it. Whatever size is picked, the
        layout it gets is the real one.
        """

        try:
            value = max(0.5, min(2.0, float(factor)))
        except (TypeError, ValueError):
            return
        if self._form is None or not self._hwnd:
            return

        from System.Drawing import Size

        form = self._form
        hwnd = self._hwnd
        scale = _window_scale(hwnd)
        fx, fy = _frame_thickness(hwnd)
        floor_w = int(state.min_fit[0] * value * scale) + 2 * fx
        floor_h = int(state.min_fit[1] * value * scale) + fy

        def apply():
            form.browser.webview.ZoomFactor = value
            if self._mini or self._fullscreen:
                return
            form.MinimumSize = Size(floor_w, floor_h)
            rect = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width >= floor_w and height >= floor_h:
                return
            # Grow from where it is, and keep it on the screen it is on.
            _, _, work_right, work_bottom = _work_area_for(hwnd)
            want_w, want_h = max(width, floor_w), max(height, floor_h)
            left = min(rect.left, max(0, work_right - want_w))
            top = min(rect.top, max(0, work_bottom - want_h))
            user32.SetWindowPos(
                hwnd, None, left, top, want_w, want_h,
                SWP_NOZORDER | SWP_NOACTIVATE,
            )

        self._ui(apply)

    def win_set_native_frame(self, on: bool) -> dict:
        self._native_frame_pref = bool(on)
        _write_prefs({'native_frame': self._native_frame_pref})
        return self.win_state()

    def _hide_to_tray(self) -> bool:
        """UI thread. Returns True when the window actually went away."""
        if self._tray is None or not self._tray.install():
            return False
        self._hidden = True
        try:
            self._form.Hide()
        except Exception:
            self._hidden = False
            return False
        self._tray.notify_hidden()
        return True

    def _show_from_tray(self) -> None:
        form = self._form
        if form is None:
            return

        def restore():
            from System.Windows.Forms import FormWindowState

            self._hidden = False
            form.Show()
            if form.WindowState == FormWindowState.Minimized:
                form.WindowState = FormWindowState.Normal
            form.Activate()
            if self._hwnd:
                user32.SetForegroundWindow(self._hwnd)
            if self._tray is not None and not self._close_to_tray:
                self._tray.dispose()

        self._ui(restore)
        self._push_state()

    def win_show(self) -> None:
        self._show_from_tray()

    # --- app lifecycle ------------------------------------------------------
    def _quit(self) -> None:
        self._quitting = True
        if self._hidden:
            # A hidden form ignores WM_SYSCOMMAND/SC_CLOSE; close it directly.
            self._ui(lambda: self._form.Close())
        else:
            self._post(WM_SYSCOMMAND, SC_CLOSE)

    def app_quit(self) -> None:
        self._quit()
