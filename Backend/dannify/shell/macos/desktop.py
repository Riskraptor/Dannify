"""The rest of macOS: opening at login, Finder, the Dock's progress bar, the
sound settings, global shortcuts, the clipboard and the theme.

AppKit is imported where it is used, so the parts that are only files and
paths (the login item, where the app lives) can be checked anywhere.
"""

from __future__ import annotations

import ctypes
import plistlib
import sys
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

from ..core import HOTKEYS

BUNDLE_ID = 'io.github.danielmwendwa9451.dannify'


def bundle_path(executable: Optional[str] = None) -> Optional[Path]:
    """The Dannify.app this copy runs from; None from a source checkout."""

    if executable is None:
        if not getattr(sys, 'frozen', False):
            return None
        executable = sys.executable
    exe = Path(executable).resolve()
    # <Name>.app/Contents/MacOS/<program>
    app = exe.parent.parent.parent
    if exe.parent.name == 'MacOS' and exe.parent.parent.name == 'Contents' and app.suffix == '.app':
        return app
    return None


# ---------------------------------------------------------------------------
# Open at login (a LaunchAgent of our own)
# ---------------------------------------------------------------------------
def launch_agent_file() -> Path:
    return Path.home() / 'Library' / 'LaunchAgents' / f'{BUNDLE_ID}.plist'


def launch_agent_plist(app: Path) -> bytes:
    """What macOS runs at login: the app, through LaunchServices, hidden.

    Started with --minimized so signing in to the Mac does not throw a window
    in anyone's face; the music is one click on the Dock icon away.
    """

    return plistlib.dumps({
        'Label': BUNDLE_ID,
        'ProgramArguments': ['/usr/bin/open', str(app), '--args', '--minimized'],
        'RunAtLoad': True,
        'LimitLoadToSessionType': 'Aqua',
        'ProcessType': 'Interactive',
    })


def autostart_state() -> dict:
    return {'available': bundle_path() is not None, 'on': launch_agent_file().is_file()}


def set_autostart(on: bool, app: Optional[Path] = None) -> None:
    path = launch_agent_file()
    if not on:
        path.unlink(missing_ok=True)
        return
    app = app or bundle_path()
    if app is None:
        return
    # Written, not loaded: loading it now would start a second copy at once.
    # launchd reads the folder at the next login.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.plist.tmp')
    tmp.write_bytes(launch_agent_plist(app))
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Finder, the browser and System Settings
# ---------------------------------------------------------------------------
def _file_url(path: Path):
    from .cocoa import Foundation

    return Foundation.NSURL.fileURLWithPath_(str(path))


def reveal(target: Path) -> bool:
    """A Finder window with *target* selected."""

    from .cocoa import AppKit, on_main

    def run() -> bool:
        AppKit.NSWorkspace.sharedWorkspace().activateFileViewerSelectingURLs_([_file_url(target)])
        return True
    return bool(on_main(run, wait=True))


def open_folder(folder: Path) -> bool:
    from .cocoa import AppKit, on_main

    return bool(on_main(lambda: AppKit.NSWorkspace.sharedWorkspace().openURL_(_file_url(folder)), wait=True))


def open_url(url: str) -> bool:
    from .cocoa import AppKit, Foundation, on_main

    def run() -> bool:
        address = Foundation.NSURL.URLWithString_(url)
        return address is not None and bool(AppKit.NSWorkspace.sharedWorkspace().openURL_(address))
    return bool(on_main(run, wait=True))


def open_sound_settings() -> bool:
    """Sound in System Settings (Ventura and later) or System Preferences."""

    from .cocoa import os_major

    choices = ['x-apple.systempreferences:com.apple.preference.sound']
    if os_major() >= 13:
        choices.insert(0, 'x-apple.systempreferences:com.apple.Sound-Settings.extension')
    return any(open_url(choice) for choice in choices)


def clipboard_text() -> str:
    from .cocoa import AppKit, on_main

    def run() -> str:
        board = AppKit.NSPasteboard.generalPasteboard()
        return str(board.stringForType_(AppKit.NSPasteboardTypeString) or '')
    return on_main(run, wait=True) or ''


def set_appearance(dark: bool) -> None:
    """Main thread. Dark or light menus, dialogs and window chrome."""

    from .cocoa import AppKit

    name = AppKit.NSAppearanceNameDarkAqua if dark else AppKit.NSAppearanceNameAqua
    AppKit.NSApp().setAppearance_(AppKit.NSAppearance.appearanceNamed_(name))


# ---------------------------------------------------------------------------
# The Dock icon's progress bar
# ---------------------------------------------------------------------------
_dock_view = None


def _dock_view_class():
    """The app icon with a progress bar along its foot (an NSView, made once)."""

    global _dock_view
    if _dock_view is not None:
        return _dock_view
    from .cocoa import AppKit

    class DannifyDockView(AppKit.NSView):
        def drawRect_(self, rect) -> None:  # noqa: ANN001
            bounds = self.bounds()
            icon = AppKit.NSApp().applicationIconImage()
            if icon is not None:
                icon.drawInRect_(bounds)
            w, h = bounds.size.width, bounds.size.height
            track = AppKit.NSMakeRect(w * 0.12, h * 0.08, w * 0.76, h * 0.11)
            radius = track.size.height / 2
            AppKit.NSColor.colorWithWhite_alpha_(0.0, 0.6).set()
            AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(track, radius, radius).fill()
            value = max(0.0, min(1.0, float(getattr(self, 'value', 0.0))))
            if value <= 0:
                return
            inset = 2.0
            height = track.size.height - 2 * inset
            fill = AppKit.NSMakeRect(
                track.origin.x + inset, track.origin.y + inset,
                max(height, (track.size.width - 2 * inset) * value), height,
            )
            AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(0.114, 0.725, 0.329, 1.0).set()
            AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                fill, height / 2, height / 2).fill()

    _dock_view = DannifyDockView
    return _dock_view


class DockProgress:
    def __init__(self) -> None:
        self._view = None

    def set(self, value: float, visible: bool) -> None:
        """Main thread."""

        from .cocoa import AppKit

        tile = AppKit.NSApp().dockTile()
        if not visible:
            if self._view is not None:
                self._view = None
                tile.setContentView_(None)
                tile.display()
            return
        if self._view is None:
            size = tile.size()
            self._view = _dock_view_class().alloc().initWithFrame_(
                AppKit.NSMakeRect(0, 0, size.width, size.height))
            tile.setContentView_(self._view)
        self._view.value = float(value)
        tile.display()


# ---------------------------------------------------------------------------
# Global shortcuts, through Carbon's RegisterEventHotKey: still the one way an
# app takes a key combination for itself everywhere, and it asks for no
# Accessibility permission.
# ---------------------------------------------------------------------------
def _fourcc(code: bytes) -> int:
    return int.from_bytes(code, 'big')


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [('eventClass', ctypes.c_uint32), ('eventKind', ctypes.c_uint32)]


class _EventHotKeyID(ctypes.Structure):
    _fields_ = [('signature', ctypes.c_uint32), ('id', ctypes.c_uint32)]


_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
_KEY_CODES = {'P': 0x23, 'Left': 0x7B, 'Right': 0x7C}  # kVK_ANSI_P, kVK_LeftArrow, kVK_RightArrow
_CONTROL_OPTION = 0x1000 | 0x0800  # controlKey | optionKey
_SIGNATURE = _fourcc(b'DnfY')


def _carbon():
    lib = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/Carbon.framework/Carbon')
    lib.GetApplicationEventTarget.restype = ctypes.c_void_p
    lib.GetApplicationEventTarget.argtypes = []
    lib.InstallEventHandler.restype = ctypes.c_int32
    lib.InstallEventHandler.argtypes = [
        ctypes.c_void_p, _HANDLER, ctypes.c_uint32, ctypes.POINTER(_EventTypeSpec),
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
    ]
    lib.RemoveEventHandler.restype = ctypes.c_int32
    lib.RemoveEventHandler.argtypes = [ctypes.c_void_p]
    lib.RegisterEventHotKey.restype = ctypes.c_int32
    lib.RegisterEventHotKey.argtypes = [
        ctypes.c_uint32, ctypes.c_uint32, _EventHotKeyID, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p),
    ]
    lib.UnregisterEventHotKey.restype = ctypes.c_int32
    lib.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
    lib.GetEventParameter.restype = ctypes.c_int32
    lib.GetEventParameter.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p,
    ]
    return lib


class Hotkeys:
    def __init__(self, on_command: Callable[[str], None]) -> None:
        self._on_command = on_command
        self._lib = None
        self._handler = None  # kept alive: Carbon holds only the pointer
        self._handler_ref = ctypes.c_void_p()
        self._bound: list[ctypes.c_void_p] = []
        self._commands: dict[int, str] = {}

    def _on_event(self, _call, event, _data) -> int:  # noqa: ANN001
        found = _EventHotKeyID()
        status = self._lib.GetEventParameter(
            event, _fourcc(b'----'), _fourcc(b'hkid'), None,
            ctypes.sizeof(found), None, ctypes.byref(found),
        )
        command = self._commands.get(found.id) if status == 0 else None
        if command:
            try:
                self._on_command(command)
            except Exception:
                logger.opt(exception=True).debug('shortcut failed')
        return 0

    def register(self) -> list[str]:
        """Main thread. Returns the shortcuts that could not be taken."""

        self.unregister()
        try:
            if self._lib is None:
                self._lib = _carbon()
            target = self._lib.GetApplicationEventTarget()
            if not self._handler_ref.value:
                self._handler = _HANDLER(self._on_event)
                spec = _EventTypeSpec(_fourcc(b'keyb'), 5)  # kEventHotKeyPressed
                status = self._lib.InstallEventHandler(
                    target, self._handler, 1, ctypes.byref(spec), None, ctypes.byref(self._handler_ref))
                if status != 0:
                    raise OSError(f'InstallEventHandler: {status}')
        except Exception:
            logger.opt(exception=True).info('global shortcuts are not available')
            return [label for _, _, label in HOTKEYS]
        taken = []
        for number, (command, key, label) in enumerate(HOTKEYS, start=1):
            ref = ctypes.c_void_p()
            status = self._lib.RegisterEventHotKey(
                _KEY_CODES[key], _CONTROL_OPTION, _EventHotKeyID(_SIGNATURE, number),
                target, 0, ctypes.byref(ref))
            if status == 0 and ref.value:
                self._bound.append(ref)
                self._commands[number] = command
            else:
                taken.append(label)  # -9878: another app has it
        return taken

    def unregister(self) -> None:
        for ref in self._bound:
            try:
                self._lib.UnregisterEventHotKey(ref)
            except Exception:
                pass
        self._bound = []
        self._commands = {}

    def dispose(self) -> None:
        self.unregister()
        if self._lib is not None and self._handler_ref.value:
            self._lib.RemoveEventHandler(self._handler_ref)
            self._handler_ref = ctypes.c_void_p()
