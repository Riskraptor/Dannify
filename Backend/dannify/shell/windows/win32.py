"""Win32 plumbing (ctypes): the handles, messages and measures the other parts use.

Everything is optional: if a call is unavailable the app still runs, just
with one less native nicety.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


# ---------------------------------------------------------------------------
# Win32 plumbing (ctypes). Everything is optional: if a call is unavailable
# the app still runs, just with one less native nicety.
# ---------------------------------------------------------------------------
_WIN = os.name == 'nt'


if _WIN:
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    shell32 = ctypes.WinDLL('shell32')
    ole32 = ctypes.WinDLL('ole32')
    dwmapi = ctypes.WinDLL('dwmapi')

    LRESULT = ctypes.c_ssize_t
    HWND = wintypes.HWND
    UINT = wintypes.UINT
    WPARAM = wintypes.WPARAM
    LPARAM = wintypes.LPARAM

    class RECT(ctypes.Structure):
        _fields_ = [
            ('left', ctypes.c_long),
            ('top', ctypes.c_long),
            ('right', ctypes.c_long),
            ('bottom', ctypes.c_long),
        ]

    class POINT(ctypes.Structure):
        _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

    class TRACKMOUSEEVENT(ctypes.Structure):
        _fields_ = [
            ('cbSize', wintypes.DWORD),
            ('dwFlags', wintypes.DWORD),
            ('hwndTrack', HWND),
            ('dwHoverTime', wintypes.DWORD),
        ]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ('cbSize', wintypes.DWORD),
            ('rcMonitor', RECT),
            ('rcWork', RECT),
            ('dwFlags', wintypes.DWORD),
        ]

    class WINDOWPLACEMENT(ctypes.Structure):
        _fields_ = [
            ('length', UINT),
            ('flags', UINT),
            ('showCmd', UINT),
            ('ptMinPosition', POINT),
            ('ptMaxPosition', POINT),
            ('rcNormalPosition', RECT),
        ]

    def _proto(fn, restype, *argtypes):
        fn.restype = restype
        fn.argtypes = list(argtypes)
        return fn

    _proto(user32.PostMessageW, wintypes.BOOL, HWND, UINT, WPARAM, LPARAM)
    _proto(user32.RegisterHotKey, wintypes.BOOL, HWND, ctypes.c_int, UINT, UINT)
    _proto(user32.UnregisterHotKey, wintypes.BOOL, HWND, ctypes.c_int)
    _proto(user32.IsZoomed, wintypes.BOOL, HWND)
    _proto(user32.IsIconic, wintypes.BOOL, HWND)
    _proto(user32.IsWindowVisible, wintypes.BOOL, HWND)
    _proto(user32.CreatePopupMenu, wintypes.HMENU)
    _proto(user32.AppendMenuW, wintypes.BOOL,
           wintypes.HMENU, UINT, ctypes.c_size_t, wintypes.LPCWSTR)
    _proto(user32.SetMenuDefaultItem, wintypes.BOOL, wintypes.HMENU, UINT, UINT)
    _proto(user32.TrackPopupMenuEx, wintypes.BOOL,
           wintypes.HMENU, UINT, ctypes.c_int, ctypes.c_int, HWND, ctypes.c_void_p)
    _proto(user32.DestroyMenu, wintypes.BOOL, wintypes.HMENU)
    _proto(user32.GetCursorPos, wintypes.BOOL, ctypes.POINTER(POINT))
    _proto(user32.ScreenToClient, wintypes.BOOL, HWND, ctypes.POINTER(POINT))
    _proto(user32.TrackMouseEvent, wintypes.BOOL, ctypes.POINTER(TRACKMOUSEEVENT))
    _proto(user32.GetAsyncKeyState, ctypes.c_short, ctypes.c_int)
    _proto(user32.GetSystemMetrics, ctypes.c_int, ctypes.c_int)
    _proto(user32.GetWindowRect, wintypes.BOOL, HWND, ctypes.POINTER(RECT))
    _proto(user32.GetWindowPlacement, wintypes.BOOL, HWND, ctypes.POINTER(WINDOWPLACEMENT))
    _proto(user32.SetWindowPos, wintypes.BOOL, HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, UINT)
    _proto(user32.MonitorFromWindow, wintypes.HANDLE, HWND, wintypes.DWORD)
    _proto(user32.MonitorFromRect, wintypes.HANDLE, ctypes.POINTER(RECT), wintypes.DWORD)
    _proto(user32.GetMonitorInfoW, wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(MONITORINFO))
    _proto(user32.GetWindowLongW, ctypes.c_long, HWND, ctypes.c_int)
    _proto(user32.GetSystemMenu, wintypes.HMENU, HWND, wintypes.BOOL)
    _proto(user32.EnableMenuItem, wintypes.BOOL, wintypes.HMENU, UINT, UINT)
    _proto(user32.SetMenuDefaultItem, wintypes.BOOL, wintypes.HMENU, UINT, UINT)
    _proto(user32.TrackPopupMenu, wintypes.BOOL, wintypes.HMENU, UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, HWND, ctypes.c_void_p)
    _proto(user32.SetForegroundWindow, wintypes.BOOL, HWND)
    _proto(user32.ShowWindow, wintypes.BOOL, HWND, ctypes.c_int)
    _proto(user32.GetWindowThreadProcessId, wintypes.DWORD, HWND, ctypes.POINTER(wintypes.DWORD))
    _proto(user32.GetWindow, HWND, HWND, UINT)
    _proto(user32.RegisterWindowMessageW, UINT, wintypes.LPCWSTR)
    _proto(user32.OpenClipboard, wintypes.BOOL, HWND)
    _proto(user32.CloseClipboard, wintypes.BOOL)
    _proto(user32.GetClipboardData, wintypes.HANDLE, UINT)
    _proto(user32.DestroyIcon, wintypes.BOOL, wintypes.HICON)
    _proto(kernel32.GlobalLock, ctypes.c_void_p, wintypes.HGLOBAL)
    _proto(kernel32.GlobalUnlock, wintypes.BOOL, wintypes.HGLOBAL)
    # Handles are pointer-sized; without these the default c_int truncates them.
    _proto(kernel32.OpenProcess, wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _proto(kernel32.WaitForSingleObject, wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD)
    _proto(kernel32.CloseHandle, wintypes.BOOL, wintypes.HANDLE)
    _proto(dwmapi.DwmSetWindowAttribute, ctypes.c_long, HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)

    _EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, LPARAM)
    _proto(user32.EnumWindows, wintypes.BOOL, _EnumWindowsProc, LPARAM)

    try:
        _proto(user32.GetDpiForWindow, UINT, HWND)
        _proto(user32.GetSystemMetricsForDpi, ctypes.c_int, ctypes.c_int, UINT)
        _HAS_DPI_API = True
    except AttributeError:  # pre-Windows 10 1607
        _HAS_DPI_API = False


# Window messages / constants
WM_HOTKEY = 0x0312


MOD_ALT = 0x0001


MOD_CONTROL = 0x0002


MOD_NOREPEAT = 0x4000


# System-wide shortcuts (a setting, off unless turned on): Ctrl+Alt with
# P, Right and Left. P, not Space: Ctrl+Alt+Space is held by other programs
# often enough (it was on the PC this was built on). Off by default because some graphics drivers use
# Ctrl+Alt+arrows to turn the screen, and an app should not take keys away
# from the rest of the PC without being asked.
_HOTKEYS = {
    1: (0x50, 'toggle', 'Ctrl+Alt+P'),
    2: (0x27, 'next', 'Ctrl+Alt+Right'),
    3: (0x25, 'prev', 'Ctrl+Alt+Left'),
}


WM_NCCALCSIZE = 0x0083


WM_NCDESTROY = 0x0082


WM_COMMAND = 0x0111


WM_SYSCOMMAND = 0x0112


WM_NCLBUTTONDOWN = 0x00A1


SC_SIZE = 0xF000


SC_MOVE = 0xF010


SC_MINIMIZE = 0xF020


SC_MAXIMIZE = 0xF030


SC_CLOSE = 0xF060


SC_RESTORE = 0xF120


HTCAPTION = 2


# Returning this from WM_NCHITTEST over the maximize button is what makes
# Windows 11 offer its snap layouts on hover. A custom frame that never
# reports it gets no flyout, which is why the app felt unlike every other
# window: the shortcut people expect simply was not there.
HTMAXBUTTON = 9


WM_NCHITTEST = 0x0084


WM_NCMOUSEMOVE = 0x00A0


WM_NCMOUSELEAVE = 0x02A2


WM_NCLBUTTONDOWN = 0x00A1


WM_NCLBUTTONUP = 0x00A2


HTCLIENT = 1


TME_LEAVE = 0x0002


TME_NONCLIENT = 0x0010


_HT_EDGES = {
    'left': 10,
    'right': 11,
    'top': 12,
    'top-left': 13,
    'top-right': 14,
    'bottom': 15,
    'bottom-left': 16,
    'bottom-right': 17,
}


GWL_STYLE = -16


WS_CAPTION = 0x00C00000


SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED = (
    0x1,
    0x2,
    0x4,
    0x10,
    0x20,
)


MONITOR_DEFAULTTONEAREST = 2


SM_CXFRAME, SM_CYFRAME, SM_CXPADDEDBORDER, SM_SWAPBUTTON, SM_CXSMICON = 32, 33, 92, 23, 49


VK_LBUTTON, VK_RBUTTON = 0x01, 0x02


SW_RESTORE, SW_MAXIMIZE = 9, 3


SW_SHOW = 5


# GetSystemMetrics: non-zero while the session is ending.
SM_SHUTTINGDOWN = 0x2000


MF_BYCOMMAND, MF_ENABLED, MF_GRAYED = 0x0, 0x0, 0x1


TPM_RETURNCMD, TPM_RIGHTBUTTON = 0x0100, 0x0002


GW_OWNER = 4


DWMWA_USE_IMMERSIVE_DARK_MODE = 20


THBN_CLICKED = 0x1800


def _window_scale(hwnd) -> float:
    try:
        if _HAS_DPI_API and hwnd:
            return user32.GetDpiForWindow(hwnd) / 96.0
    except Exception:
        pass
    return 1.0


def _frame_thickness(hwnd) -> tuple[int, int]:
    """Width of the (invisible) resize border Windows adds around a window."""
    try:
        if _HAS_DPI_API and hwnd:
            dpi = user32.GetDpiForWindow(hwnd)
            pad = user32.GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi)
            return (
                user32.GetSystemMetricsForDpi(SM_CXFRAME, dpi) + pad,
                user32.GetSystemMetricsForDpi(SM_CYFRAME, dpi) + pad,
            )
        pad = user32.GetSystemMetrics(SM_CXPADDEDBORDER)
        return (
            user32.GetSystemMetrics(SM_CXFRAME) + pad,
            user32.GetSystemMetrics(SM_CYFRAME) + pad,
        )
    except Exception:
        return 8, 8


def _loword(value: int) -> int:
    """Low 16 bits of an LPARAM as a signed coordinate.

    Screen coordinates go negative on a monitor left of or above the
    primary one, and reading them unsigned puts the cursor 65000 pixels
    away from wherever it actually is.
    """
    word = value & 0xFFFF
    return word - 0x10000 if word & 0x8000 else word


def _hiword(value: int) -> int:
    word = (value >> 16) & 0xFFFF
    return word - 0x10000 if word & 0x8000 else word


def _work_area_for(hwnd) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) of the work area of the window's monitor."""
    try:
        hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if hmon and user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            r = mi.rcWork
            return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    return 0, 0, 1280, 800
