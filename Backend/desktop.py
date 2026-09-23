"""Dannify desktop launcher.

Wraps the FastAPI backend + built Vue frontend in a native window
(Edge WebView2 via pywebview). Designed for PyInstaller freezing.

Engineering notes: the things that make this robust:

* **No port collisions, ever.** We try a preferred high port first
  (42810: outside every common dev/server range) and verify it is
  actually bindable. If *anything* already owns it, we fall back to an
  OS-assigned ephemeral port (bind to port 0), which the kernel
  guarantees is free. The WebView is pointed at whatever port won.

* **Single instance.** A Windows named mutex (``Local\\DannifyAppMutex``)
  ensures double-launching focuses the existing window instead of
  spawning a second server. The live port + PID are written to
  ``%LOCALAPPDATA%/Dannify/instance.json`` so a second launch can find
  the running window even while its title shows the current song.

* **Instant launch.** The native window appears immediately with an
  embedded splash screen (zero network, inline HTML) while uvicorn
  boots on a daemon thread. A health poll (~50ms interval) swaps the
  splash for the real UI the moment the server answers.

* **A real desktop window.** The Windows caption is replaced by the
  app's own title bar, but the window keeps its native frame styles, so
  Aero Snap, Win+arrow snapping, the resize borders, the shadow, Win11
  rounded corners and the min/max animations all stay native (see
  ``_CustomFrame``). Dragging and edge-resizing are handed to Windows'
  own move/size loop. Taskbar thumbnail buttons (prev / play / next),
  taskbar download progress, "Show in folder", a mini player and
  persistent WebView storage round it off.

* **Clean shutdown.** Closing the window flips ``server.should_exit``;
  uvicorn drains connections and the process exits. No orphans.
"""

from __future__ import annotations

import ctypes
import json
import os
import secrets
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from ctypes import wintypes
from pathlib import Path
from typing import Optional

# The shell's own diagnostics. loguru's logger is a singleton, so this is the
# same sink main.py configures; importing it here is not a second logger.
from loguru import logger

# ---------------------------------------------------------------------------
# Paths / environment: must be set BEFORE importing main (it reads env at
# import time for DOWNLOAD_DIR / DATABASE_DIR defaults).
# ---------------------------------------------------------------------------
_FROZEN = bool(getattr(sys, 'frozen', False))
# A second copy (a developer running from source, a test build) must not
# share this folder: WebView2 refuses to open the same user-data folder twice
# with different options and the whole window fails with ERROR_INVALID_STATE.
_DATA_DIR = Path(
    os.getenv('DANNIFY_DATA_DIR')
    or (
        Path(os.getenv('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
        / 'Dannify'
    )
)
_DATA_DIR.mkdir(parents=True, exist_ok=True)
# Desktop builds log to a rotating file (there is no console window).
os.environ.setdefault('DANNIFY_LOG_FILE', str(_DATA_DIR / 'dannify.log'))

# No fixed port: a well-known one is a signature anybody can look for, and
# the window finds its own server through instance.json anyway.
PREFERRED_PORT = 0
# Loopback only unless the user deliberately shares. Binding 0.0.0.0 put the
# whole API and library on the LAN for anyone who guessed the port.
LAN_ENABLED = os.environ.get('DANNIFY_LAN', '').strip().lower() in ('1', 'true', 'yes')
BIND_HOST = '0.0.0.0' if LAN_ENABLED else '127.0.0.1'
APP_TITLE = 'Dannify'
# Windows groups taskbar buttons, jump lists and the now-playing overlay by
# Application User Model ID. A process that never sets one is filed under
# whatever host binary is playing the audio, which is why the media flyout
# said "Unknown app" instead of the name. Must match the AppUserModelID the
# installer writes on the Start Menu shortcut, or Windows treats the running
# app and its shortcut as two different programs.
APP_USER_MODEL_ID = 'Dannify.Player'

# An installer that has been downloaded and is waiting for the app to close.
# Applied by _apply_staged_update() on the way out.
_staged_update: Optional[Path] = None
_INSTANCE_FILE = _DATA_DIR / 'instance.json'
_WINDOW_STATE_FILE = _DATA_DIR / 'window.json'
_WEBVIEW_STORAGE = _DATA_DIR / 'WebView2'
# The sign-in window runs its own WebView2 profile (see _LoginWindow).
_LOGIN_STORAGE = _DATA_DIR / 'SignIn'
DEFAULT_W, DEFAULT_H = 1320, 860
# Below this the desktop layout would collapse into the phone layout.
MIN_W, MIN_H = 760, 540
MINI_W, MINI_H = 420, 124

_THEME_BG = {'dark': '#08080a', 'light': '#e7e9ed'}

# Google's login refuses "embedded browser" user agents, so the sign-in
# window reports plain desktop Chrome (the same string ytmusicapi sends).
_LOGIN_URL = (
    'https://accounts.google.com/ServiceLogin'
    '?service=youtube&continue=https%3A%2F%2Fmusic.youtube.com%2F'
)
_SIGNED_IN_HOSTS = ('music.youtube.com', 'www.youtube.com')
ORIGIN = 'https://music.youtube.com'


def _asset(name: str) -> Path:
    """Locate a bundled asset in both frozen and source checkouts."""
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    candidate = base / 'assets' / name
    if candidate.exists():
        return candidate
    return Path(__file__).resolve().parent / 'assets' / name


# ---------------------------------------------------------------------------
# HARD RULE: no child process may ever open a console window.
#
# The desktop build is windowed (no console). Without this, every spawned
# ffmpeg/ffprobe/yt-dlp helper pops a visible terminal window on Windows
# Windows Terminal (the Win11 default host) IGNORES the polite
# STARTF_USESHOWWINDOW/SW_HIDE hint, so the only reliable switch is the
# CREATE_NO_WINDOW creation flag. We patch subprocess.Popen globally so the
# whole process tree (our code AND third-party libs) is covered. This also
# removes the conhost-spawn + focus-steal latency on every play.
# ---------------------------------------------------------------------------
if os.name == 'nt':
    import subprocess as _sp

    _ORIG_POPEN_INIT = _sp.Popen.__init__

    def _no_window_popen_init(self, *args, **kwargs):  # noqa: ANN001
        kwargs['creationflags'] = (
            kwargs.get('creationflags', 0) | _sp.CREATE_NO_WINDOW
        )
        return _ORIG_POPEN_INIT(self, *args, **kwargs)

    _sp.Popen.__init__ = _no_window_popen_init


def logger_print(*args) -> None:  # noqa: D401, ANN001
    """Append a line to the rotating log even before backend logging is wired."""
    try:
        with open(_DATA_DIR / 'dannify.log', 'a', encoding='utf-8') as f:
            f.write('[desktop] ' + ' '.join(str(a) for a in args) + '\n')
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Persisted window preferences (geometry, theme, title-bar style, mini pos)
# ---------------------------------------------------------------------------
def _read_prefs() -> dict:
    try:
        data = json.loads(_WINDOW_STATE_FILE.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_prefs(patch: dict) -> None:
    try:
        data = _read_prefs()
        data.update(patch)
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _WINDOW_STATE_FILE.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(data), encoding='utf-8')
        tmp.replace(_WINDOW_STATE_FILE)
    except Exception:
        pass


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
    _proto(user32.IsZoomed, wintypes.BOOL, HWND)
    _proto(user32.IsIconic, wintypes.BOOL, HWND)
    _proto(user32.IsWindowVisible, wintypes.BOOL, HWND)
    _proto(user32.GetCursorPos, wintypes.BOOL, ctypes.POINTER(POINT))
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
    def __init__(self, hwnd: int, on_command=None, on_taskbar_created=None):
        self.hwnd = hwnd
        self.installed = False
        self._on_command = on_command
        self._on_taskbar_created = on_taskbar_created
        self._taskbar_msg = 0
        self._proc = None
        self._comctl = None

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
                    if msg == WM_COMMAND and (wparam >> 16) & 0xFFFF == THBN_CLICKED:
                        if self._on_command:
                            self._on_command(wparam & 0xFFFF)
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
        self._ptr = ctypes.c_void_p()
        self._buttons_added = False

    def dispose(self) -> None:
        for handle in self._icons.values():
            try:
                user32.DestroyIcon(handle)
            except Exception:
                pass
        self._icons = {}


# ---------------------------------------------------------------------------
# Notification-area icon.
#
# Dannify keeps playing when its window is gone, so the tray icon is a real
# control surface, not a decoration: it shows what's playing, exposes
# transport controls, and is the only way back to a window that was closed
# to tray. Double-click restores, middle-click plays/pauses.
# ---------------------------------------------------------------------------
# --- Tray menu appearance -------------------------------------------------
#
# WinForms draws menus the way Windows 7 did: a hard 3D border, a grey image
# gutter, and a blue selection bar. Next to Windows 11's own tray menus that
# reads as a broken or very old application, which is exactly what it looked
# like. These two helpers give it flat modern colours and rounded corners.

# DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND. Ignored before Windows 11.
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2


def _round_window_corners(hwnd: int) -> None:
    if not _WIN or not hwnd:
        return
    try:
        value = ctypes.c_int(_DWMWCP_ROUND)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(_DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        logger.opt(exception=True).debug('could not round the menu corners')


_TRAY_RENDERER_CACHE: dict = {}


def _tray_renderer(dark: bool):
    """A flat renderer with Windows 11 selection colours.

    Cached per theme: a renderer holds no per-menu state, and building the
    .NET subclass on every menu rebuild is wasted work.
    """

    cached = _TRAY_RENDERER_CACHE.get(dark)
    if cached is not None:
        return cached

    from System.Drawing import Color, SolidBrush, Rectangle
    from System.Drawing.Drawing2D import SmoothingMode
    from System.Windows.Forms import (
        ProfessionalColorTable,
        ToolStripProfessionalRenderer,
    )

    surface = (
        Color.FromArgb(255, 44, 44, 47) if dark else Color.FromArgb(255, 249, 249, 249)
    )
    hover = (
        Color.FromArgb(255, 60, 60, 64) if dark else Color.FromArgb(255, 236, 236, 238)
    )
    line = (
        Color.FromArgb(255, 62, 62, 66) if dark else Color.FromArgb(255, 226, 226, 229)
    )

    class _Colors(ProfessionalColorTable):
        @property
        def MenuItemSelected(self):  # noqa: N802
            return hover

        @property
        def MenuItemSelectedGradientBegin(self):  # noqa: N802
            return hover

        @property
        def MenuItemSelectedGradientEnd(self):  # noqa: N802
            return hover

        @property
        def MenuItemBorder(self):  # noqa: N802
            return hover

        @property
        def MenuBorder(self):  # noqa: N802
            return line

        @property
        def ToolStripDropDownBackground(self):  # noqa: N802
            return surface

        @property
        def ImageMarginGradientBegin(self):  # noqa: N802
            return surface

        @property
        def ImageMarginGradientMiddle(self):  # noqa: N802
            return surface

        @property
        def ImageMarginGradientEnd(self):  # noqa: N802
            return surface

        @property
        def SeparatorDark(self):  # noqa: N802
            return line

        @property
        def SeparatorLight(self):  # noqa: N802
            return surface

    class _Renderer(ToolStripProfessionalRenderer):
        def __init__(self):
            super().__init__(_Colors())
            self.RoundedEdges = False

        def OnRenderMenuItemBackground(self, e):  # noqa: N802, ANN001
            """Rounded selection pill rather than a full-width bar."""

            if not e.Item.Selected or not e.Item.Enabled:
                return
            g = e.Graphics
            g.SmoothingMode = SmoothingMode.AntiAlias
            rect = Rectangle(
                3, 0, e.Item.Width - 6, e.Item.Height
            )
            brush = SolidBrush(hover)
            try:
                g.FillRectangle(brush, rect)
            finally:
                brush.Dispose()

        def OnRenderSeparator(self, e):  # noqa: N802, ANN001
            g = e.Graphics
            brush = SolidBrush(line)
            try:
                g.FillRectangle(
                    brush, Rectangle(8, e.Item.Height // 2, e.Item.Width - 16, 1)
                )
            finally:
                brush.Dispose()

    renderer = _Renderer()
    _TRAY_RENDERER_CACHE[dark] = renderer
    return renderer


class _Tray:
    LABEL_KEYS = ('nowPlaying', 'play', 'pause', 'prev', 'next', 'show', 'quit', 'hidden')

    def __init__(self, api: 'DesktopApi'):
        self._api = api
        self._icon = None  # WinForms.NotifyIcon
        self._items: dict[str, object] = {}
        self._track = ''
        self._playing = False
        self._has_track = False
        self._told_user = False
        self.labels = {
            'nowPlaying': 'Nothing playing',
            'play': 'Play',
            'pause': 'Pause',
            'prev': 'Previous',
            'next': 'Next',
            'show': 'Open Dannify',
            'quit': 'Quit Dannify',
            'hidden': 'Dannify is still playing here.',
        }

    @property
    def available(self) -> bool:
        return self._icon is not None

    def install(self) -> bool:
        """UI thread only. Safe to call twice."""
        if self._icon is not None:
            return True
        try:
            from System import EventHandler
            from System.Windows.Forms import (
                MouseButtons,
                MouseEventHandler,
                NotifyIcon,
                ToolStripMenuItem,
                ToolStripSeparator,
            )

            menu = self._build_menu(ToolStripMenuItem, ToolStripSeparator, EventHandler)
            icon = NotifyIcon()
            icon.Icon = _app_icon()
            icon.Text = APP_TITLE
            icon.ContextMenuStrip = menu
            icon.DoubleClick += EventHandler(lambda s, e: self._api._show_from_tray())
            icon.MouseUp += MouseEventHandler(
                lambda s, e: self._api._media('toggle')
                if e.Button == MouseButtons.Middle
                else None
            )
            icon.Visible = True
            self._icon = icon
            return True
        except Exception as exc:
            logger_print('tray icon unavailable:', exc)
            return False

    def _build_menu(self, MenuItem, Separator, EventHandler):  # noqa: N803, ANN001
        """A menu that looks like it belongs in Windows 11.

        Dark or light to match the system, a comfortable row height, the
        track title on top in bold, and "Open Dannify" as the default item
        so a plain click on the icon does the obvious thing.
        """
        from System.Drawing import Color, Font, FontStyle, SystemFonts
        from System.Windows.Forms import (
            ContextMenuStrip,
            ToolStripDropDownDirection,
        )

        dark = not _system_uses_light_theme()
        # Windows 11's own menu surface, not the WinForms grey.
        if dark:
            fg = Color.FromArgb(255, 239, 240, 243)
            bg = Color.FromArgb(255, 44, 44, 47)
            dim = Color.FromArgb(255, 158, 159, 166)
        else:
            fg = Color.FromArgb(255, 26, 28, 32)
            bg = Color.FromArgb(255, 249, 249, 249)
            dim = Color.FromArgb(255, 105, 107, 113)

        menu = ContextMenuStrip()
        menu.Renderer = _tray_renderer(dark)
        menu.ShowImageMargin = False
        menu.DropDownDirection = ToolStripDropDownDirection.AboveLeft
        menu.BackColor = bg
        menu.ForeColor = fg
        # Breathing room around the block of items, the way Windows 11 menus
        # sit off their own edges.
        menu.Padding = _padding(4, 6, 4, 6)
        try:
            base = SystemFonts.MenuFont
            menu.Font = Font(base.FontFamily, 9.75)
        except Exception:
            base = None

        # Rounded corners, once the dropdown actually has a window handle.
        def _round(sender, event):  # noqa: ANN001
            try:
                _round_window_corners(int(menu.Handle.ToInt64()))
            except Exception:
                pass

        menu.HandleCreated += EventHandler(_round)

        def item(key, handler=None, bold=False, header=False):
            entry = MenuItem(self.labels[key])
            entry.ForeColor = dim if header else fg
            entry.BackColor = bg
            # 32px rows: Windows 11 menu metrics, and a tray menu is clicked
            # in a hurry.
            entry.Padding = _padding(6, 5, 6, 5)
            if handler is not None:
                entry.Click += EventHandler(lambda s, e: handler())
            else:
                entry.Enabled = False
                entry.ForeColor = dim
            if base is not None:
                entry.Font = Font(
                    base.FontFamily,
                    9.0 if header else 9.75,
                    FontStyle.Bold if bold else FontStyle.Regular,
                )
            self._items[key] = entry
            return entry

        # The header is the track, not a command: smaller, dimmer, and it
        # does not pretend to be a disabled menu item you failed to click.
        menu.Items.Add(item('nowPlaying', None, header=True))
        menu.Items.Add(Separator())
        menu.Items.Add(item('play', lambda: self._api._media('toggle')))
        menu.Items.Add(item('prev', lambda: self._api._media('prev')))
        menu.Items.Add(item('next', lambda: self._api._media('next')))
        menu.Items.Add(Separator())
        menu.Items.Add(item('show', self._api._show_from_tray, bold=True))
        menu.Items.Add(item('quit', self._api._quit))
        return menu

    def apply_labels(self, labels: dict) -> None:
        for key in self.LABEL_KEYS:
            value = labels.get(key)
            if isinstance(value, str) and value:
                self.labels[key] = value[:80]
        self.refresh()

    def set_track(self, title: str, artist: str, playing: bool, has_track: bool) -> None:
        self._track = f'{title}: {artist}' if title and artist else (title or '')
        self._playing = playing
        self._has_track = has_track
        self.refresh()

    def refresh(self) -> None:
        if self._icon is None:
            return
        try:
            label = self._track or self.labels['nowPlaying']
            self._icon.Text = f'{APP_TITLE}\n{label}'[:127]
            for key in ('nowPlaying', 'play', 'prev', 'next', 'show', 'quit'):
                entry = self._items.get(key)
                if entry is None:
                    continue
                if key == 'nowPlaying':
                    entry.Text = label
                elif key == 'play':
                    entry.Text = self.labels['pause' if self._playing else 'play']
                    entry.Enabled = self._has_track
                elif key in ('prev', 'next'):
                    entry.Enabled = self._has_track
                else:
                    entry.Text = self.labels[key]
        except Exception:
            pass

    def notify_hidden(self) -> None:
        """One balloon, the first time the window vanishes into the tray."""
        if self._icon is None or self._told_user:
            return
        self._told_user = True
        try:
            from System.Windows.Forms import ToolTipIcon

            self._icon.BalloonTipIcon = ToolTipIcon.Info
            self._icon.BalloonTipTitle = APP_TITLE
            self._icon.BalloonTipText = self.labels['hidden']
            self._icon.ShowBalloonTip(4000)
        except Exception:
            pass

    def dispose(self) -> None:
        icon, self._icon = self._icon, None
        if icon is None:
            return
        try:
            icon.Visible = False
            icon.Dispose()
        except Exception:
            pass


def _padding(left: int, top: int, right: int, bottom: int):
    from System.Windows.Forms import Padding

    return Padding(left, top, right, bottom)


def _system_uses_light_theme() -> bool:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize',
        ) as key:
            return winreg.QueryValueEx(key, 'SystemUsesLightTheme')[0] == 1
    except Exception:
        return False


_APP_ICON = None


def _app_icon():
    """The window / tray icon, loaded once (System.Drawing.Icon)."""
    global _APP_ICON
    if _APP_ICON is None:
        from System.Drawing import Icon, SystemIcons

        path = _asset('dannify.ico')
        try:
            _APP_ICON = Icon(str(path))
        except Exception as exc:
            logger_print('app icon unavailable:', exc)
            _APP_ICON = SystemIcons.Application
    return _APP_ICON


# ---------------------------------------------------------------------------
# JS API: exposed to the page as window.pywebview.api.*
# (Attributes starting with "_" are private and not exposed.)
# ---------------------------------------------------------------------------
class DesktopApi:
    def __init__(self, native_frame_pref: bool, prefs: dict | None = None):
        prefs = prefs or {}
        self._window = None
        self._form = None
        self._hwnd = 0
        self._frame: _CustomFrame | None = None
        self._taskbar: _Taskbar | None = None
        self._tray: _Tray | None = None
        self._native_frame_pref = native_frame_pref
        self._native_frame = native_frame_pref
        self._fullscreen = False
        self._mini = False
        self._pre_mini: dict | None = None
        self._on_top = False
        self._theme = 'dark'
        # On by default: closing the window on a music player is
        # 'get out of my way', not 'stop the music'. Settings can turn
        # it off, and that choice is remembered.
        self._close_to_tray = bool(prefs.get('close_to_tray', True))
        self._minimize_to_tray = bool(prefs.get('minimize_to_tray', False))
        self._hidden = False
        # Set while the user is genuinely quitting, so close-to-tray steps aside.
        self._quitting = False
        self._login = None  # the Google sign-in window, while it is open
        self._launch_geometry: tuple[int, int, int, int] | None = None
        # Once the window starts closing, calling into it (Invoke/evaluate_js)
        # raises from a destroyed handle: stop talking to it.
        self._closing = False

    # --- wiring (called from Python, not JS) -------------------------------
    def _attach(self, window) -> None:  # noqa: ANN001
        """Runs on the UI thread from pywebview's before_show event."""
        self._window = window
        self._form = window.native
        try:
            self._hwnd = int(self._form.Handle.ToInt64())
        except Exception:
            self._hwnd = 0
        try:
            self._form.Icon = _app_icon()
        except Exception:
            pass
        if not (_WIN and self._hwnd):
            return
        self._taskbar = _Taskbar(self._hwnd)
        self._tray = _Tray(self)
        if self._close_to_tray or self._minimize_to_tray:
            self._tray.install()
        self._frame = _CustomFrame(
            self._hwnd,
            on_command=self._on_thumb_button,
            on_taskbar_created=self._on_taskbar_created,
        )
        if self._native_frame_pref:
            # Keep the Windows caption; the subclass is still needed for the
            # taskbar buttons, so install it without reclaiming the caption.
            self._frame._nccalcsize = lambda hwnd, msg, w, l: self._frame._comctl.DefSubclassProc(hwnd, msg, w, l)  # noqa: E731
        ok = self._frame.install()
        self._native_frame = self._native_frame_pref or not ok

    def _ui(self, fn, wait: bool = False):  # noqa: ANN001
        """Run *fn* on the window's UI thread."""
        form = self._form
        if form is None or self._closing:
            return None
        from System import Action

        result = []

        def run():
            try:
                result.append(fn())
            except Exception as exc:  # never let an exception cross into .NET
                logger_print('ui call failed:', exc)

        try:
            if not form.InvokeRequired:
                run()
            elif wait:
                form.Invoke(Action(run))
            else:
                form.BeginInvoke(Action(run))
        except Exception as exc:
            logger_print('invoke failed:', exc)
        return result[0] if result else None

    def _push_state(self) -> None:
        if self._window is None or self._closing:
            return
        state = json.dumps(self.win_state())
        threading.Thread(
            target=self._eval,
            args=(f'window.__dannifyWindowState && window.__dannifyWindowState({state})',),
            daemon=True,
        ).start()

    def _eval(self, script: str) -> None:
        if self._closing:
            return
        try:
            self._window.evaluate_js(script)
        except Exception:
            pass

    def _media(self, cmd: str) -> None:
        """Drive playback from a native control (taskbar button, tray menu)."""
        # Never evaluate_js on the UI thread: it waits for the UI thread.
        threading.Thread(
            target=self._eval,
            args=(f"window.__dannifyMedia && window.__dannifyMedia('{cmd}')",),
            daemon=True,
        ).start()

    def _on_thumb_button(self, button_id: int) -> None:
        cmd = {BTN_PREV: 'prev', BTN_PLAY: 'toggle', BTN_NEXT: 'next'}.get(button_id)
        if cmd:
            self._media(cmd)

    def _on_taskbar_created(self) -> None:
        if self._taskbar is not None:
            try:
                self._taskbar.reset()
                self._taskbar.add_buttons()
            except Exception as exc:
                logger_print('taskbar buttons unavailable:', exc)

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
            'maximized': bool(hwnd and user32.IsZoomed(hwnd)) and not self._fullscreen,
            'minimized': bool(hwnd and user32.IsIconic(hwnd)),
            'fullscreen': self._fullscreen,
            'mini': self._mini,
            'onTop': self._on_top,
            'nativeFrame': self._native_frame,
            'nativeFramePref': self._native_frame_pref,
            'closeToTray': self._close_to_tray,
            'minimizeToTray': self._minimize_to_tray,
        }

    def win_minimize(self) -> None:
        self._post(WM_SYSCOMMAND, SC_MINIMIZE)

    def win_toggle_maximize(self) -> None:
        if self._fullscreen or self._mini or not self._hwnd:
            return
        self._post(WM_SYSCOMMAND, SC_RESTORE if user32.IsZoomed(self._hwnd) else SC_MAXIMIZE)

    def win_close(self) -> None:
        self._post(WM_SYSCOMMAND, SC_CLOSE)

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
                    _write_prefs({'mini_pos': [round(rect.left / scale), round(rect.top / scale)]})
                form.TopMost = False
                form.MinimumSize = Size(int(MIN_W * scale), int(MIN_H * scale))
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

    def win_set_zoom(self, factor: float) -> None:
        try:
            value = max(0.5, min(2.0, float(factor)))
        except (TypeError, ValueError):
            return

        def apply():
            self._form.browser.webview.ZoomFactor = value

        self._ui(apply)

    def win_set_native_frame(self, on: bool) -> dict:
        self._native_frame_pref = bool(on)
        _write_prefs({'native_frame': self._native_frame_pref})
        return self.win_state()

    # --- tray ---------------------------------------------------------------
    def tray_set(self, options: dict) -> dict:
        """Enable/disable close-to-tray and minimize-to-tray."""
        if not isinstance(options, dict):
            return self.win_state()
        if 'closeToTray' in options:
            self._close_to_tray = bool(options['closeToTray'])
            _write_prefs({'close_to_tray': self._close_to_tray})
        if 'minimizeToTray' in options:
            self._minimize_to_tray = bool(options['minimizeToTray'])
            _write_prefs({'minimize_to_tray': self._minimize_to_tray})
        if self._tray is not None:
            wanted = self._close_to_tray or self._minimize_to_tray
            if wanted and not self._tray.available:
                self._ui(self._tray.install, wait=True)
            elif not wanted and self._tray.available and not self._hidden:
                self._ui(self._tray.dispose, wait=True)
        self._push_state()
        return self.win_state()

    def tray_labels(self, labels: dict) -> None:
        """Localized strings for the tray menu (pushed by the frontend)."""
        if self._tray is not None and isinstance(labels, dict):
            self._ui(lambda: self._tray.apply_labels(labels))

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
            if self._tray is not None and not (self._close_to_tray or self._minimize_to_tray):
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

    def app_restart(self) -> bool:
        """Relaunch Dannify (used by the 'restart to apply' prompt)."""
        try:
            import subprocess

            env = dict(os.environ)
            env['DANNIFY_WAIT_PID'] = str(os.getpid())
            if _FROZEN:
                cmd = [sys.executable, *sys.argv[1:]]
            else:
                cmd = [sys.executable, os.path.abspath(__file__), *sys.argv[1:]]
            subprocess.Popen(cmd, env=env, close_fds=True, cwd=os.getcwd())
        except Exception as exc:
            logger_print('restart failed:', exc)
            return False
        threading.Timer(0.25, self._quit).start()
        return True

    @staticmethod
    def _vetted_installer(installer: str) -> Optional[Path]:
        """The path, but only if it is an installer we put there ourselves.

        Nothing outside our own updates folder is ever run, whatever the UI
        asks for: this is a path arriving from JavaScript.
        """

        try:
            path = Path(str(installer or '')).resolve()
            path.relative_to((_DATA_DIR / 'updates').resolve())
            if path.suffix.lower() != '.exe' or not path.is_file():
                return None
            return path
        except Exception:
            return None

    def app_install_update(self, installer: str) -> bool:
        """Run a downloaded installer and step out of its way."""
        path = self._vetted_installer(installer)
        if path is None:
            return False
        try:
            os.startfile(str(path))  # noqa: S606
        except Exception as exc:
            logger_print('could not launch installer:', exc)
            return False
        threading.Timer(0.4, self._quit).start()
        return True

    def app_stage_update(self, installer: str) -> bool:
        """Hold an installer to apply when the app next closes.

        The point of this is that nobody has to decide anything. An update
        downloads quietly, the user is told it is ready, and if they never
        press restart it goes in the next time they close the window: the
        way a browser does it.
        """

        global _staged_update
        path = self._vetted_installer(installer)
        if path is None:
            return False
        _staged_update = path
        logger.info('Update staged for the next exit: {}', path.name)
        return True

    def app_clear_staged_update(self) -> bool:
        global _staged_update
        _staged_update = None
        return True

    # --- YouTube Music account ----------------------------------------------
    def account_sign_in(self) -> dict:
        """Show the Google sign-in window and keep the resulting session.

        Runs on the JS-bridge worker thread, so blocking here is fine: the
        window has its own UI thread (see _LoginWindow) and the app stays
        responsive throughout.
        """
        if not _WIN:
            return {'signed_in': False, 'error': 'Sign-in needs the desktop app'}
        if self._login is not None:
            return {'signed_in': False, 'error': ''}

        from dannify import account

        login = _LoginWindow(self._theme)
        self._login = login
        try:
            cookies = login.run()
        finally:
            self._login = None
        if not cookies:
            # No cookies means the user closed the window, or WebView2 failed.
            return {'signed_in': False, 'error': login.error}
        try:
            return account.sign_in(cookies)
        except Exception as exc:
            logger_print('sign-in rejected:', exc)
            return {'signed_in': False, 'error': str(exc)}

    def account_clear_session(self) -> bool:
        """Forget the Google session so the next sign-in starts clean."""
        import shutil

        try:
            shutil.rmtree(_LOGIN_STORAGE, ignore_errors=True)
            return True
        except Exception as exc:
            logger_print('could not clear the sign-in profile:', exc)
            return False

    # --- app / shell --------------------------------------------------------
    def app_set_theme(self, theme: str) -> None:
        theme = 'light' if theme == 'light' else 'dark'
        if theme == self._theme and _read_prefs().get('theme') == theme:
            return
        self._theme = theme
        _write_prefs({'theme': theme})
        hwnd = self._hwnd
        bg = _THEME_BG[theme]

        def apply():
            from System.Drawing import ColorTranslator

            color = ColorTranslator.FromHtml(bg)
            self._form.BackColor = color
            try:
                self._form.browser.webview.DefaultBackgroundColor = color
            except Exception:
                pass
            if hwnd:
                value = ctypes.c_int(1 if theme == 'dark' else 0)
                dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
                )

        self._ui(apply)

    def shell_reveal(self, rel_path: str) -> bool:
        """Open Explorer with the file selected (paths confined to the library)."""
        target = _library_path(rel_path)
        if target is None or not target.exists():
            return False
        try:
            ole32.CoInitializeEx(None, 0x2)  # apartment-threaded, per worker thread
            pidl = ctypes.c_void_p()
            if shell32.SHParseDisplayName(str(target), None, ctypes.byref(pidl), 0, None) == 0:
                shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0)
                ole32.CoTaskMemFree(pidl)
                return True
        except Exception:
            pass
        try:
            import subprocess

            subprocess.Popen(f'explorer /select,"{target}"')
            return True
        except Exception:
            return False

    def shell_open_library(self) -> bool:
        base = _library_path('')
        if base is None:
            return False
        try:
            os.startfile(str(base))  # noqa: S606
            return True
        except Exception:
            return False

    def shell_open_external(self, url: str) -> bool:
        url = str(url or '')
        if not url.startswith(('https://', 'http://')):
            return False
        return bool(webbrowser.open(url))

    def clipboard_read(self) -> str:
        if not _WIN or not user32.OpenClipboard(None):
            return ''
        try:
            handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
            if not handle:
                return ''
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ''
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    # --- taskbar ------------------------------------------------------------
    def taskbar_progress(self, value: float, mode: str = 'normal') -> None:
        if self._taskbar is None:
            return
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        self._ui(lambda: self._taskbar.set_progress(value, str(mode)))

    def taskbar_playback(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        playing = bool(payload.get('playing'))
        has_track = bool(payload.get('hasTrack'))
        title = str(payload.get('title') or '')[:120]
        artist = str(payload.get('artist') or '')[:120]
        labels = payload.get('labels')

        def apply():
            tb = self._taskbar
            if tb is not None:
                if isinstance(labels, dict):
                    tb.labels.update({k: str(v)[:60] for k, v in labels.items() if k in tb.labels})
                tb.playing = playing
                tb.has_track = has_track
                tb.update_buttons()
            if self._tray is not None:
                self._tray.set_track(title, artist, playing, has_track)
            # Like other players: the window title shows what's playing.
            if self._form is not None:
                if playing and title:
                    self._form.Text = f'{artist} - {title}' if artist else title
                else:
                    self._form.Text = APP_TITLE

        self._ui(apply)


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


def _library_path(rel_path: str) -> Path | None:
    """Resolve *rel_path* inside the live library folder (no escaping it)."""
    try:
        from dannify import api as _api

        base = Path(_api.state.download_dir).resolve()
    except Exception:
        return None
    if not rel_path:
        return base
    try:
        target = (base / rel_path).resolve()
        target.relative_to(base)
        return target
    except (ValueError, RuntimeError, OSError):
        return None


def _current_placement(hwnd) -> dict:
    """Restored (non-maximized) bounds in logical px + maximized flag."""
    scale = _window_scale(hwnd)
    wp = WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(WINDOWPLACEMENT)
    maximized = bool(user32.IsZoomed(hwnd))
    rect = RECT()
    if maximized and user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
        # rcNormalPosition is in work-area coordinates.
        left, top, _, _ = _work_area_for(hwnd)
        hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        dx = dy = 0
        if hmon and user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            dx, dy = left - mi.rcMonitor.left, top - mi.rcMonitor.top
        r = wp.rcNormalPosition
        rect.left, rect.top = r.left + dx, r.top + dy
        rect.right, rect.bottom = r.right + dx, r.bottom + dy
    else:
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return {
        'x': round(rect.left / scale),
        'y': round(rect.top / scale),
        'w': round((rect.right - rect.left) / scale),
        'h': round((rect.bottom - rect.top) / scale),
        'maximized': maximized,
    }


# ---------------------------------------------------------------------------
# Splash (instant paint while the server boots). It has its own tiny title
# bar so the window can be moved/closed before the app has loaded.
# ---------------------------------------------------------------------------
def _splash_html(theme: str, native_frame: bool, body: str = '') -> str:
    dark = theme != 'light'
    bg = _THEME_BG['dark' if dark else 'light']
    fg = '#e7e7ef' if dark else '#16181c'
    muted = '#8a8a98' if dark else '#6b6f78'
    track = '#23232e' if dark else '#d5d8de'
    content = body or (
        "<div class='logo'>Dan<span>nify</span></div>"
        "<div class='bar'></div>"
        "<div class='hint'>Starting your music…</div>"
    )
    controls = '' if native_frame else (
        "<div class='caption' onmousedown='drag(event)' ondblclick='api(\"win_toggle_maximize\")'>"
        "<button onclick='api(\"win_minimize\")' title='Minimize'>&#xE921;</button>"
        "<button onclick='api(\"win_close\")' class='close' title='Close'>&#xE8BB;</button>"
        '</div>'
    )
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><style>
  html,body{{margin:0;height:100%;background:{bg};color:{fg};overflow:hidden;
    font-family:'Segoe UI Variable Text','Segoe UI',system-ui,sans-serif;
    user-select:none;cursor:default}}
  .caption{{position:fixed;top:0;left:0;right:0;height:44px;display:flex;
    justify-content:flex-end}}
  .caption button{{width:46px;height:44px;border:0;background:transparent;
    color:{fg};font-family:'Segoe Fluent Icons','Segoe MDL2 Assets';font-size:10px}}
  .caption button:hover{{background:rgba(128,128,128,.18)}}
  .caption .close:hover{{background:#c42b1c;color:#fff}}
  .wrap{{height:100%;display:flex;flex-direction:column;align-items:center;
    justify-content:center;text-align:center;animation:fade .45s ease}}
  .logo{{font-size:44px;font-weight:800;letter-spacing:-1px}}
  .logo span{{color:#1db954}}
  .bar{{margin:26px auto 0;width:180px;height:3px;border-radius:99px;
    background:{track};overflow:hidden;position:relative}}
  .bar::after{{content:'';position:absolute;left:-40%;top:0;height:100%;
    width:40%;border-radius:99px;background:#1db954;
    animation:slide 1s cubic-bezier(.4,0,.2,1) infinite}}
  .hint{{margin-top:14px;font-size:12px;color:{muted}}}
  code{{font-size:12px;color:{muted}}}
  @keyframes slide{{to{{left:100%}}}}
  @keyframes fade{{from{{opacity:0;transform:scale(.97)}}to{{opacity:1}}}}
</style></head><body>
  {controls}
  <div class='wrap'>{content}</div>
  <script>
    function api(name){{
      try{{ window.pywebview && window.pywebview.api[name](); }}catch(e){{}}
    }}
    function drag(e){{
      if(e.button!==0||e.target.tagName==='BUTTON'||e.detail>1) return;
      api('win_start_drag');
    }}
  </script>
</body></html>"""


# ---------------------------------------------------------------------------
# Single instance (Windows named mutex)
# ---------------------------------------------------------------------------
def _wait_for_parent_exit() -> None:
    """A relaunch waits for the old process before claiming the mutex."""
    pid = os.environ.pop('DANNIFY_WAIT_PID', '')
    if not (_WIN and pid.isdigit()):
        return
    handle = kernel32.OpenProcess(0x00100000, False, int(pid))  # SYNCHRONIZE
    if not handle:
        return
    try:
        kernel32.WaitForSingleObject(handle, 20000)
    finally:
        kernel32.CloseHandle(handle)


def _acquire_single_instance() -> bool:
    """Return True if we are the first instance; focus the other otherwise.

    ``DANNIFY_INSTANCE`` suffixes the mutex so developers can run a second
    copy side by side (it is never set in shipped builds).
    """
    if not _WIN:
        return True
    _wait_for_parent_exit()
    suffix = os.environ.get('DANNIFY_INSTANCE', '')
    kernel32.CreateMutexW(None, False, f'Local\\DannifyAppMutex{suffix}')
    if ctypes.get_last_error() == 183 or kernel32.GetLastError() == 183:
        _focus_existing_window()
        return False
    return True


def _focus_existing_window() -> None:
    """Bring the running instance forward (its title may be a song name)."""
    try:
        pid = int(json.loads(_INSTANCE_FILE.read_text(encoding='utf-8')).get('pid', 0))
    except Exception:
        pid = 0
    found = []

    def visit(hwnd, _):  # noqa: ANN001
        owner_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if (
            owner_pid.value == pid
            and user32.IsWindowVisible(hwnd)
            and not user32.GetWindow(hwnd, GW_OWNER)
        ):
            found.append(hwnd)
            return False
        return True

    try:
        if pid:
            user32.EnumWindows(_EnumWindowsProc(visit), 0)
        hwnd = found[0] if found else user32.FindWindowW(None, APP_TITLE)
        if hwnd:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Collision-proof port selection
# ---------------------------------------------------------------------------
def _port_is_free(port: int, host: str = BIND_HOST) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            s.bind((host, port))
        return True
    except OSError:
        return False


def _pick_port() -> int:
    """A port the kernel guarantees is free, different on every launch."""
    if PREFERRED_PORT and _port_is_free(PREFERRED_PORT):
        return PREFERRED_PORT
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((BIND_HOST, 0))  # the OS hands us a port nobody owns
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Server thread
# ---------------------------------------------------------------------------
def _start_server(port: int, token: str):
    """Boot uvicorn on a daemon thread; return the Server for shutdown."""
    import asyncio

    import main as backend
    from uvicorn import Config, Server

    # DANNIFY_LOG_LEVEL=debug turns on the detail needed to diagnose a
    # packaged build, where there is no console and no devtools.
    backend._setup_logging(os.environ.get('DANNIFY_LOG_LEVEL', 'info'))
    # Only this window knows the key, so nothing else on the machine can
    # reach the API (see the _require_key middleware in main.py).
    backend.api.state.auth_token = token
    backend._fix_mime_types()
    app = backend.build_app()

    config = Config(
        app=app,
        host=BIND_HOST,  # loopback unless DANNIFY_LAN=1 opts into sharing
        port=port,
        log_level='info',
        log_config=None,
        workers=1,
        # Nothing on this socket should introduce itself. A `server:` header
        # naming the web stack is the clearest possible sign that a desktop
        # app is a web app wearing a window.
        server_header=False,
        date_header=False,
    )
    server = Server(config)

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        _benign = (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)

        def _quiet(loop, context):  # noqa: ANN001
            exc = context.get('exception')
            msg = context.get('message', '')
            if isinstance(exc, _benign) or '_call_connection_lost' in msg:
                return

        loop.set_exception_handler(_quiet)
        try:
            loop.run_until_complete(server.serve())
        except Exception:
            pass
        finally:
            try:
                loop.close()
            except Exception:
                pass

    thread = threading.Thread(target=_run, name='dannify-server', daemon=True)
    thread.start()
    return server


def _wait_until_up(port: int, timeout: float = 30.0, token: str = '') -> bool:
    """Poll until the API answers us.

    Carries the session key like any other request. It used to hit an
    endpoint left open to everyone, which meant a browser pointed at the
    port got a version number back and knew exactly what it had found.
    Nothing is open now, so the probe has to identify itself too.
    """
    url = f'http://127.0.0.1:{port}/api/version'
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(url)
            if token:
                request.add_header('X-Dannify-Key', token)
            with urllib.request.urlopen(request, timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.05)
    return False


def _write_instance_file(port: int) -> None:
    try:
        _INSTANCE_FILE.write_text(
            json.dumps({'port': port, 'pid': os.getpid()}), encoding='utf-8'
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Window geometry: restore last session on the monitor it was on, clamped to
# a visible work area so a saved off-screen position can never strand the
# window where the user can't reach it.
# ---------------------------------------------------------------------------
def _system_scale() -> float:
    try:
        return user32.GetDpiForSystem() / 96.0
    except Exception:
        return 1.0


def _work_area_near(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    """Logical (left, top, width, height) of the monitor nearest a rect."""
    scale = _system_scale()
    try:
        r = RECT(int(x * scale), int(y * scale), int((x + w) * scale), int((y + h) * scale))
        hmon = user32.MonitorFromRect(ctypes.byref(r), MONITOR_DEFAULTTONEAREST)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if hmon and user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            wk = mi.rcWork
            return (
                round(wk.left / scale),
                round(wk.top / scale),
                round((wk.right - wk.left) / scale),
                round((wk.bottom - wk.top) / scale),
            )
    except Exception:
        pass
    return 0, 0, 1280, 800


def _settle(measured: dict, launched: tuple[int, int, int, int] | None) -> dict:
    """Prefer the geometry we launched with when nothing really moved.

    Installing the custom frame makes Windows report a window a few pixels
    taller than the one we created, so writing the measured value back grew
    the window on every run.
    """
    if launched is None or measured.get('maximized'):
        return measured
    lx, ly, lw, lh = launched
    drift = max(
        abs(measured['x'] - lx), abs(measured['y'] - ly),
        abs(measured['w'] - lw), abs(measured['h'] - lh),
    )
    if drift <= 48:  # nobody drags a window by less than this on purpose
        return {'x': lx, 'y': ly, 'w': lw, 'h': lh, 'maximized': False}
    return measured


def _clamp_to_visible(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    left, top, work_w, work_h = _work_area_near(x, y, w, h)
    # Leave a little room: a window sized to the exact work area can still
    # spill its shadow (and on some setups its last row of pixels) past the
    # edge, which is how the player bar ends up under the taskbar.
    w = max(MIN_W, min(w, work_w - 8))
    h = max(MIN_H, min(h, work_h - 8))
    x = max(left, min(x, left + work_w - w))
    y = max(top, min(y, top + work_h - h))
    return x, y, w, h


def _centered_geometry() -> tuple[int, int, int, int]:
    """Default (x, y, w, h): DEFAULT_W × DEFAULT_H centered on the primary work area."""
    left, top, work_w, work_h = _work_area_near(0, 0, 1, 1)
    w = min(DEFAULT_W, max(MIN_W, work_w - 80))
    h = min(DEFAULT_H, max(MIN_H, work_h - 80))
    return left + (work_w - w) // 2, top + (work_h - h) // 2, w, h


def _load_window_state(prefs: dict) -> tuple[int, int, int, int, bool]:
    """Return ``(x, y, w, h, maximized)`` from disk, falling back to centered."""
    if {'x', 'y', 'w', 'h'} <= set(prefs):
        try:
            x, y, w, h = _clamp_to_visible(
                int(prefs['x']), int(prefs['y']), int(prefs['w']), int(prefs['h'])
            )
            return x, y, w, h, bool(prefs.get('maximized', False))
        except Exception:
            logger_print('Could not load window state: using centered defaults')
    x, y, w, h = _centered_geometry()
    return x, y, w, h, False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _claim_app_identity() -> None:
    """Tell Windows who we are, before any window or audio exists.

    Has to happen first: the shell caches the identity on the first window a
    process shows, so setting it later changes nothing.
    """

    if not _WIN:
        return
    try:
        fn = shell32.SetCurrentProcessExplicitAppUserModelID
        fn.argtypes = [ctypes.c_wchar_p]
        fn.restype = ctypes.c_long
        if fn(APP_USER_MODEL_ID) != 0:
            logger.debug('the shell refused our app identity')
    except Exception:
        logger.opt(exception=True).debug('could not set the app identity')


# --- The media flyout's "Unknown app" -------------------------------------
#
# Windows' now-playing flyout names the app that owns the media session. In a
# WebView2 app that is not us: Chromium registers the session from
# msedgewebview2.exe, which has no identity of its own, so Windows shows
# "Unknown app" over our title and artwork. It is a known WebView2 gap that
# Microsoft has acknowledged and not fixed (WebView2Feedback #2236).
#
# There is one lever available. Windows resolves a window's app identity from
# its shell property store before falling back to the process, so stamping
# PKEY_AppUserModel_ID onto the windows Chromium registers from can give the
# session a name. Strictly a best effort: it touches windows we do not own,
# only ever inside our own process tree, and every call is allowed to fail.

_PKEY_APPUSERMODEL_ID_FMTID = '{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}'
_PKEY_APPUSERMODEL_ID_PID = 5
_IID_IPROPERTYSTORE = '{886d8eeb-8cf2-4446-8d02-cdba1dbdcf99}'
# WebView2 builds its windows lazily and rebuilds them when the page
# navigates, so one pass at startup is not enough.
_TAG_DELAYS = (1.5, 5.0, 12.0, 30.0)


class _GUID(ctypes.Structure):
    _fields_ = [
        ('a', ctypes.c_uint32),
        ('b', ctypes.c_uint16),
        ('c', ctypes.c_uint16),
        ('d', ctypes.c_ubyte * 8),
    ]


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [('fmtid', _GUID), ('pid', ctypes.c_ulong)]


class _PROPVARIANT(ctypes.Structure):
    _fields_ = [
        ('vt', ctypes.c_ushort),
        ('r1', ctypes.c_ushort),
        ('r2', ctypes.c_ushort),
        ('r3', ctypes.c_ushort),
        ('data', ctypes.c_byte * 16),
    ]


def _guid(text: str) -> _GUID:
    value = _GUID()
    ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(value))
    return value


def _our_process_tree() -> set[int]:
    """Every pid descended from this one, so we never touch another app's
    WebView2 (the user may well have several running)."""

    import collections

    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ('dwSize', wintypes.DWORD),
            ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD),
            ('th32DefaultHeapID', ctypes.POINTER(ctypes.c_ulong)),
            ('th32ModuleID', wintypes.DWORD),
            ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD),
            ('pcPriClassBase', ctypes.c_long),
            ('dwFlags', wintypes.DWORD),
            ('szExeFile', ctypes.c_char * 260),
        ]

    children: dict[int, list[int]] = collections.defaultdict(list)
    # Without these the returned HANDLE is truncated to 32 bits on a 64-bit
    # build and every snapshot looks like a failure.
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    kernel32.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return {os.getpid()}
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        ok = kernel32.Process32First(snapshot, ctypes.byref(entry))
        while ok:
            children[entry.th32ParentProcessID].append(entry.th32ProcessID)
            ok = kernel32.Process32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)

    mine = {os.getpid()}
    queue = [os.getpid()]
    while queue:
        for child in children.get(queue.pop(), ()):
            if child not in mine:
                mine.add(child)
                queue.append(child)
    return mine


def _stamp_window_identity(hwnd: int) -> bool:
    ptr = ctypes.c_void_p()
    iid = _guid(_IID_IPROPERTYSTORE)
    if shell32.SHGetPropertyStoreForWindow(
        wintypes.HWND(hwnd), ctypes.byref(iid), ctypes.byref(ptr)
    ) != 0 or not ptr:
        return False
    try:
        # VT_LPWSTR: the store takes ownership of a CoTaskMemAlloc'd copy.
        size = (len(APP_USER_MODEL_ID) + 1) * 2
        ole32.CoTaskMemAlloc.restype = ctypes.c_void_p
        ole32.CoTaskMemAlloc.argtypes = [ctypes.c_size_t]
        mem = ole32.CoTaskMemAlloc(ctypes.c_size_t(size))
        if not mem:
            return False
        ctypes.memmove(mem, ctypes.c_wchar_p(APP_USER_MODEL_ID), size)
        value = _PROPVARIANT()
        ctypes.memset(ctypes.byref(value), 0, ctypes.sizeof(value))
        value.vt = 31
        ctypes.memmove(
            ctypes.byref(value, 8),
            ctypes.byref(ctypes.c_void_p(mem)),
            ctypes.sizeof(ctypes.c_void_p),
        )
        table = ctypes.cast(
            ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        )[0]
        set_value = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.POINTER(_PROPERTYKEY),
            ctypes.POINTER(_PROPVARIANT),
        )(table[6])
        commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(table[7])
        key = _PROPERTYKEY(
            _guid(_PKEY_APPUSERMODEL_ID_FMTID), _PKEY_APPUSERMODEL_ID_PID
        )
        ok = set_value(ptr, ctypes.byref(key), ctypes.byref(value)) == 0
        commit(ptr)
        return ok
    finally:
        table = ctypes.cast(
            ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        )[0]
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])(ptr)


def _tag_media_windows() -> int:
    """Stamp our identity on every window in our tree that Windows might ask
    about. Returns how many took it."""

    if not _WIN:
        return 0
    try:
        mine = _our_process_tree()
        tagged = 0

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, _lparam):  # noqa: ANN001
            nonlocal tagged
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in mine:
                return True
            name = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, name, 64)
            # Chromium's own top-level windows, plus our real one.
            if name.value.startswith('Chrome_WidgetWin') or hwnd == _main_hwnd():
                if _stamp_window_identity(hwnd):
                    tagged += 1
            return True

        user32.EnumWindows(visit, 0)
        return tagged
    except Exception:
        logger.opt(exception=True).debug('could not tag the media windows')
        return 0


def _main_hwnd() -> int:
    try:
        return int(getattr(api, '_hwnd', 0) or 0)
    except Exception:
        return 0


def _apply_staged_update() -> None:
    """Install a downloaded update now that the window is gone.

    Silent on purpose: the user closed the app, so putting a wizard on
    screen would be the opposite of helpful. The installer keeps settings
    and the library, and does not relaunch (its post-install step is
    skipped in silent mode).

    If this fails there is nothing to tell anyone, because nobody is
    looking. The next launch finds the same update still pending and offers
    it again, so a failure costs one more prompt rather than a broken
    install.
    """

    installer = _staged_update
    if installer is None or not _WIN:
        return
    import subprocess

    try:
        if not installer.is_file():
            return
        logger.info('Applying staged update: {}', installer.name)
        # Waits for our own process to be gone before starting, so the
        # installer's single-instance check does not trip over us.
        subprocess.Popen(
            [
                'cmd', '/c',
                f'ping -n 3 127.0.0.1 >nul & '
                f'"{installer}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART',
            ],
            creationflags=(
                getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                | getattr(subprocess, 'DETACHED_PROCESS', 0)
            ),
            close_fds=True,
        )
    except Exception:
        logger.opt(exception=True).debug('could not apply the staged update')


def _schedule_media_identity() -> None:
    """Re-stamp a few times: WebView2 creates and replaces these windows
    after the app is already up."""

    def run(delay: float) -> None:
        time.sleep(delay)
        count = _tag_media_windows()
        if count:
            logger.debug('media identity applied to {} window(s)', count)

    for delay in _TAG_DELAYS:
        threading.Thread(
            target=run, args=(delay,), name='dannify-media-id', daemon=True
        ).start()


def main() -> None:
    _claim_app_identity()
    if not _acquire_single_instance():
        sys.exit(0)

    port = _pick_port()
    session_key = secrets.token_urlsafe(24)
    server = _start_server(port, session_key)
    _write_instance_file(port)

    import webview

    prefs = _read_prefs()
    theme = 'light' if prefs.get('theme') == 'light' else 'dark'
    native_frame = bool(prefs.get('native_frame', False))
    x, y, w, h, maximized = _load_window_state(prefs)

    # Keep WebView data (localStorage: language, volume, layout, history)
    # between launches: pywebview defaults to a throw-away private profile.
    _WEBVIEW_STORAGE.mkdir(parents=True, exist_ok=True)

    # Browser flags. This environment variable replaces pywebview's own
    # argument string, so we repeat its overscroll fix. Hardware media keys
    # route through Windows' media controls (keyboard keys, volume flyout).
    browser_args = [
        # Translate/OptimizationHints phone home and cost memory for a UI that
        # ships its own translations; ElasticOverscroll is pywebview's fix for
        # rubber-banding, which a desktop app should not do.
        '--disable-features=ElasticOverscroll,Translate,OptimizationHints,MediaRouter',
        # Register with Windows' media controls: the play/pause/next keyboard
        # keys and the volume flyout drive playback, with artwork and title.
        '--enable-features=HardwareMediaKeyHandling,MediaSessionService,GlobalMediaControls',
        # One page, one renderer. Without this WebView2 keeps spare processes
        # around that cost 40-60 MB each and buy us nothing.
        '--renderer-process-limit=1',
        # The whole UI holds a few thousand track objects at most; letting V8
        # grow to the default (a share of system RAM) just delays collection.
        '--js-flags=--max-old-space-size=256',
    ]
    # Remote debugging is a development aid and a back door into the running
    # app, so a shipped build ignores the variable entirely.
    devtools_port = '' if _FROZEN else os.environ.get('DANNIFY_DEVTOOLS_PORT', '').strip()
    if devtools_port.isdigit():
        browser_args.append(f'--remote-debugging-port={devtools_port}')
    os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = ' '.join(browser_args)

    api = DesktopApi(native_frame_pref=native_frame, prefs=prefs)
    api._theme = theme
    # What we asked for. Windows reports back a slightly different rect once
    # the custom frame is installed, and saving *that* made the window creep
    # a little taller on every launch until the player bar fell off the
    # bottom of the screen. If the user never touched the window, we keep
    # exactly what they last chose.
    api._launch_geometry = (x, y, w, h)

    window = webview.create_window(
        APP_TITLE,
        html=_splash_html(theme, native_frame),  # instant paint: no waiting on the server
        js_api=api,
        x=x,
        y=y,
        width=w,
        height=h,
        min_size=(MIN_W, MIN_H),
        background_color=_THEME_BG[theme],
        text_select=False,
        zoomable=True,
        maximized=maximized,
        shadow=False,  # the native frame already provides the DWM shadow
    )

    # pywebview hands the window only to a parameter literally named "window".
    def _before_show(window) -> None:  # noqa: ANN001  (UI thread, before first paint)
        api._attach(window)

    def _swap_to_app() -> None:
        # Give the media flyout something to call us other than "Unknown app".
        _schedule_media_identity()
        if _wait_until_up(port, token=session_key):
            # Edge WebView2 sometimes deadlocks on load_url() called from a
            # background thread; navigating via JS sidesteps it. The query
            # flag tells the frontend it runs inside the desktop shell.
            target = f'http://127.0.0.1:{port}/?shell=desktop&k={session_key}'
            try:
                window.evaluate_js(f"window.location.replace('{target}')")
            except Exception:
                window.load_url(target)
        else:
            window.load_html(
                _splash_html(
                    theme,
                    api._native_frame,
                    '<h2>Dannify could not start</h2>'
                    '<p>Please check the log file at<br><code>'
                    f'{_DATA_DIR / "dannify.log"}</code></p>',
                )
            )

    def _on_state_change() -> None:
        api._push_state()

    def _on_minimized() -> None:
        # pywebview dispatches this event on a throwaway thread with no
        # message pump, and a NotifyIcon built there never receives its
        # taskbar callbacks: the window would vanish behind a dead tray
        # icon. Marshal onto the real UI thread first.
        if api._minimize_to_tray and not api._mini and not api._quitting:
            api._ui(api._hide_to_tray, wait=True)
        api._push_state()

    def _on_closing():
        # Runs on the UI thread before the window goes away. Returning False
        # cancels the close, which is how "keep playing in the tray" works.
        if api._close_to_tray and not api._quitting and api._hide_to_tray():
            return False
        # Remember the restored geometry (and whether it was maximized).
        api._closing = True
        try:
            hwnd = api._hwnd
            if hwnd and not api._fullscreen:
                placement = api._pre_mini if api._mini and api._pre_mini else _current_placement(hwnd)
                placement = _settle(placement, api._launch_geometry)
                if placement['w'] >= MIN_W and placement['h'] >= MIN_H:
                    _write_prefs(placement)
        except Exception:
            pass

    def _on_closed() -> None:
        for part in (api._taskbar, api._tray):
            try:
                if part is not None:
                    part.dispose()
            except Exception:
                pass
        try:
            server.should_exit = True
        except Exception:
            pass

    window.events.before_show += _before_show
    window.events.maximized += _on_state_change
    window.events.restored += _on_state_change
    window.events.minimized += _on_minimized
    window.events.closing += _on_closing
    window.events.closed += _on_closed

    # gui='edgechromium' = Edge WebView2 (ships with Windows 10/11).
    webview.start(
        _swap_to_app,
        gui='edgechromium',
        debug=False,
        private_mode=False,
        storage_path=str(_WEBVIEW_STORAGE),
    )

    # Window closed → give uvicorn a moment to drain, then exit.
    time.sleep(0.3)
    _apply_staged_update()


if __name__ == '__main__':
    # PoW solver sub-mode: if this exe was respawned by the lyrics-publish
    # flow to chase a nonce, just run the search loop and exit (no
    # FastAPI, no window, no log file). Detected via two env vars our own
    # parent sets: never exposed to the user.
    _job = os.environ.get('DANNIFY_POW_WORKER')
    _job_out = os.environ.get('DANNIFY_POW_OUT')
    if _job and _job_out:
        import hashlib as _hashlib
        try:
            prefix, target_hex, start, stride = _job.split('|')
            target = bytes.fromhex(target_hex)
            # lrclib hashes ``prefix + nonce`` with NO separator. The
            # colon-separated form is only used for the X-Publish-Token
            # HTTP header. The Rust reference is the source of truth:
            # https://github.com/tranxuanthang/lrcget/blob/main/src-tauri/src/lrclib/challenge_solver.rs
            pre = prefix.encode()
            sha = _hashlib.sha256
            n = int(start)
            stride = int(stride)
            while True:
                if sha(pre + str(n).encode()).digest() < target:
                    # Windowed exe has no stdout: write result to the
                    # caller-provided file path so the parent can read
                    # it without a pipe.
                    with open(_job_out, 'w', encoding='utf-8') as f:
                        f.write(str(n))
                    break
                n += stride
        except Exception:
            pass
        sys.exit(0)

    main()
