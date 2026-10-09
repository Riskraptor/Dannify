"""The bridge calls the interface makes (frontend/src/desktop/bridge.js),
answered for a GTK window. Same names, same answers as on Windows."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from .. import core
from . import desktop, login, updater
from .gtk import Gdk, Gtk, find_webview, on_ui
from .mpris import Mpris
from .tray import Tray

_EDGES = {
    'n': 'NORTH', 's': 'SOUTH', 'e': 'EAST', 'w': 'WEST',
    'ne': 'NORTH_EAST', 'nw': 'NORTH_WEST', 'se': 'SOUTH_EAST', 'sw': 'SOUTH_WEST',
}


class LinuxApi:
    def __init__(self, prefs: dict, icon: Path, port: int, token: str) -> None:
        self._window = None  # pywebview's Window
        self._gtk = None  # its Gtk.ApplicationWindow
        self._view = None  # the WebKit view inside it
        self._icon = icon
        self._port, self._token = port, token
        self._native_frame = bool(prefs.get('native_frame'))
        self._native_frame_pref = self._native_frame
        self._close_to_tray = bool(prefs.get('close_to_tray', True))
        self._global_hotkeys = bool(prefs.get('global_hotkeys', False))
        self._hotkeys_taken: list[str] = []
        self._theme = 'light' if prefs.get('theme') == 'light' else 'dark'
        self._zoom = 1.0
        self._mini = False
        self._pre_mini: Optional[tuple[int, int, int, int, bool]] = None
        self._on_top = False
        self._fullscreen = False
        self._maximized = False
        self._minimized = False
        self._focused = True
        self._hidden = False
        self._quitting = False
        self._closing = False
        self._staged: Optional[Path] = None
        self._login: Optional[login.LoginWindow] = None
        self._restarting = False
        self._tray = Tray(icon, self._tray_command)
        self._mpris = Mpris(self._media, self.win_show, self.app_quit,
                           os.environ.get('DANNIFY_INSTANCE', ''))
        self._hotkeys = desktop.Hotkeys(self._media)

    # --- plumbing ---------------------------------------------------------
    def _attach(self, window) -> None:  # noqa: ANN001
        """GTK thread, before the window first shows."""

        self._window = window
        self._gtk = window.native
        self._view = find_webview(self._gtk)
        try:
            self._gtk.set_icon_from_file(str(self._icon))
        except Exception:
            pass
        self._gtk.set_size_request(core.MIN_W, core.MIN_H)
        self._gtk.connect('window-state-event', self._on_window_state)
        self._gtk.connect('focus-in-event', lambda *_: self._set_focus(True))
        self._gtk.connect('focus-out-event', lambda *_: self._set_focus(False))
        desktop.prefer_dark(self._theme == 'dark')
        if self._close_to_tray:
            self._tray.install()
        if self._global_hotkeys:
            self._hotkeys_taken = self._hotkeys.register()
        self._mpris.start()

    def _set_focus(self, on: bool) -> bool:
        self._focused = on
        self._push_state()
        return False

    def _on_window_state(self, _widget, event) -> bool:  # noqa: ANN001
        state = event.new_window_state
        self._maximized = bool(state & Gdk.WindowState.MAXIMIZED)
        self._minimized = bool(state & Gdk.WindowState.ICONIFIED)
        self._fullscreen = bool(state & Gdk.WindowState.FULLSCREEN)
        self._push_state()
        return False

    def _push_state(self) -> None:
        if self._window is None or self._closing:
            return
        state = json.dumps(self.win_state())
        self._eval(f'window.__dannifyWindowState && window.__dannifyWindowState({state})')

    def _eval(self, script: str) -> None:
        window = self._window

        def run() -> None:
            try:
                window.evaluate_js(script)
            except Exception:
                pass

        if window is not None and not self._closing:
            threading.Thread(target=run, daemon=True).start()

    def _media(self, cmd: str) -> None:
        """A command from the tray, the media keys or a shortcut."""

        safe = ''.join(ch for ch in str(cmd) if ch.isalnum() or ch in ':.-')
        self._eval(f"window.__dannifyMedia && window.__dannifyMedia('{safe}')")

    def _tray_command(self, cmd: str) -> None:
        if cmd == 'show':
            self.win_show()
        elif cmd == 'quit':
            self.app_quit()
        else:
            self._media(cmd)

    # --- window -----------------------------------------------------------
    def win_state(self) -> dict:
        return {
            'platform': 'linux',
            'maximized': self._maximized and not self._fullscreen,
            'minimized': self._minimized,
            'fullscreen': self._fullscreen,
            'focused': self._focused,
            'mini': self._mini,
            'onTop': self._on_top,
            'nativeFrame': self._native_frame,
            'nativeFramePref': self._native_frame_pref,
            'closeToTray': self._close_to_tray and self._tray.available,
            'trayAvailable': self._tray.available or self._close_to_tray,
            'globalHotkeys': self._global_hotkeys,
            'hotkeysTaken': list(self._hotkeys_taken),
            'autostart': desktop.autostart_state(),
        }

    def win_minimize(self) -> None:
        on_ui(lambda: self._gtk.iconify())

    def win_toggle_maximize(self) -> None:
        def run() -> None:
            if self._maximized:
                self._gtk.unmaximize()
            else:
                self._gtk.maximize()
        if not self._mini:
            on_ui(run)

    def win_close(self) -> None:
        on_ui(lambda: self._gtk.close())

    def win_set_max_button(self, rect: Any = None) -> None:
        return None  # Windows' snap layouts only

    def win_start_drag(self) -> None:
        def run() -> None:
            seat = Gdk.Display.get_default().get_default_seat()
            _, x, y = seat.get_pointer().get_position()
            self._gtk.begin_move_drag(1, x, y, Gtk.get_current_event_time())
        if not self._native_frame:
            on_ui(run)

    def win_start_resize(self, edge: str) -> None:
        name = _EDGES.get(str(edge or '').lower())
        if not name or self._native_frame or self._maximized:
            return

        def run() -> None:
            seat = Gdk.Display.get_default().get_default_seat()
            _, x, y = seat.get_pointer().get_position()
            self._gtk.begin_resize_drag(getattr(Gdk.WindowEdge, name), 1, x, y,
                                        Gtk.get_current_event_time())
        on_ui(run)

    def win_system_menu(self) -> None:
        """The window menu a title bar's right click gives."""

        def run() -> None:
            menu = Gtk.Menu()
            for label, action in (
                ('Minimize', self._gtk.iconify),
                ('Restore' if self._maximized else 'Maximize', self.win_toggle_maximize),
                (None, None),
                ('Close', self._gtk.close),
            ):
                if label is None:
                    menu.append(Gtk.SeparatorMenuItem())
                    continue
                item = Gtk.MenuItem(label=label)
                item.connect('activate', lambda _w, a=action: a())
                menu.append(item)
            menu.show_all()
            menu.attach_to_widget(self._gtk, None)
            menu.popup_at_pointer(None)
        on_ui(run)

    def win_toggle_fullscreen(self) -> dict:
        if not self._mini:
            on_ui(lambda: self._gtk.unfullscreen() if self._fullscreen else self._gtk.fullscreen(), wait=True)
            time.sleep(0.1)
        return self.win_state()

    def win_set_on_top(self, on: bool) -> dict:
        self._on_top = bool(on)
        on_ui(lambda: self._gtk.set_keep_above(self._on_top), wait=True)
        self._push_state()
        return self.win_state()

    def win_set_mini(self, on: bool) -> dict:
        """The compact player: the same window, small and on top."""

        on = bool(on)
        if on == self._mini or self._gtk is None:
            return self.win_state()

        def enter() -> None:
            if self._fullscreen:
                self._gtk.unfullscreen()
            x, y = self._gtk.get_position()
            w, h = self._gtk.get_size()
            self._pre_mini = (x, y, w, h, self._maximized)
            if self._maximized:
                self._gtk.unmaximize()
            self._gtk.set_size_request(core.MINI_W, core.MINI_H)
            self._gtk.resize(core.MINI_W, core.MINI_H)
            pos = core.read_prefs().get('mini_pos')
            if isinstance(pos, list) and len(pos) == 2:
                self._gtk.move(int(pos[0]), int(pos[1]))
            self._gtk.set_keep_above(True)

        def leave() -> None:
            x, y = self._gtk.get_position()
            core.write_prefs({'mini_pos': [x, y]})
            self._gtk.set_keep_above(False)
            self._apply_min_size()
            if self._pre_mini:
                px, py, pw, ph, maximized = self._pre_mini
                self._gtk.resize(pw, ph)
                self._gtk.move(px, py)
                if maximized:
                    self._gtk.maximize()

        self._mini = on
        self._on_top = on
        on_ui(enter if on else leave, wait=True)
        self._push_state()
        return self.win_state()

    def win_set_mini_size(self, height: float) -> None:
        """Grow or shrink the compact player when its panel opens or closes."""

        if not self._mini or self._gtk is None:
            return
        want = int(max(core.MINI_H, min(float(height or core.MINI_H), core.MINI_MAX_H)))

        def run() -> None:
            w, _ = self._gtk.get_size()
            self._gtk.set_size_request(core.MINI_W, want)
            self._gtk.resize(w, want)
        on_ui(run)

    def _apply_min_size(self) -> None:
        """GTK thread. The smallest window the interface still fits at this zoom."""

        floor_w, floor_h = int(core.MIN_W * self._zoom), int(core.MIN_H * self._zoom)
        self._gtk.set_size_request(floor_w, floor_h)
        w, h = self._gtk.get_size()
        if not (self._maximized or self._fullscreen) and (w < floor_w or h < floor_h):
            self._gtk.resize(max(w, floor_w), max(h, floor_h))

    def win_set_zoom(self, factor: float) -> None:
        """Interface size, and a minimum window that grows with it, so a zoomed
        interface never drops into the narrow layout meant for phones."""

        try:
            self._zoom = max(0.5, min(2.0, float(factor)))
        except (TypeError, ValueError):
            return

        def run() -> None:
            if self._view is not None:
                self._view.set_zoom_level(self._zoom)
            if not self._mini:
                self._apply_min_size()
        on_ui(run)

    def win_set_native_frame(self, on: bool) -> dict:
        self._native_frame_pref = bool(on)
        core.write_prefs({'native_frame': self._native_frame_pref})
        return self.win_state()

    def win_show(self) -> None:
        def run() -> None:
            self._hidden = False
            self._gtk.show()
            self._gtk.deiconify()
            self._gtk.present()
            if not self._close_to_tray:
                self._tray.dispose()
        on_ui(run)
        self._push_state()

    def _hide_to_tray(self) -> bool:
        """GTK thread. True when the window went to the tray."""

        if not self._tray.install():
            return False
        self._hidden = True
        self._gtk.hide()
        return True

    # --- tray, shortcuts, autostart -------------------------------------------
    def tray_set(self, options: dict) -> dict:
        if isinstance(options, dict) and 'closeToTray' in options:
            self._close_to_tray = bool(options['closeToTray'])
            core.write_prefs({'close_to_tray': self._close_to_tray})
            if self._close_to_tray:
                on_ui(self._tray.install, wait=True)
            elif not self._hidden:
                on_ui(self._tray.dispose, wait=True)
        self._push_state()
        return self.win_state()

    def tray_labels(self, labels: dict) -> None:
        merged = core.merge_labels(self._tray.labels, labels)
        on_ui(lambda: self._tray.apply_labels(merged))

    def app_set_global_hotkeys(self, on: bool) -> dict:
        self._global_hotkeys = bool(on)
        core.write_prefs({'global_hotkeys': self._global_hotkeys})

        def run() -> None:
            if self._global_hotkeys:
                self._hotkeys_taken = self._hotkeys.register()
            else:
                self._hotkeys.unregister()
                self._hotkeys_taken = []
        on_ui(run, wait=True)
        self._push_state()
        return self.win_state()

    def app_set_autostart(self, on: bool) -> dict:
        desktop.set_autostart(bool(on))
        self._push_state()
        return self.win_state()

    def app_set_theme(self, theme: str) -> None:
        self._theme = 'light' if theme == 'light' else 'dark'
        core.write_prefs({'theme': self._theme})

        def run() -> None:
            desktop.prefer_dark(self._theme == 'dark')
            if self._view is not None:
                color = Gdk.RGBA()
                color.parse(core.THEME_BG[self._theme])
                self._view.set_background_color(color)
        on_ui(run)

    # --- the shell ------------------------------------------------------------
    def shell_open_sound_settings(self) -> bool:
        return desktop.open_sound_settings()

    def shell_reveal(self, rel_path: str) -> bool:
        target = core.library_path(rel_path)
        return bool(target and target.exists() and desktop.reveal(target))

    def shell_open_library(self) -> bool:
        base = core.library_path('')
        return bool(base and desktop.open_folder(base))

    def shell_open_external(self, url: str) -> bool:
        url = str(url or '')
        return url.startswith(('https://', 'http://')) and desktop.open_url(url)

    def clipboard_read(self) -> str:
        def run() -> str:
            return Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text() or ''
        return on_ui(run, wait=True) or ''

    def taskbar_progress(self, value: float, mode: str = 'normal') -> None:
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        desktop.launcher_progress(value, str(mode) != 'none' and value > 0)

    def taskbar_playback(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        playing = bool(payload.get('playing'))
        has_track = bool(payload.get('hasTrack'))
        title = str(payload.get('title') or '')[:200]
        artist = str(payload.get('artist') or '')[:200]
        changes = {
            'playing': playing, 'has_track': has_track, 'title': title, 'artist': artist,
            'album': str(payload.get('album') or '')[:200],
            'duration': _number(payload.get('duration')),
            'key': str(payload.get('key') or f'{title}|{artist}'),
        }
        if 'position' in payload:
            changes['position'] = _number(payload.get('position'))
        cover = str(payload.get('cover') or '')

        def run() -> None:
            self._tray.set_track(title, artist, playing, has_track)
            self._mpris.update(**changes)
        on_ui(run)
        threading.Thread(target=self._set_art, args=(cover, changes['key']), daemon=True).start()

    def _set_art(self, cover: str, key: str) -> None:
        """The cover for the media panel, as an address the desktop can open.

        Covers from YouTube are plain https. The library's own come from this
        app's server, which answers only with the session key, so those are
        fetched here and handed over as a file.
        """

        art = ''
        if cover.startswith('https://'):
            art = cover
        elif cover.startswith('/'):
            folder = core.DATA_DIR / 'media-art'
            target = folder / (hashlib.sha1(cover.encode()).hexdigest()[:20] + '.img')
            try:
                if not target.is_file():
                    folder.mkdir(parents=True, exist_ok=True)
                    for old in sorted(folder.glob('*.img'), key=lambda p: p.stat().st_mtime)[:-40]:
                        old.unlink(missing_ok=True)
                    request = urllib.request.Request(
                        f'http://127.0.0.1:{self._port}{cover}', headers={'X-Dannify-Key': self._token},
                    )
                    with urllib.request.urlopen(request, timeout=10) as resp:
                        target.write_bytes(resp.read(8 * 1024 * 1024))
                art = target.as_uri()
            except Exception:
                logger.opt(exception=True).debug('no cover for the media panel')
        if self._mpris.state.get('key') == key:
            on_ui(lambda: self._mpris.update(art=art))

    # --- account --------------------------------------------------------------
    def account_sign_in(self) -> dict:
        """Show the Google sign-in window and keep the resulting session.

        Runs on a bridge worker thread, so waiting here is fine: the window
        lives on the GTK thread and the app stays responsive throughout.
        """

        if self._login is not None:
            return {'signed_in': False, 'error': ''}
        from dannify import account

        self._login = login.LoginWindow(self._theme, str(self._icon))
        try:
            cookies = self._login.run()
            error = self._login.error
        finally:
            self._login = None
        if not cookies:
            return {'signed_in': False, 'error': error}
        try:
            return account.sign_in(cookies)
        except Exception as exc:
            logger.opt(exception=True).info('sign-in rejected')
            return {'signed_in': False, 'error': str(exc)}

    def account_clear_session(self) -> bool:
        return login.clear_session()

    # --- quitting, restarting, updating ---------------------------------------
    def app_quit(self) -> None:
        self._quitting = True

        def run() -> None:
            if self._hidden:
                self._window.destroy()
            else:
                self._gtk.close()
        on_ui(run)

    def app_restart(self) -> bool:
        """Start a new copy that waits for this one to go, then go."""

        env = dict(os.environ, DANNIFY_WAIT_PID=str(os.getpid()))
        try:
            subprocess.Popen(core.relaunch_command(), env=env, start_new_session=True,  # noqa: S603
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError:
            logger.opt(exception=True).info('restart failed')
            return False
        self._restarting = True
        threading.Timer(0.25, self.app_quit).start()
        return True

    def app_install_update(self, installer: str) -> bool:
        """Install the downloaded update now, then come back as the new version."""

        path = core.vetted_update(installer, '.deb')
        if path is None or not updater.install_deb(path):
            return False
        self._staged = None
        return self.app_restart()

    def app_stage_update(self, installer: str) -> bool:
        """Keep the update for when the app closes (the system asks for the
        password then), the way a browser updates on its way out."""

        path = core.vetted_update(installer, '.deb')
        if path is None:
            return False
        self._staged = path
        return True

    def app_clear_staged_update(self) -> bool:
        self._staged = None
        return True

    def _install_staged(self) -> None:
        """After the window closed for good: the update waiting for it, if any."""

        if self._staged is not None and not self._restarting:
            updater.install_deb(self._staged)


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number > 0 and number == number else 0.0
