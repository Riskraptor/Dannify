"""The bridge calls the interface makes (frontend/src/desktop/bridge.js),
answered for a Cocoa window. Same names, same answers as on Windows.

The window keeps macOS's own traffic-light buttons: the page runs under a
transparent title bar (a full-size content view), so win_state reports
nativeFrame and the interface leaves room for them instead of drawing its own.
"""

from __future__ import annotations

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
from .cocoa import AppKit, Foundation, hex_color, on_main
from .nowplaying import NowPlaying
from .tray import Tray

_FULLSCREEN_MASK = 1 << 14  # NSWindowStyleMaskFullScreen
_FULL_SIZE_CONTENT = 1 << 15  # NSWindowStyleMaskFullSizeContentView
_TEXTURED = 1 << 8  # what pywebview adds for a frameless window; not wanted
_FULLSCREEN_PRIMARY = 1 << 7  # NSWindowCollectionBehaviorFullScreenPrimary
_BUTTONS = (0, 1, 2)  # close, minimise, zoom
# The page's own title bar (--titlebar-h in frontend/src/index.css) is taller
# than macOS's 28 points; the buttons are centred in it instead.
_BAR_HEIGHT = 44
_BUTTONS_X = 14
_NOTES = (
    'NSWindowDidBecomeKeyNotification', 'NSWindowDidResignKeyNotification',
    'NSWindowDidMiniaturizeNotification', 'NSWindowDidDeminiaturizeNotification',
    'NSWindowDidEnterFullScreenNotification', 'NSWindowDidExitFullScreenNotification',
    'NSWindowDidEndLiveResizeNotification', 'NSWindowDidResizeNotification',
)


class MacApi:
    def __init__(self, prefs: dict, port: int, token: str, app: Optional[Path]) -> None:
        self._window = None  # pywebview's Window
        self._ns = None  # its NSWindow
        self._view = None  # the WKWebView inside it
        self._app = app  # the Dannify.app this copy runs from, if any
        self._port, self._token = port, token
        self._native_frame_pref = bool(prefs.get('native_frame'))
        self._close_to_tray = bool(prefs.get('close_to_tray', True))
        self._global_hotkeys = bool(prefs.get('global_hotkeys', False))
        self._hotkeys_taken: list[str] = []
        self._theme = 'light' if prefs.get('theme') == 'light' else 'dark'
        self._zoom = 1.0
        self._mini = False
        self._pre_mini: Optional[tuple] = None
        self._on_top = False
        self._fullscreen = False
        self._maximized = False
        self._minimized = False
        self._focused = True
        self._hidden = False
        self._hide_after_fullscreen = False
        self._fullscreen_changed = threading.Event()
        self._quitting = False
        self._closing = False
        self._restarting = False
        self._staged: Optional[Path] = None
        self._login: Optional[login.LoginWindow] = None
        self._art_for: tuple = ()
        self._observers: list = []
        self._tray = Tray(self._tray_command)
        self._now_playing = NowPlaying(self._media)
        self._hotkeys = desktop.Hotkeys(self._media)
        self._dock = desktop.DockProgress()

    # --- plumbing ---------------------------------------------------------
    def _attach(self, window, hidden: bool, frame: Optional[list]) -> None:  # noqa: ANN001
        """Main thread, before the window first shows."""

        from webview.platforms.cocoa import BrowserView

        self._window = window
        ns = self._ns = window.native
        browser = BrowserView.instances.get(window.uid)
        self._view = browser.webview if browser is not None else None
        self._hidden = hidden

        # The page fills the window, title bar included, under macOS's own
        # buttons. pywebview hides those for a frameless window; they come back.
        ns.setStyleMask_((ns.styleMask() | _FULL_SIZE_CONTENT) & ~_TEXTURED)
        ns.setTitlebarAppearsTransparent_(True)
        ns.setTitleVisibility_(AppKit.NSWindowTitleHidden)
        self._show_buttons(True)
        ns.setCollectionBehavior_(ns.collectionBehavior() | _FULLSCREEN_PRIMARY)
        ns.setMinSize_(AppKit.NSMakeSize(core.MIN_W, core.MIN_H))
        self._restore_frame(frame)
        self._place_buttons()

        center = Foundation.NSNotificationCenter.defaultCenter()
        queue = Foundation.NSOperationQueue.mainQueue()
        for name in _NOTES:
            self._observers.append(center.addObserverForName_object_queue_usingBlock_(
                getattr(AppKit, name), ns, queue, self._on_window_note))

        desktop.set_appearance(self._theme == 'dark')
        if self._close_to_tray:
            self._tray.install()
        if self._global_hotkeys:
            self._hotkeys_taken = self._hotkeys.register()
        self._now_playing.start()

    def _restore_frame(self, frame: Optional[list]) -> None:
        """Main thread. Where the window was last time, if that is still on a
        screen (a monitor may have gone since)."""

        try:
            x, y, w, h = (float(v) for v in frame)
            rect = AppKit.NSMakeRect(x, y, max(w, core.MIN_W), max(h, core.MIN_H))
        except (TypeError, ValueError):
            self._ns.center()
            return
        if any(AppKit.NSIntersectsRect(s.visibleFrame(), rect) for s in AppKit.NSScreen.screens()):
            self._ns.setFrame_display_(rect, False)
        else:
            self._ns.center()

    def _frame(self) -> list:
        f = self._ns.frame()
        return [round(f.origin.x), round(f.origin.y), round(f.size.width), round(f.size.height)]

    def _save_geometry(self) -> None:
        """Main thread."""

        if self._ns is None or self._mini or self._fullscreen or self._hidden:
            return
        try:
            core.write_prefs({'mac_frame': self._frame()})
        except Exception:
            pass

    def _show_buttons(self, on: bool) -> None:
        for kind in _BUTTONS:
            button = self._ns.standardWindowButton_(kind)
            if button is not None:
                button.setHidden_(not on)

    def _place_buttons(self) -> None:
        """Main thread. The window's buttons, centred in the page's title bar.

        AppKit lays the title bar out again on every resize and on leaving
        full screen, so this runs after each of those too.
        """

        ns = self._ns
        if ns is None or self._fullscreen or self._mini:
            return
        buttons = [ns.standardWindowButton_(kind) for kind in _BUTTONS]
        if any(b is None for b in buttons) or buttons[0].superview() is None:
            return
        bar_view = buttons[0].superview()
        container = bar_view.superview()
        if container is None:
            return
        bar = container.frame()
        bar.size.height = _BAR_HEIGHT
        bar.origin.y = ns.frame().size.height - _BAR_HEIGHT
        container.setFrame_(bar)
        step = buttons[1].frame().origin.x - buttons[0].frame().origin.x
        for i, button in enumerate(buttons):
            size = button.frame().size
            # Centred both ways up, whichever way the bar counts.
            y = (bar_view.frame().size.height - size.height) / 2
            button.setFrameOrigin_(AppKit.NSMakePoint(_BUTTONS_X + i * step, y))

    def _on_window_note(self, note) -> None:  # noqa: ANN001
        """Main thread: the window changed; tell the page if that shows."""

        name = str(note.name())
        ns = self._ns
        if ns is None:
            return
        if 'FullScreen' in name:
            self._fullscreen_changed.set()
            if 'Exit' in name and self._hide_after_fullscreen:
                self._hide_after_fullscreen = False
                ns.orderOut_(None)
        before = (self._focused, self._minimized, self._fullscreen, self._maximized)
        self._focused = bool(ns.isKeyWindow())
        self._minimized = bool(ns.isMiniaturized())
        self._fullscreen = bool(ns.styleMask() & _FULLSCREEN_MASK)
        self._maximized = bool(ns.isZoomed()) and not self._fullscreen and not self._mini
        self._place_buttons()
        if (self._focused, self._minimized, self._fullscreen, self._maximized) != before:
            self._push_state()

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
        """A command from the menu bar, the media keys or a shortcut."""

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
            'platform': 'macos',
            'maximized': self._maximized and not self._fullscreen,
            'minimized': self._minimized,
            'fullscreen': self._fullscreen,
            'focused': self._focused,
            'mini': self._mini,
            'onTop': self._on_top,
            # macOS always draws the window's buttons itself.
            'nativeFrame': True,
            'nativeFramePref': self._native_frame_pref,
            'closeToTray': self._close_to_tray,
            'trayAvailable': True,
            'globalHotkeys': self._global_hotkeys,
            'hotkeysTaken': list(self._hotkeys_taken),
            'autostart': desktop.autostart_state(),
        }

    def win_minimize(self) -> None:
        on_main(lambda: self._ns.miniaturize_(None))

    def win_toggle_maximize(self) -> None:
        """What a double click on a title bar does here: the user's own choice
        in System Settings (zoom, minimise or nothing)."""

        def run() -> None:
            action = str(Foundation.NSUserDefaults.standardUserDefaults()
                         .stringForKey_('AppleActionOnDoubleClick') or 'Maximize')
            if action == 'Minimize':
                self._ns.miniaturize_(None)
            elif action != 'None':
                self._ns.zoom_(None)
        if not self._mini and not self._fullscreen:
            on_main(run)

    def win_close(self) -> None:
        on_main(lambda: self._ns.performClose_(None))

    def win_set_max_button(self, rect: Any = None) -> None:
        return None  # Windows' snap layouts only

    def win_start_drag(self) -> None:
        """Move the window with the mouse, from the page's title bar."""

        def run() -> None:
            ns = self._ns
            if ns is None or self._fullscreen or not (AppKit.NSEvent.pressedMouseButtons() & 1):
                return
            # AppKit's own window drag, started from a press where the mouse
            # is now: snapping to screen edges and Spaces work as for any title bar.
            press = AppKit.NSEvent.mouseEventWithType_location_modifierFlags_timestamp_windowNumber_context_eventNumber_clickCount_pressure_(  # noqa: E501
                AppKit.NSEventTypeLeftMouseDown, ns.mouseLocationOutsideOfEventStream(), 0,
                Foundation.NSProcessInfo.processInfo().systemUptime(), ns.windowNumber(),
                None, 0, 1, 1.0)
            if press is not None:
                ns.performWindowDragWithEvent_(press)
        on_main(run)

    def win_start_resize(self, edge: str) -> None:
        return None  # the window's own edges resize it

    def win_system_menu(self) -> None:
        return None  # a macOS title bar has no menu

    def _wait_for_fullscreen(self, toggle: bool) -> None:
        """Worker thread. Toggle full screen (if asked) and wait for the
        animation to finish, so what comes next sees the final frame."""

        self._fullscreen_changed.clear()
        if toggle:
            on_main(lambda: self._ns.toggleFullScreen_(None))
        self._fullscreen_changed.wait(2.0)
        time.sleep(0.05)

    def win_toggle_fullscreen(self) -> dict:
        if not self._mini and self._ns is not None:
            self._wait_for_fullscreen(True)
        return self.win_state()

    def win_set_on_top(self, on: bool) -> dict:
        self._on_top = bool(on)
        level = AppKit.NSFloatingWindowLevel if self._on_top else AppKit.NSNormalWindowLevel
        on_main(lambda: self._ns.setLevel_(level), wait=True)
        self._push_state()
        return self.win_state()

    def win_set_mini(self, on: bool) -> dict:
        """The compact player: the same window, small and floating."""

        on = bool(on)
        if on == self._mini or self._ns is None:
            return self.win_state()
        if on and self._fullscreen:
            self._wait_for_fullscreen(True)

        def enter() -> None:
            ns = self._ns
            self._pre_mini = (self._frame(), bool(ns.isZoomed()))
            visible = (ns.screen() or AppKit.NSScreen.mainScreen()).visibleFrame()
            pos = core.read_prefs().get('mac_mini_pos')
            try:
                x, y = float(pos[0]), float(pos[1])
                rect = AppKit.NSMakeRect(x, y, core.MINI_W, core.MINI_H)
                if not any(AppKit.NSIntersectsRect(s.visibleFrame(), rect)
                           for s in AppKit.NSScreen.screens()):
                    raise ValueError('off screen')
            except (TypeError, ValueError, IndexError):
                # The bottom-right corner, out of the way, the first time.
                rect = AppKit.NSMakeRect(
                    visible.origin.x + visible.size.width - core.MINI_W - 16,
                    visible.origin.y + 16, core.MINI_W, core.MINI_H)
            self._show_buttons(False)
            ns.setMinSize_(AppKit.NSMakeSize(core.MINI_W, core.MINI_H))
            ns.setFrame_display_animate_(rect, True, True)
            ns.setLevel_(AppKit.NSFloatingWindowLevel)

        def leave() -> None:
            ns = self._ns
            f = ns.frame()
            core.write_prefs({'mac_mini_pos': [round(f.origin.x), round(f.origin.y)]})
            ns.setLevel_(AppKit.NSNormalWindowLevel)
            self._show_buttons(True)
            self._place_buttons()
            if self._pre_mini:
                (x, y, w, h), zoomed = self._pre_mini
                ns.setFrame_display_animate_(AppKit.NSMakeRect(x, y, w, h), True, True)
                if zoomed and not ns.isZoomed():
                    ns.zoom_(None)
            self._apply_min_size()

        self._mini = on
        self._on_top = on
        on_main(enter if on else leave, wait=True)
        self._push_state()
        return self.win_state()

    def win_set_mini_size(self, height: float) -> None:
        """Grow or shrink the compact player when its panel opens or closes.

        The bottom edge stays put, so it unfolds upwards: it usually sits in
        the bottom-right corner, and growing downwards would push it off the
        screen.
        """

        if not self._mini or self._ns is None:
            return
        try:
            want = int(max(core.MINI_H, min(float(height or core.MINI_H), core.MINI_MAX_H)))
        except (TypeError, ValueError):
            return

        def run() -> None:
            ns = self._ns
            f = ns.frame()
            visible = (ns.screen() or AppKit.NSScreen.mainScreen()).visibleFrame()
            y = f.origin.y
            top = visible.origin.y + visible.size.height
            if y + want > top:
                # Not enough room above: grow downwards instead.
                y = max(visible.origin.y, top - want)
            # The minimum has to come off first or the shrink is refused.
            ns.setMinSize_(AppKit.NSMakeSize(core.MINI_W, core.MINI_H))
            ns.setFrame_display_animate_(AppKit.NSMakeRect(f.origin.x, y, f.size.width, want), True, True)
            ns.setMinSize_(AppKit.NSMakeSize(core.MINI_W, want))
        on_main(run)

    def _apply_min_size(self) -> None:
        """Main thread. The smallest window the interface still fits at this zoom."""

        ns = self._ns
        floor_w, floor_h = core.MIN_W * self._zoom, core.MIN_H * self._zoom
        ns.setMinSize_(AppKit.NSMakeSize(floor_w, floor_h))
        f = ns.frame()
        if not (self._fullscreen or ns.isZoomed()) and (f.size.width < floor_w or f.size.height < floor_h):
            w, h = max(f.size.width, floor_w), max(f.size.height, floor_h)
            # Grown from the top-left corner, as a resize by hand would.
            ns.setFrame_display_(
                AppKit.NSMakeRect(f.origin.x, f.origin.y + f.size.height - h, w, h), True)

    def win_set_zoom(self, factor: float) -> None:
        """Interface size, and a minimum window that grows with it, so a zoomed
        interface never drops into the narrow layout meant for phones."""

        try:
            self._zoom = max(0.5, min(2.0, float(factor)))
        except (TypeError, ValueError):
            return

        def run() -> None:
            view = self._view
            if view is not None:
                if view.respondsToSelector_('setPageZoom:'):
                    view.setPageZoom_(self._zoom)
                else:
                    view.setMagnification_centeredAtPoint_(self._zoom, AppKit.NSMakePoint(0, 0))
            if not self._mini:
                self._apply_min_size()
        on_main(run)

    def win_set_native_frame(self, on: bool) -> dict:
        # Kept for the other platforms' sake; a Mac window always has its own.
        self._native_frame_pref = bool(on)
        core.write_prefs({'native_frame': self._native_frame_pref})
        return self.win_state()

    def win_show(self) -> None:
        def run() -> None:
            ns = self._ns
            self._hidden = False
            if ns.isMiniaturized():
                ns.deminiaturize_(None)
            ns.makeKeyAndOrderFront_(None)
            AppKit.NSApp().activateIgnoringOtherApps_(True)
            if not self._close_to_tray:
                self._tray.dispose()
        if self._ns is not None:
            on_main(run)
            self._push_state()

    def _hide_to_tray(self) -> bool:
        """Main thread. True when the window went away and the app plays on."""

        if not self._tray.install():
            return False
        self._save_geometry()
        self._hidden = True
        if self._fullscreen:
            # Hidden straight from full screen, it would leave its Space
            # behind, black; out of full screen first.
            self._hide_after_fullscreen = True
            self._ns.toggleFullScreen_(None)
        else:
            self._ns.orderOut_(None)
        return True

    # --- tray, shortcuts, login items -------------------------------------
    def tray_set(self, options: dict) -> dict:
        if isinstance(options, dict) and 'closeToTray' in options:
            self._close_to_tray = bool(options['closeToTray'])
            core.write_prefs({'close_to_tray': self._close_to_tray})
            if self._close_to_tray:
                on_main(self._tray.install, wait=True)
            elif not self._hidden:
                on_main(self._tray.dispose, wait=True)
        self._push_state()
        return self.win_state()

    def tray_labels(self, labels: dict) -> None:
        merged = core.merge_labels(self._tray.labels, labels)
        on_main(lambda: self._tray.apply_labels(merged))

    def app_set_global_hotkeys(self, on: bool) -> dict:
        self._global_hotkeys = bool(on)
        core.write_prefs({'global_hotkeys': self._global_hotkeys})

        def run() -> None:
            if self._global_hotkeys:
                self._hotkeys_taken = self._hotkeys.register()
            else:
                self._hotkeys.unregister()
                self._hotkeys_taken = []
        on_main(run, wait=True)
        self._push_state()
        return self.win_state()

    def app_set_autostart(self, on: bool) -> dict:
        desktop.set_autostart(bool(on), self._app)
        self._push_state()
        return self.win_state()

    def app_set_theme(self, theme: str) -> None:
        self._theme = 'light' if theme == 'light' else 'dark'
        core.write_prefs({'theme': self._theme})

        def run() -> None:
            desktop.set_appearance(self._theme == 'dark')
            color = hex_color(core.THEME_BG[self._theme])
            if self._ns is not None:
                self._ns.setBackgroundColor_(color)
            view = self._view
            if view is not None and view.respondsToSelector_('setUnderPageBackgroundColor:'):
                view.setUnderPageBackgroundColor_(color)
        on_main(run)

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
        return desktop.clipboard_text()

    def taskbar_progress(self, value: float, mode: str = 'normal') -> None:
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        visible = str(mode) != 'none' and value > 0
        on_main(lambda: self._dock.set(value, visible))

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
            self._now_playing.update(**changes)
        on_main(run)
        if has_track and cover and self._art_for != (changes['key'], cover):
            self._art_for = (changes['key'], cover)
            threading.Thread(target=self._set_art, args=(cover, changes['key']), daemon=True).start()

    def _set_art(self, cover: str, key: str) -> None:
        """The cover for Now Playing, fetched here: it wants the picture
        itself, not an address. The library's own covers come from this
        app's server, which answers only with the session key."""

        if cover.startswith('https://'):
            request = urllib.request.Request(cover, headers={'User-Agent': 'Dannify'})
        elif cover.startswith('/'):
            request = urllib.request.Request(f'http://127.0.0.1:{self._port}{cover}',
                                             headers={'X-Dannify-Key': self._token})
        else:
            return
        try:
            with urllib.request.urlopen(request, timeout=10) as resp:  # noqa: S310
                data = resp.read(8 * 1024 * 1024)
        except Exception:
            logger.opt(exception=True).debug('no cover for Now Playing')
            return
        on_main(lambda: self._now_playing.set_art(key, data))

    # --- account --------------------------------------------------------------
    def account_sign_in(self) -> dict:
        """Show the Google sign-in window and keep the resulting session.

        Runs on a bridge worker thread, so waiting here is fine: the window
        lives on the main thread and the app stays responsive throughout.
        """

        if self._login is not None:
            return {'signed_in': False, 'error': ''}
        from dannify import account

        self._login = login.LoginWindow(self._theme)
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
        """Quit for real, as Quit in the Dannify menu does, through the app
        delegate's applicationShouldTerminate: and its clean-up."""

        self._quitting = True
        on_main(lambda: AppKit.NSApp().terminate_(None))

    def app_restart(self) -> bool:
        """Start a new copy that waits for this one to go, then go."""

        env = updater.child_environment()
        env['DANNIFY_WAIT_PID'] = str(os.getpid())
        command = core.relaunch_command(env)
        try:
            if command[0] == '/usr/bin/open':
                # Waited for: if LaunchServices refuses, this copy stays.
                done = subprocess.run(command, env=env, capture_output=True, timeout=30)  # noqa: S603
                if done.returncode != 0:
                    raise OSError(done.stderr.decode(errors='replace')[-300:])
            else:
                subprocess.Popen(command, env=env, start_new_session=True,  # noqa: S603
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            logger.opt(exception=True).info('restart failed')
            return False
        self._restarting = True
        threading.Timer(0.25, self.app_quit).start()
        return True

    def app_install_update(self, installer: str) -> bool:
        """Put the downloaded app in place now and come back as the new version."""

        path = core.vetted_update(installer, '.zip')
        if path is None:
            return False
        if not updater.install(path, self._app, pid=os.getpid(), data_dir=core.DATA_DIR, launch=True):
            return False
        self._staged = None
        self._restarting = True  # the updater starts the new version
        threading.Timer(0.25, self.app_quit).start()
        return True

    def app_stage_update(self, installer: str) -> bool:
        """Keep the update for when the app quits, the way a browser updates
        on its way out. False when this copy cannot replace itself, so the
        interface points to the download page instead."""

        path = core.vetted_update(installer, '.zip')
        if path is None or updater.refuse_reason(self._app):
            return False
        self._staged = path
        return True

    def app_clear_staged_update(self) -> bool:
        self._staged = None
        return True

    def _install_staged(self) -> None:
        """While quitting for good: the update waiting for it, if any."""

        if self._staged is not None and not self._restarting:
            staged, self._staged = self._staged, None
            updater.install(staged, self._app, pid=os.getpid(), data_dir=core.DATA_DIR, launch=False)

    def _shutdown(self) -> None:
        """Main thread, once, on the way out."""

        self._closing = True
        center = Foundation.NSNotificationCenter.defaultCenter()
        for token in self._observers:
            try:
                center.removeObserver_(token)
            except Exception:
                pass
        self._observers = []
        for stop in (self._tray.dispose, self._now_playing.stop, self._hotkeys.dispose,
                     lambda: self._dock.set(0, False)):
            try:
                stop()
            except Exception:
                pass


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number > 0 and number == number else 0.0
