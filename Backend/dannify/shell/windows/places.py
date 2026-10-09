"""Where things are: the library, window placement on screen, start with Windows."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Optional
from loguru import logger

from .base import (
    DEFAULT_H,
    DEFAULT_W,
    MIN_H,
    MIN_W,
    _FROZEN,
    _THEME_BG,
    logger_print,
    state,
)
from .win32 import (
    MONITORINFO,
    MONITOR_DEFAULTTONEAREST,
    RECT,
    WINDOWPLACEMENT,
    _WIN,
    _window_scale,
    _work_area_for,
    user32,
)


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


_RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


def _autostart_target() -> Optional[Path]:
    """What Windows should start at sign-in: the installed launcher, or
    nothing for a copy that is not installed (it would start the wrong thing
    after an update)."""

    if not (_WIN and _FROZEN):
        return None
    try:
        from dannify import layout

        launcher = layout.launcher()
    except Exception:
        return None
    return launcher if launcher is not None and launcher.is_file() else None


def _autostart_name() -> str:
    return 'Dannify' + os.environ.get('DANNIFY_INSTANCE', '')


def _autostart_state() -> dict:
    target = _autostart_target()
    if target is None:
        return {'available': False, 'on': False}
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _autostart_name())
        on = str(target).lower() in str(value).lower()
    except OSError:
        on = False
    return {'available': True, 'on': on}


def _set_autostart(on: bool) -> None:
    target = _autostart_target()
    if target is None:
        return
    import winreg

    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                # Minimized: at sign-in it should be there, not in the way.
                winreg.SetValueEx(key, _autostart_name(), 0, winreg.REG_SZ, f'"{target}" --minimized')
            else:
                try:
                    winreg.DeleteValue(key, _autostart_name())
                except FileNotFoundError:
                    pass
    except OSError:
        logger.opt(exception=True).warning('could not change starting with Windows')


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


# The smallest the window may be: MIN_W x MIN_H, but never more than the
# screen can show. A 1366 x 768 laptop at 150% scaling has well under 540
# logical pixels of height above the taskbar, and forcing 540 there put the
# player bar underneath the taskbar on every start.


def _fit_minimum(work_w: int, work_h: int) -> tuple[int, int]:
    state.min_fit = (max(480, min(MIN_W, work_w - 8)), max(360, min(MIN_H, work_h - 8)))
    return state.min_fit


def _clamp_to_visible(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    left, top, work_w, work_h = _work_area_near(x, y, w, h)
    # Leave a little room: a window sized to the exact work area can still
    # spill its shadow (and on some setups its last row of pixels) past the
    # edge, which is how the player bar ends up under the taskbar.
    min_w, min_h = _fit_minimum(work_w, work_h)
    w = max(min_w, min(w, work_w - 8))
    h = max(min_h, min(h, work_h - 8))
    x = max(left, min(x, left + work_w - w))
    y = max(top, min(y, top + work_h - h))
    return x, y, w, h


def _centered_geometry() -> tuple[int, int, int, int]:
    """Default (x, y, w, h): DEFAULT_W × DEFAULT_H centered on the primary work area."""
    left, top, work_w, work_h = _work_area_near(0, 0, 1, 1)
    min_w, min_h = _fit_minimum(work_w, work_h)
    w = min(DEFAULT_W, max(min_w, work_w - 80))
    h = min(DEFAULT_H, max(min_h, work_h - 80))
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
