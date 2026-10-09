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
import sys
import threading
from pathlib import Path
from typing import Optional

from .win32 import (
    _WIN,
    ole32,
    shell32,
)


# ---------------------------------------------------------------------------
# Paths / environment: must be set BEFORE importing main (it reads env at
# import time for DOWNLOAD_DIR / DATABASE_DIR defaults).
# ---------------------------------------------------------------------------
_FROZEN = bool(getattr(sys, 'frozen', False))


# The folder main.py and desktop.py are in (Backend/ in a checkout).
_BACKEND = Path(__file__).resolve().parents[3]


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
# Applied by _apply_staged_update() on the way out. Only a copy that is not
# installed the 4.0 way ever uses this; an installed one updates in place
# through its launcher (see dannify/layout.py).
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
    base = Path(getattr(sys, '_MEIPASS', _BACKEND))
    candidate = base / 'assets' / name
    if candidate.exists():
        return candidate
    return _BACKEND / 'assets' / name


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


def _reveal_in_explorer(target: Path) -> bool:
    """Open Explorer on the folder of ``target`` with it selected."""

    initialized = False
    try:
        # apartment-threaded, per worker thread; balanced below, since the
        # bridge reuses its threads for other calls
        initialized = ole32.CoInitializeEx(None, 0x2) in (0, 1)
        pidl = ctypes.c_void_p()
        if shell32.SHParseDisplayName(str(target), None, ctypes.byref(pidl), 0, None) == 0:
            shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0)
            ole32.CoTaskMemFree(pidl)
            return True
    except Exception:
        pass
    finally:
        if initialized:
            try:
                ole32.CoUninitialize()
            except Exception:
                pass
    try:
        import subprocess

        subprocess.Popen(f'explorer /select,"{target}"')
        return True
    except Exception:
        return False


def _install_crash_hooks() -> None:
    """Get anything that escapes into the log, and a trace of a hard crash.

    A packaged app has no console: an exception nobody caught in a worker
    thread, or Python itself going down, used to leave nothing behind at all.
    """

    import traceback

    global _crash_file
    try:
        import faulthandler

        _crash_file = open(_DATA_DIR / 'crash.log', 'a', encoding='utf-8')  # noqa: SIM115
        faulthandler.enable(_crash_file)
    except Exception:
        _crash_file = None

    before = sys.excepthook

    def on_uncaught(kind, exc, tb):
        if not issubclass(kind, KeyboardInterrupt):
            logger_print('uncaught: ' + ''.join(traceback.format_exception(kind, exc, tb)))
        before(kind, exc, tb)

    def on_thread(args):
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread else '?'
        logger_print(
            f'uncaught in thread {name}: '
            + ''.join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        )

    sys.excepthook = on_uncaught
    threading.excepthook = on_thread


_crash_file = None


# ---------------------------------------------------------------------------
# The window's browser, kept to being an app
# ---------------------------------------------------------------------------

# Switches that turn the embedded browser into something another program can
# drive or read from: a debugging port, extensions, security turned off.
_RISKY_SWITCHES = (
    'remote-debugging',
    'remote-allow-origins',
    'auto-open-devtools',
    'load-extension',
    'disable-web-security',
    'user-data-dir',
    'disk-cache-dir',
)


# Environment variables the WebView2 runtime reads, which a shortcut or a
# script could set to attach a debugger or swap the runtime for another.
_WEBVIEW_ENV = (
    'WEBVIEW2_BROWSER_EXECUTABLE_FOLDER',
    'WEBVIEW2_USER_DATA_FOLDER',
    'WEBVIEW2_RELEASE_CHANNEL_PREFERENCE',
    'WEBVIEW2_PIPE_FOR_SCRIPT_DEBUGGER',
    'WEBVIEW2_WAIT_FOR_SCRIPT_DEBUGGER',
)


def _webview_untampered() -> bool:
    """False when Windows has been told to open the app's browser up.

    The runtime takes extra switches from a machine or user policy as well as
    from the environment. The environment is ours to set (and is, below); a
    policy naming this program and handing it a debugging port is somebody
    trying to read the songs out of it.
    """

    for name in _WEBVIEW_ENV:
        os.environ.pop(name, None)
    if not _WIN:
        return True
    import winreg

    exe = Path(sys.executable).name.lower()
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            key = winreg.OpenKey(hive, r'Software\Policies\Microsoft\Edge\WebView2\AdditionalBrowserArguments')
        except OSError:
            continue
        with key:
            index = 0
            while True:
                try:
                    name, value, _kind = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                if str(name).lower() not in (exe, '*'):
                    continue
                if any(switch in str(value).lower() for switch in _RISKY_SWITCHES):
                    logger_print('refusing: a WebView2 policy adds', value)
                    return False
    return True


def _refuse_tampered() -> None:
    if not _WIN:
        return
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            'Dannify cannot open while this PC is set to let other programs '
            'control it (a WebView2 policy names Dannify). Remove that setting '
            'and open Dannify again.',
            APP_TITLE,
            0x10 | 0x40000,  # MB_ICONERROR | MB_TOPMOST
        )
    except Exception:
        pass


# Bumped when the window's cache has to be emptied once on the next start.
_CACHE_GENERATION = '2'


def _purge_window_cache() -> None:
    """Empty the window's cache once: earlier versions let audio into it.

    Before 4.4 a saved song reached the window marked "no-cache", which still
    lets the browser keep the decrypted bytes in its cache folder. Those
    copies go, once; nothing has been written there since.
    """

    marker = _WEBVIEW_STORAGE / '.cache-generation'
    try:
        if marker.read_text(encoding='utf-8').strip() == _CACHE_GENERATION:
            return
    except OSError:
        pass
    import shutil

    for sub in ('Cache', 'Code Cache', 'Service Worker', 'GPUCache'):
        for folder in (_WEBVIEW_STORAGE / 'EBWebView' / 'Default' / sub,):
            if folder.is_dir():
                shutil.rmtree(folder, ignore_errors=True)
    try:
        _WEBVIEW_STORAGE.mkdir(parents=True, exist_ok=True)
        marker.write_text(_CACHE_GENERATION, encoding='utf-8')
    except OSError:
        pass


def _lock_view_settings(core) -> None:  # noqa: ANN001
    """What a web page may do and an app should not."""

    for name, value in (
        # Ctrl and the wheel, or a pinch, zooming the page like a browser.
        # The interface size is a setting (and still applied, by the app).
        ('IsZoomControlEnabled', False),
        ('IsPinchZoomEnabled', False),
        # Offering to remember what is typed into the app's own fields.
        ('IsPasswordAutosaveEnabled', False),
        ('IsGeneralAutofillEnabled', False),
        # Swiping back and forward through pages.
        ('IsSwipeNavigationEnabled', False),
    ):
        try:
            setattr(core.Settings, name, value)
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
            'then open it again. If it keeps happening, restart your PC.',
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


class _State:
    """What the parts of the shell set and read while it runs."""

    # Applied by app._apply_staged_update() on the way out. Only a copy that
    # is not installed (no launcher) downloads an installer to stage.
    staged_update: Optional[Path] = None
    # The smallest window the interface fits in on this screen (see
    # places._fit_minimum).
    min_fit: tuple[int, int] = (MIN_W, MIN_H)
    # The bridge object, once the window exists.
    api = None


state = _State()
