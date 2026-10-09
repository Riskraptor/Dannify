"""The taskbar button: thumbnail toolbar (prev / play / next) and progress."""

from __future__ import annotations

import ctypes

from .win32 import (
    HWND,
    SM_CXSMICON,
    UINT,
    ole32,
    user32,
)


# ---------------------------------------------------------------------------
# Taskbar: thumbnail toolbar (prev / play-pause / next) + progress bar.
# Raw ITaskbarList3 COM via ctypes; every call runs on the UI (STA) thread.
# ---------------------------------------------------------------------------
class _GUID(ctypes.Structure):
    _fields_ = [
        ('Data1', ctypes.c_uint32),
        ('Data2', ctypes.c_uint16),
        ('Data3', ctypes.c_uint16),
        ('Data4', ctypes.c_ubyte * 8),
    ]

    @classmethod
    def parse(cls, text: str) -> '_GUID':
        g = cls()
        ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(g))
        return g


class _THUMBBUTTON(ctypes.Structure):
    _fields_ = [
        ('dwMask', ctypes.c_uint32),
        ('iId', ctypes.c_uint32),
        ('iBitmap', ctypes.c_uint32),
        ('hIcon', ctypes.c_void_p),
        ('szTip', ctypes.c_wchar * 260),
        ('dwFlags', ctypes.c_uint32),
    ]


THB_ICON, THB_TOOLTIP, THB_FLAGS = 0x2, 0x4, 0x8


THBF_ENABLED, THBF_DISABLED = 0x0, 0x1


TBPF_NOPROGRESS, TBPF_INDETERMINATE, TBPF_NORMAL, TBPF_ERROR, TBPF_PAUSED = 0, 1, 2, 4, 8


BTN_PREV, BTN_PLAY, BTN_NEXT = 1, 2, 3


class _Taskbar:
    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self._ptr = ctypes.c_void_p()
        self._icons: dict[str, int] = {}
        self._buttons_added = False
        self.playing = False
        self.has_track = False
        self.labels = {'prev': 'Previous', 'play': 'Play', 'pause': 'Pause', 'next': 'Next'}

    def _method(self, index: int, *argtypes):
        vtbl = ctypes.cast(self._ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtbl[index])

    def _ensure(self) -> bool:
        if self._ptr.value:
            return True
        clsid = _GUID.parse('{56FDF344-FD6D-11d0-958A-006097C9A090}')
        iid = _GUID.parse('{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}')
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(self._ptr)
        )
        if hr != 0 or not self._ptr.value:
            self._ptr = ctypes.c_void_p()
            return False
        self._method(3)(self._ptr)  # HrInit
        return True

    # --- icons: drawn at runtime with GDI+, matching the taskbar theme ------
    def _make_icons(self) -> None:
        if self._icons:
            return
        import clr  # noqa: F401  (pythonnet)
        from System import Array
        from System.Drawing import Bitmap, Color, Graphics, PointF, RectangleF, SolidBrush
        from System.Drawing.Drawing2D import SmoothingMode

        size = max(16, user32.GetSystemMetrics(SM_CXSMICON))
        light_taskbar = False
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize',
            ) as key:
                light_taskbar = winreg.QueryValueEx(key, 'SystemUsesLightTheme')[0] == 1
        except Exception:
            pass
        color = Color.FromArgb(255, 32, 32, 32) if light_taskbar else Color.White
        s = float(size)

        def draw(shapes) -> int:
            bmp = Bitmap(size, size)
            g = Graphics.FromImage(bmp)
            g.SmoothingMode = SmoothingMode.AntiAlias
            g.Clear(Color.Transparent)
            brush = SolidBrush(color)
            for kind, pts in shapes:
                if kind == 'poly':
                    g.FillPolygon(brush, Array[PointF]([PointF(x * s, y * s) for x, y in pts]))
                else:
                    x, y, w, h = pts
                    g.FillRectangle(brush, RectangleF(x * s, y * s, w * s, h * s))
            g.Dispose()
            handle = bmp.GetHicon().ToInt64()
            bmp.Dispose()
            return handle

        self._icons = {
            'play': draw([('poly', [(0.28, 0.16), (0.84, 0.5), (0.28, 0.84)])]),
            'pause': draw([('rect', (0.22, 0.18, 0.2, 0.64)), ('rect', (0.58, 0.18, 0.2, 0.64))]),
            'prev': draw([('rect', (0.16, 0.2, 0.12, 0.6)), ('poly', [(0.84, 0.2), (0.32, 0.5), (0.84, 0.8)])]),
            'next': draw([('poly', [(0.16, 0.2), (0.68, 0.5), (0.16, 0.8)]), ('rect', (0.72, 0.2, 0.12, 0.6))]),
        }

    def _buttons(self):
        arr = (_THUMBBUTTON * 3)()
        state = THBF_ENABLED if self.has_track else THBF_DISABLED
        spec = [
            (BTN_PREV, 'prev', self.labels['prev']),
            (BTN_PLAY, 'pause' if self.playing else 'play', self.labels['pause' if self.playing else 'play']),
            (BTN_NEXT, 'next', self.labels['next']),
        ]
        for i, (bid, icon, tip) in enumerate(spec):
            arr[i].dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS
            arr[i].iId = bid
            arr[i].hIcon = self._icons.get(icon, 0)
            arr[i].szTip = tip
            arr[i].dwFlags = state
        return arr

    def add_buttons(self) -> None:
        if not self._ensure():
            return
        self._make_icons()
        arr = self._buttons()
        fn = self._method(15, HWND, UINT, ctypes.POINTER(_THUMBBUTTON))
        if fn(self._ptr, self.hwnd, 3, arr) == 0:
            self._buttons_added = True

    def update_buttons(self) -> None:
        if not self._buttons_added:
            return
        arr = self._buttons()
        self._method(16, HWND, UINT, ctypes.POINTER(_THUMBBUTTON))(self._ptr, self.hwnd, 3, arr)

    def set_progress(self, value: float, mode: str) -> None:
        if not self._ensure():
            return
        flag = {
            'none': TBPF_NOPROGRESS,
            'indeterminate': TBPF_INDETERMINATE,
            'error': TBPF_ERROR,
            'paused': TBPF_PAUSED,
        }.get(mode, TBPF_NORMAL)
        self._method(10, HWND, ctypes.c_int)(self._ptr, self.hwnd, flag)
        if flag in (TBPF_NORMAL, TBPF_ERROR, TBPF_PAUSED):
            done = int(max(0.0, min(1.0, value)) * 1000)
            self._method(9, HWND, ctypes.c_ulonglong, ctypes.c_ulonglong)(
                self._ptr, self.hwnd, done, 1000
            )

    def reset(self) -> None:
        """Explorer restarted: the old COM object and buttons are gone."""
        if self._ptr.value:
            try:
                self._method(2)(self._ptr)  # IUnknown::Release
            except Exception:
                pass
        self._ptr = ctypes.c_void_p()
        self._buttons_added = False

    def dispose(self) -> None:
        for handle in self._icons.values():
            try:
                user32.DestroyIcon(handle)
            except Exception:
                pass
        self._icons = {}
