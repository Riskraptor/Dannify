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
# Or a folder of replacement files from a partial update, applied the same
# way but by our own helper rather than by Setup.
_staged_delta: Optional[Path] = None
_INSTANCE_FILE = _DATA_DIR / 'instance.json'
_WINDOW_STATE_FILE = _DATA_DIR / 'window.json'
_WEBVIEW_STORAGE = _DATA_DIR / 'WebView2'
# The sign-in window runs its own WebView2 profile (see _LoginWindow).
_LOGIN_STORAGE = _DATA_DIR / 'SignIn'
DEFAULT_W, DEFAULT_H = 1320, 860
# Below this the desktop layout would collapse into the phone layout.
MIN_W, MIN_H = 760, 540
MINI_W, MINI_H = 420, 124
# The compact player can drop a lyrics or queue panel below the bar.
MINI_MAX_H = 560

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
    """Append a line to the rotating log even before backend logging is wired.

    Two places, because the first one can be unavailable exactly when there is
    something worth recording: during an update two copies are briefly alive
    and the log can be held open, and a line dropped then is a line about the
    thing that went wrong. The fallback sits beside it and is only written
    when the main file refuses.
    """

    line = '[desktop] ' + ' '.join(str(a) for a in args) + '\n'
    try:
        with open(_DATA_DIR / 'dannify.log', 'a', encoding='utf-8') as f:
            f.write(line)
        return
    except Exception:
        pass
    try:
        with open(_DATA_DIR / 'dannify-startup.log', 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass


def _fatal() -> None:
    """Last resort when the app cannot start.

    A packaged app has no console, so anything that escapes main() used to
    surface as the build tool's own crash box: a Python traceback with file
    names and line numbers in it. That tells the person nothing they can act
    on and quite reasonably alarms them. The detail goes to the log; the
    window says what happened and what to try.
    """

    import traceback

    try:
        logger_print('startup failed\n' + traceback.format_exc())
    except Exception:
        pass
    if not _WIN:
        return
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            'Dannify could not start.\n\n'
            'Close it from the notification area if a copy is still running, '
            'then open it again. If it keeps happening, install the latest '
            'version over the top of this one.',
            APP_TITLE,
            0x10 | 0x40000,  # MB_ICONERROR | MB_TOPMOST
        )
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
    ):
        self.hwnd = hwnd
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

            icon = NotifyIcon()
            icon.Icon = _app_icon()
            icon.Text = APP_TITLE
            # No ContextMenuStrip: the menu is a real Windows one, popped by
            # hand on right-click so the shell draws it (see _NativeMenu).
            # Single left click restores, which is what Spotify, Discord and
            # every other tray app does. Double click kept for habit. The
            # right button opens the menu, so it must not restore.
            def _clicked(sender, args):  # noqa: ANN001
                try:
                    if args.Button == MouseButtons.Left:
                        self._api._show_from_tray()
                except Exception:
                    pass

            icon.MouseClick += MouseEventHandler(_clicked)
            icon.DoubleClick += EventHandler(lambda s, e: self._api._show_from_tray())
            def _mouse_up(sender, args):  # noqa: ANN001
                try:
                    if args.Button == MouseButtons.Middle:
                        self._api._media('toggle')
                    elif args.Button == MouseButtons.Right:
                        self._popup_menu()
                except Exception:
                    logger.opt(exception=True).debug('tray click failed')

            icon.MouseUp += MouseEventHandler(_mouse_up)
            icon.Visible = True
            self._icon = icon
            return True
        except Exception as exc:
            logger_print('tray icon unavailable:', exc)
            return False

    def _popup_menu(self) -> None:
        """Right-click: show the real Windows menu."""

        menu = _NativeMenu()
        label = self._track or self.labels['nowPlaying']
        # The track is context, not a command, so it is a disabled row at the
        # top exactly as every other player's tray menu does it.
        menu.add(label[:64], None, enabled=False)
        menu.add_separator()
        menu.add(
            self.labels['pause' if self._playing else 'play'],
            lambda: self._api._media('toggle'),
            enabled=self._has_track,
        )
        menu.add(
            self.labels['prev'],
            lambda: self._api._media('prev'),
            enabled=self._has_track,
        )
        menu.add(
            self.labels['next'],
            lambda: self._api._media('next'),
            enabled=self._has_track,
        )
        menu.add_separator()
        menu.add(self.labels['show'], self._api._show_from_tray, default=True)
        menu.add(self.labels['quit'], self._api._quit)
        menu.show(self._api._hwnd or 0)

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
        """Only the hover tooltip needs updating now.

        The menu is rebuilt from current state every time it opens, so there
        are no persistent menu items left to keep in sync.
        """

        if self._icon is None:
            return
        try:
            label = self._track or self.labels['nowPlaying']
            self._icon.Text = (APP_TITLE + chr(10) + label)[:127]
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
        # Minimising minimises. The close button is what sends the app to
        # the tray, and a switch that made minimise do the same thing just
        # meant people turned it on once and then could not work out why
        # their window kept disappearing. The switch is gone; this clears it
        # for anyone who had it on.
        if prefs.get('minimize_to_tray'):
            _write_prefs({'minimize_to_tray': False})
        self._hidden = False
        # When the browser engine's renderer last died, so a reload loop
        # cannot get going.
        self._renderer_failures: list[float] = []
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
        if self._close_to_tray:
            self._tray.install()
        self._frame = _CustomFrame(
            self._hwnd,
            on_command=self._on_thumb_button,
            on_taskbar_created=self._on_taskbar_created,
            on_maximize=self.win_toggle_maximize,
            on_max_hover=self._on_max_hover,
        )
        if self._native_frame_pref:
            # Keep the Windows caption; the subclass is still needed for the
            # taskbar buttons, so install it without reclaiming the caption.
            self._frame._nccalcsize = lambda hwnd, msg, w, l: self._frame._comctl.DefSubclassProc(hwnd, msg, w, l)  # noqa: E731
        ok = self._frame.install()
        self._native_frame = self._native_frame_pref or not ok
        self._guard_renderer()

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

    def _on_max_hover(self, on: bool) -> None:
        """Windows owns the mouse over the maximize button; the page does not
        get :hover there, so tell it to light the button itself."""
        flag = 'true' if on else 'false'
        threading.Thread(
            target=self._eval,
            args=(f'window.__dannifyMaxHover && window.__dannifyMaxHover({flag})',),
            daemon=True,
        ).start()

    def _guard_renderer(self) -> None:
        """Never let the browser engine show its own crash page.

        Lose the renderer, whether to Task Manager, a graphics driver reset or
        plain memory pressure, and WebView2 paints "This page is having a
        problem" with a blue Refresh button under it. That is a browser
        telling somebody their tab died, in the middle of what is meant to be
        an application: it is the single most website-like thing the window
        can do. Take the event and put the interface back instead.
        """

        if not _WIN:
            return

        def attach():
            try:
                view = self._form.browser.webview
            except Exception:
                return

            def on_failed(_sender, args):  # noqa: ANN001
                try:
                    kind = str(args.ProcessFailedKind)
                except Exception:
                    kind = '?'
                logger_print('renderer failed:', kind)
                # The browser process itself going is not survivable in place;
                # everything else is a reload.
                if 'Browser' in kind:
                    return
                self._recover_renderer()

            def subscribe(core) -> bool:
                if core is None:
                    return False
                try:
                    core.ProcessFailed += on_failed
                    return True
                except Exception:
                    return False

            try:
                if subscribe(view.CoreWebView2):
                    return
            except Exception:
                pass

            def on_ready(_sender, _args):  # noqa: ANN001
                try:
                    subscribe(view.CoreWebView2)
                except Exception:
                    pass

            try:
                view.CoreWebView2InitializationCompleted += on_ready
            except Exception:
                pass

        self._ui(attach)

    def _recover_renderer(self) -> None:
        """Reload after a renderer died, without spinning on it."""

        now = time.time()
        recent = [t for t in self._renderer_failures if now - t < 60]
        recent.append(now)
        self._renderer_failures = recent
        if len(recent) > 3:
            # Something is wrong that reloading will not mend. Stop trying
            # rather than flickering at the user for ever.
            logger_print('renderer keeps failing; leaving it alone')
            return

        def go():
            try:
                self._form.browser.webview.CoreWebView2.Reload()
            except Exception as exc:
                logger_print('could not reload after a renderer failure:', exc)

        self._ui(go)

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
        floor_w = int(MIN_W * value * scale) + 2 * fx
        floor_h = int(MIN_H * value * scale) + fy

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

    # --- tray ---------------------------------------------------------------
    def tray_set(self, options: dict) -> dict:
        """Enable or disable close-to-tray."""
        if not isinstance(options, dict):
            return self.win_state()
        if 'closeToTray' in options:
            self._close_to_tray = bool(options['closeToTray'])
            _write_prefs({'close_to_tray': self._close_to_tray})
        if self._tray is not None:
            wanted = self._close_to_tray
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

    def app_restart(self) -> bool:
        """Relaunch Dannify (used by the 'restart to apply' prompt)."""
        # When a partial update is waiting, the helper that applies it is also
        # the thing that starts the app again. Spawning a copy here as well
        # put two processes in the same folder at the same moment: one
        # rewriting it, one booting out of it. Whoever lost that race came up
        # broken. Just close; the helper does the rest.
        if _staged_delta is not None:
            threading.Timer(0.25, self._quit).start()
            return True
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
        _note_update_attempt(_version_from_staging(path))
        logger.info('Update staged for the next exit: {}', path.name)
        return True

    def app_stage_delta(self, folder: str) -> bool:
        """Hold a folder of replacement files to apply when the app closes.

        Same contract as staging an installer: nothing happens now, the work
        is done on the way out so no file is in use when it is replaced.
        """

        global _staged_delta
        try:
            path = Path(str(folder or '')).resolve()
            path.relative_to((_DATA_DIR / 'updates').resolve())
            if not (path / 'apply.json').is_file():
                return False
        except Exception:
            return False
        _staged_delta = path
        _note_update_attempt(_version_from_staging(path))
        logger.info('Partial update staged for the next exit: {}', path.name)
        return True

    def app_clear_staged_update(self) -> bool:
        global _staged_update, _staged_delta
        _staged_update = None
        _staged_delta = None
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
            # The window is called Dannify, full stop. Putting the track in
            # the title made the caption, the taskbar and alt-tab all read
            # like a browser tab retitling itself. What is playing belongs in
            # the player bar and the tray tooltip, which both already show it.
            if self._form is not None and self._form.Text != APP_TITLE:
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


# --- Applying a downloaded update -----------------------------------------
#
# An update that only fetched the files that changed arrives as a folder of
# replacements plus an apply.json describing them. Something has to copy
# them over the installation, and it cannot be the app itself: a running
# executable holds its own file open.
#
# So the app relaunches itself with --apply-update. That second copy waits
# for the first to exit, does the copying, and starts the app again. Using
# our own executable rather than shipping a separate updater means there is
# no extra binary to sign, to explain, or to go missing. It is a windowed
# program, so nothing appears on screen while it works.


def _apply_update_folder(staging: Path) -> bool:
    """Copy a staged update over this installation. Runs in the helper.

    Nothing may be imported once the first file has moved. This program is a
    single executable with its own archive of modules inside it, and the
    importer opens that archive by path, lazily, the first time a module is
    asked for. Replace the executable and the next lazy import reads the new
    archive at the old offsets: "Error -3 while decompressing data". That is
    not hypothetical, it is what happened. Everything the rest of this
    function and its caller need is loaded up front, by _preload_for_apply().
    """

    import shutil

    from dannify import delta

    staging = Path(staging)
    plan_file = staging / 'apply.json'
    try:
        plan = json.loads(plan_file.read_text(encoding='utf-8'))
    except Exception:
        logger_print('no usable apply.json in', staging)
        return False

    exe_name = Path(sys.executable).name.lower()
    target = Path(sys.executable).resolve().parent
    files = plan.get('files', {})
    logger_print(f'applying update {plan.get("version", "?")} into {target}')

    # Two passes, because the old way could destroy an installation.
    #
    # It used to rename the live file out of the way and then copy the new one
    # in. If that copy failed - a full disk, a virus scanner holding the fresh
    # unsigned executable, the power going - the rename had already happened
    # and the file was simply gone. When the file in question is Dannify.exe,
    # nothing launches any more and there is nothing left to roll back to.
    #
    # So: copy everything beside its destination first, touching nothing live.
    # Only once every copy has landed do the renames, which are as close to
    # atomic as the filesystem gets and cannot half-write. If one of those
    # fails, put back the ones already done.
    staged: list[tuple[Path, Path]] = []  # (destination, its .new)
    try:
        for rel in sorted(files):
            source = staging / rel
            if not source.is_file():
                continue  # unchanged file, was never downloaded
            dest = target / rel
            fresh = dest.with_name(dest.name + '.new')
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                fresh.unlink()
            except OSError:
                pass
            shutil.copy2(source, fresh)
            staged.append((dest, fresh))
    except Exception as exc:
        logger_print('could not stage', exc)
        for _dest, fresh in staged:
            try:
                fresh.unlink()
            except OSError:
                pass
        return False

    # Our own executable goes last, so the window in which this process is
    # running against a swapped archive is as small as it can be.
    staged.sort(key=lambda p: p[0].name.lower() == exe_name)

    marker = target / '.updating'
    try:
        marker.write_text(str(plan.get('version', '')), encoding='utf-8')
    except OSError:
        pass

    done: list[tuple[Path, Path, bool]] = []  # (dest, its .old, .old exists)
    for dest, fresh in staged:
        stale = dest.with_name(dest.name + '.old')
        try:
            try:
                stale.unlink()
            except OSError:
                pass
            had = dest.exists()
            if had:
                # A running executable cannot be overwritten, but it can be
                # renamed out of the way: that includes this very file.
                dest.rename(stale)
            fresh.rename(dest)
            done.append((dest, stale, had))
        except Exception as exc:
            logger_print('could not put', dest.name, 'in place:', exc)
            # Undo, newest first, so the install is exactly as we found it.
            for gone, old, had in reversed(done):
                try:
                    gone.rename(gone.with_name(gone.name + '.new'))
                    if had:
                        old.rename(gone)
                except OSError:
                    logger_print('rollback failed for', gone.name)
            try:
                marker.unlink()
            except OSError:
                pass
            return False

    copied = len(done)
    try:
        marker.unlink()
    except OSError:
        pass

    # Check what actually landed. Only the handful we replaced, so this costs
    # nothing, and a silently corrupt copy is worth catching here rather than
    # at the next launch.
    for dest, _stale, _had in done:
        rel = dest.relative_to(target).as_posix()
        want = files.get(rel) or {}
        if not want.get('sha256'):
            continue
        try:
            if delta.sha256_of(dest) != want['sha256']:
                logger_print('what landed does not match the manifest:', rel)
                return False
        except OSError as exc:
            logger_print('could not read back', rel, exc)
            return False

    emptied: set[Path] = set()
    for rel in plan.get('removed', []):
        # The plan is written by whichever version downloaded the update, and
        # an older one listed everything the manifest did not mention: the
        # uninstaller Setup left here, and the ship-time config. Check again
        # on this side, where the files actually are.
        if not delta.is_ours(str(rel)):
            logger_print('keeping', rel, '(not ours to remove)')
            continue
        try:
            gone = (target / rel).resolve()
            gone.relative_to(target)  # never delete outside the install
            if gone.is_file():
                gone.unlink()
                emptied.add(gone.parent)
        except Exception:
            pass

    # A release that drops a whole folder leaves the folder behind, because
    # the plan lists files. An install that has been updated a few times then
    # carries a little museum of empty directories, named for things the app
    # no longer ships. Walk up from each one and take the empty ones with it.
    for folder in sorted(emptied, key=lambda p: len(p.parts), reverse=True):
        while folder != target:
            try:
                folder.relative_to(target)
                folder.rmdir()  # refuses if anything is still in there
            except Exception:
                break
            folder = folder.parent

    logger_print(f'update applied: {copied} file(s) replaced')
    return True


def _wait_for_apply_to_finish(root: Path, timeout: float = 45.0) -> None:
    """Hold off while an update helper is part way through the folder.

    The helper leaves a marker beside the app for the few seconds its renames
    take. Starting in the middle of that means loading half of one build and
    half of another, so wait it out. A stale marker from a helper that died is
    cleared once the timeout passes: an app that refuses to start for ever is
    worse than one that starts against a folder nobody is touching.
    """

    marker = root / '.updating'
    waited = 0.0
    while waited < timeout:
        try:
            if not marker.exists():
                return
        except OSError:
            return
        time.sleep(0.25)
        waited += 0.25
    logger_print('an update looks stuck; starting anyway')
    try:
        marker.unlink()
    except OSError:
        pass


def _sweep_old_files(root: Path) -> None:
    """Clear what a previous update left lying about.

    Reaching here means this build started, so the copies it replaced are
    safe to drop. Half-staged .new files are swept too: an apply that never
    got as far as its renames leaves them, and they are dead weight.

    Empty folders go the same way. An update removes files, not directories,
    so a release that stops shipping a whole folder leaves the folder there,
    and an install updated a few times collects a set of empty directories
    named for things the app no longer has. Nothing in here ever wants an
    empty folder, and one this build needs it makes for itself.
    """

    try:
        for stale in list(Path(root).rglob('*.old')) + list(Path(root).rglob('*.new')):
            try:
                stale.unlink()
            except OSError:
                pass  # still locked; the next launch gets it
    except Exception:
        pass

    try:
        # Deepest first, so clearing a child lets its parent go in the same
        # pass. rmdir refuses a folder with anything in it, which is the whole
        # safety check: no listing, no rules about what may go.
        folders = sorted(
            (p for p in Path(root).rglob('*') if p.is_dir()),
            key=lambda p: len(p.parts),
            reverse=True,
        )
        for folder in folders:
            try:
                folder.rmdir()
            except OSError:
                pass
    except Exception:
        pass


def _preload_for_apply() -> tuple:
    """Load everything the update helper needs, before it touches a file.

    See the note in _apply_update_folder: once our own executable has been
    replaced, importing anything that is not already in memory reads the new
    archive with the old offsets and fails. So the imports happen here, while
    the file on disk is still the one we were started from.
    """

    import shutil
    import subprocess

    from dannify import delta

    # Touch the attributes too, not just the module objects: a lazy importer
    # can defer a submodule until first use.
    _ = (shutil.copy2, shutil.rmtree, subprocess.Popen, delta.is_ours)
    return shutil, subprocess, delta


def _run_update_helper(staging: str) -> int:
    """The --apply-update entry point."""

    shutil, subprocess, _delta = _preload_for_apply()
    _wait_for_parent_exit()
    ok = _apply_update_folder(Path(staging))
    exe = Path(sys.executable).resolve()
    if ok:
        try:
            shutil.rmtree(staging, ignore_errors=True)
        except Exception:
            pass
    # Start the app again either way: a failed update must not leave the
    # user with nothing running. A bad copy still has the old files, and the
    # update will simply be offered again.
    #
    # Not immediately, though, and not only once. Waiting for the old process
    # to exit is not the same as waiting for it to let go: the browser engine
    # runs in its own child processes, and they keep the profile folder open
    # for a moment after their parent is gone. Start inside that moment and
    # the engine refuses to open the folder at all, which takes the whole
    # window down with it. That is what put "Dannify could not start" on
    # screen after an update while the update itself had worked perfectly.
    for attempt in range(4):
        time.sleep(2 if attempt == 0 else 3)
        try:
            child = subprocess.Popen(
                [str(exe)],
                cwd=str(exe.parent),
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                close_fds=True,
            )
        except Exception as exc:
            logger_print('could not relaunch after the update:', exc)
            return 0 if ok else 1

        # A copy that got the folder stays up. One that did not is gone in
        # about a second, so a short watch tells the two apart.
        settled = None
        for _ in range(12):
            time.sleep(0.5)
            settled = child.poll()
            if settled is not None:
                break
        if settled is None:
            return 0 if ok else 1
        # Exit code 0 is the single-instance path: something else is already
        # running, which is a fine place to stop.
        if settled == 0:
            return 0 if ok else 1
        logger_print(f'relaunch {attempt + 1} exited with {settled}; trying again')

    logger_print('gave up relaunching after the update')
    return 0 if ok else 1


# A name the installer can signal to ask us to shut down. Without this the
# only way to close a running copy is a window message, and close-to-tray
# swallows those: the app hides instead of exiting and the installer sits
# there waiting for a process that is never going to leave.
_QUIT_EVENT_NAME = r'Local\DannifyQuitRequest'


def _quit_event_name() -> str:
    return _QUIT_EVENT_NAME + os.environ.get('DANNIFY_INSTANCE', '')


def _watch_for_quit_request(on_quit) -> None:
    """Quit when something outside asks us to, properly rather than to tray."""

    if not _WIN:
        return

    def run() -> None:
        try:
            _proto(kernel32.CreateEventW, wintypes.HANDLE,
                   ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR)
            _proto(kernel32.WaitForSingleObject, wintypes.DWORD,
                   wintypes.HANDLE, wintypes.DWORD)
            handle = kernel32.CreateEventW(None, True, False, _quit_event_name())
            if not handle:
                return
            # INFINITE; the thread is a daemon so it dies with the process.
            if kernel32.WaitForSingleObject(handle, 0xFFFFFFFF) == 0:
                logger.info('Shutdown requested from outside; closing')
                on_quit()
        except Exception:
            logger.opt(exception=True).debug('quit watcher failed')

    threading.Thread(target=run, name='dannify-quit-watch', daemon=True).start()


def _signal_quit_request() -> bool:
    """Ask a running copy to exit. True if one was there to ask."""

    if not _WIN:
        return False
    try:
        _proto(kernel32.OpenEventW, wintypes.HANDLE,
               wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
        _proto(kernel32.SetEvent, wintypes.BOOL, wintypes.HANDLE)
        EVENT_MODIFY_STATE = 0x0002
        handle = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, _quit_event_name())
        if not handle:
            return False
        kernel32.SetEvent(handle)
        kernel32.CloseHandle(handle)
        return True
    except Exception:
        return False


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


def _running_instance_window() -> int:
    """The main window of the instance already running, or 0.

    Prefers the handle it wrote down; falls back to walking its windows.
    Deliberately does not filter on visibility: the whole point is to find
    the window when it has been hidden into the tray.
    """

    pid = 0
    hwnd = 0
    try:
        note = json.loads(_INSTANCE_FILE.read_text(encoding='utf-8'))
        pid = int(note.get('pid', 0) or 0)
        hwnd = int(note.get('hwnd', 0) or 0)
    except Exception:
        pass

    if hwnd and user32.IsWindow(wintypes.HWND(hwnd)):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(owner))
        if not pid or owner.value == pid:
            return hwnd

    if not pid:
        return 0
    found: list[int] = []

    def visit(candidate, _):  # noqa: ANN001
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(candidate, ctypes.byref(owner))
        if owner.value != pid or user32.GetWindow(candidate, GW_OWNER):
            return True
        name = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(candidate, name, 128)
        # The app's own frame, not an IME or message-only helper window.
        if name.value.startswith('WindowsForms10.Window.8'):
            found.append(candidate)
            return False
        return True

    try:
        user32.EnumWindows(_EnumWindowsProc(visit), 0)
    except Exception:
        return 0
    return found[0] if found else 0


def _focus_existing_window() -> None:
    """Bring the running instance forward, from wherever it is.

    Launching the app again when it is already running should behave like
    every other Windows application: the window you already have comes
    back. It used to do nothing at all when the window had been hidden into
    the tray, which left people with no way to find the app they could hear
    playing.
    """

    hwnd = _running_instance_window()
    if not hwnd:
        return
    handle = wintypes.HWND(hwnd)
    try:
        # SW_SHOW un-hides; SW_RESTORE un-minimises. A window can need both.
        if not user32.IsWindowVisible(handle):
            user32.ShowWindow(handle, SW_SHOW)
        if user32.IsIconic(handle):
            user32.ShowWindow(handle, SW_RESTORE)
        # Windows refuses a foreground steal unless the calling thread is
        # attached to the one that owns the window. We were just launched by
        # the user, so we are entitled to it; the attach is what makes the
        # entitlement transfer.
        target_thread = user32.GetWindowThreadProcessId(handle, None)
        our_thread = kernel32.GetCurrentThreadId()
        attached = False
        if target_thread and target_thread != our_thread:
            attached = bool(user32.AttachThreadInput(our_thread, target_thread, True))
        try:
            user32.BringWindowToTop(handle)
            user32.SetForegroundWindow(handle)
            user32.SetActiveWindow(handle)
        finally:
            if attached:
                user32.AttachThreadInput(our_thread, target_thread, False)
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


_PORT_FILE = _DATA_DIR / 'port.json'


def _pick_port() -> int:
    """The same port this installation used last time, if it is still free.

    It used to take whatever the kernel handed out, which meant a different
    port on every launch. The page is served from that port, so the browser
    engine saw a different origin each time and handed the app an empty
    localStorage: volume, language, zoom, the home cache, the playing
    position, half-written lyrics, all gone every single start. Everything
    the app thought it remembered between launches, it did not.

    Still not a fixed number, and still not a well-known one. It is chosen
    once per installation and kept, so the origin stops moving.
    """

    if PREFERRED_PORT and _port_is_free(PREFERRED_PORT):
        return PREFERRED_PORT

    try:
        saved = int(json.loads(_PORT_FILE.read_text(encoding='utf-8'))['port'])
        if 1024 < saved < 65536 and _port_is_free(saved):
            return saved
    except Exception:
        pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((BIND_HOST, 0))  # the OS hands us a port nobody owns
        port = int(s.getsockname()[1])
    try:
        _PORT_FILE.write_text(json.dumps({'port': port}), encoding='utf-8')
    except OSError:
        pass  # a moving port is a nuisance, not a reason to fail to start
    return port


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


_UPDATE_NOTE = _DATA_DIR / 'update-result.json'


def _note_update_attempt(version: str) -> None:
    """Write down which version we are about to install.

    An update that fails used to do so in complete silence: the files were not
    replaced, nothing said why, and the same update was offered again on the
    next check, forever. From the outside that is an app whose updates simply
    never work.

    The next start compares this against the version actually running. If they
    match the update landed and the note goes. If they do not, something ate
    it, and the app says so instead of quietly offering it again.
    """

    try:
        _UPDATE_NOTE.write_text(
            json.dumps({'version': str(version or '')}), encoding='utf-8',
        )
    except OSError:
        pass


def _version_from_staging(path) -> str:
    """The version a staging folder or installer is carrying."""

    name = Path(path).name
    match = _re_version.search(name)
    return match.group(0) if match else ''


_re_version = __import__('re').compile(r'\d+\.\d+\.\d+')


def _write_instance_file(port: int, hwnd: int = 0) -> None:
    """Leave a note for a second launch: how to reach us, and which window
    to bring forward.

    The handle matters. Finding the window by title does not work (the title
    is whatever is playing) and finding it by enumerating visible windows
    does not work either, because a window hidden in the tray is not
    visible. Writing the handle down removes the guessing.
    """

    try:
        payload = {'port': port, 'pid': os.getpid()}
        if hwnd:
            payload['hwnd'] = int(hwnd)
        _INSTANCE_FILE.write_text(json.dumps(payload), encoding='utf-8')
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

    import subprocess

    # A partial update goes first: it is the cheaper and more common one.
    if _staged_delta is not None and _WIN:
        try:
            exe = Path(sys.executable).resolve()
            logger.info('Applying partial update from {}', _staged_delta.name)
            env = dict(os.environ)
            env['DANNIFY_WAIT_PID'] = str(os.getpid())
            subprocess.Popen(
                [str(exe), '--apply-update', str(_staged_delta)],
                cwd=str(exe.parent),
                env=env,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                close_fds=True,
            )
            return
        except Exception:
            logger.opt(exception=True).debug('could not start the update helper')

    installer = _staged_update
    if installer is None or not _WIN:
        return

    try:
        if not installer.is_file():
            return
        logger.info('Applying staged update: {}', installer.name)
        # Launched directly. This used to go through `cmd /c ping ... &` to
        # wait for our own process to exit, which put a console window on
        # screen for a moment with 127.0.0.1 in it: CREATE_NO_WINDOW is
        # documented to be ignored when combined with DETACHED_PROCESS, so
        # the flags never suppressed it. The wait was not needed anyway,
        # because the installer waits for our mutex itself.
        subprocess.Popen(
            [str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
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


_OPEN_FILE = _DATA_DIR / 'open.json'


def _file_argument() -> str:
    """The file Explorer handed us, if it did.

    Double-clicking a .dnf runs the app with the path as its only argument,
    so anything that is not one of our own switches and is a file on disk is
    that. Checked against the disk rather than by extension so a rename does
    not make the association stop working.
    """

    for arg in sys.argv[1:]:
        if arg.startswith('-'):
            continue
        try:
            if Path(arg).is_file():
                return str(Path(arg).resolve())
        except OSError:
            continue
    return ''


def _hand_file_to_running_instance(path: str) -> None:
    """Pass the file to the copy already running, then bring it forward."""

    try:
        _OPEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _OPEN_FILE.write_text(
            json.dumps({'path': path, 'n': time.time_ns()}), encoding='utf-8',
        )
    except OSError:
        logger_print('could not pass the file to the running copy')


def _watch_for_opened_files() -> None:
    """Play files handed over by a second copy started from Explorer.

    Windows starts a whole new process for every double-click. That copy
    finds the mutex taken, drops the path here and brings the existing window
    forward, and this is the end that notices. One stat call every half second
    costs nothing and works whether or not the window handle can be found.
    """

    import main as backend

    last = ''
    while True:
        time.sleep(0.5)
        try:
            if not _OPEN_FILE.is_file():
                continue
            note = json.loads(_OPEN_FILE.read_text(encoding='utf-8'))
            stamp = str(note.get('n') or '')
            if not stamp or stamp == last:
                continue
            last = stamp
            wanted = str(note.get('path') or '')
        except Exception:
            continue
        if wanted:
            try:
                backend.open_external(wanted)
            except Exception:
                logger_print('could not open', wanted)


def main() -> None:
    # `--quit` is how the installer asks a running copy to get out of the
    # way before it replaces the files. It is not a user-facing switch.
    if '--quit' in sys.argv[1:]:
        _signal_quit_request()
        sys.exit(0)

    # `--apply-update <dir>` is this same program acting as its own updater:
    # it waits for the copy that spawned it to exit, replaces the files, and
    # starts the app again.
    if '--apply-update' in sys.argv[1:]:
        where = sys.argv[sys.argv.index('--apply-update') + 1 :]
        if where:
            sys.exit(_run_update_helper(where[0]))
        sys.exit(2)

    # Never boot out of a folder something is still rewriting.
    _wait_for_apply_to_finish(Path(sys.executable).resolve().parent)

    # Tidy up whatever the last update renamed out of the way.
    _sweep_old_files(Path(sys.executable).resolve().parent)

    _claim_app_identity()
    opening = _file_argument()
    if not _acquire_single_instance():
        # Already running, and it has just been brought forward. Explorer
        # started us only to open a file, so leave it where the running copy
        # will find it and get out of the way.
        if opening:
            _hand_file_to_running_instance(opening)
        sys.exit(0)

    port = _pick_port()
    session_key = secrets.token_urlsafe(24)
    server = _start_server(port, session_key)
    _write_instance_file(port)

    threading.Thread(
        target=_watch_for_opened_files, name='dannify-open', daemon=True,
    ).start()
    if opening:
        # We are the first copy: the window is not up yet and nothing is
        # listening on the websocket, so wait for it rather than shouting
        # into an empty room.
        def _open_when_ready(path: str = opening) -> None:
            import main as backend

            for _ in range(60):
                time.sleep(0.5)
                if getattr(backend.api.state.connections, 'connected', False):
                    break
            try:
                backend.open_external(path)
            except Exception:
                logger_print('could not open', path)

        threading.Thread(
            target=_open_when_ready, name='dannify-open-first', daemon=True,
        ).start()

    import webview

    prefs = _read_prefs()
    theme = 'light' if prefs.get('theme') == 'light' else 'dark'
    # Dannify draws its own title bar, always. The Windows caption used to be
    # optional, and turning it on left two title bars stacked: the system's
    # with the app name, then ours underneath with the logo and name again,
    # which reads as one app running inside another. The option is gone and
    # any saved copy of it is cleared, so an install that had it on fixes
    # itself on the next launch. A native caption can still appear if the
    # custom frame fails to install, and the interface drops its own brand
    # row in that case so there is never a second bar.
    if prefs.get('native_frame'):
        _write_prefs({'native_frame': False})
    native_frame = False
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
        # Ctrl with the scroll wheel zooming the whole interface is browser
        # behaviour and makes the app feel like a page in a window. Interface
        # size is a setting under Appearance instead.
        zoomable=False,
        maximized=maximized,
        shadow=False,  # the native frame already provides the DWM shadow
    )

    # pywebview hands the window only to a parameter literally named "window".
    def _before_show(window) -> None:  # noqa: ANN001  (UI thread, before first paint)
        api._attach(window)
        # Now that there is a real window, record it so a second launch can
        # bring it back even after it has been hidden into the tray.
        try:
            _write_instance_file(port, api._hwnd)
        except Exception:
            pass

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
                    # Nothing about files or folders here. Someone looking at
                    # this screen wants to know what to do, not where we keep
                    # our notes.
                    '<h2>Dannify could not start</h2>'
                    '<p>Close it from the notification area if a copy is '
                    'still running, then open it again.</p>',
                )
            )

    def _on_state_change() -> None:
        api._push_state()

    def _on_minimized() -> None:
        api._push_state()

    def _on_closing():
        # Runs on the UI thread before the window goes away. Returning False
        # cancels the close, which is how "keep playing in the tray" works.
        #
        # Except when Windows itself is going down: an app that answers a
        # shutdown by hiding is an app that blocks the shutdown.
        shutting_down = False
        try:
            shutting_down = bool(user32.GetSystemMetrics(SM_SHUTTINGDOWN))
        except Exception:
            pass
        if (
            api._close_to_tray
            and not api._quitting
            and not shutting_down
            and api._hide_to_tray()
        ):
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

    # Let the installer (or anything else) ask us to close properly rather
    # than hide into the tray.
    _watch_for_quit_request(api._quit)

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

    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        _fatal()
