"""The rest of the Linux desktop: start at login, the file manager, the
dock's progress bar, the sound settings, global shortcuts and the theme."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

from ..core import HOTKEYS
from .gtk import Gdk, Gio, GLib, Gtk

DESKTOP_ID = 'dannify.desktop'


def _spawn(args: list[str]) -> bool:
    """Start a helper program and leave it be (never wait on a GUI)."""

    try:
        subprocess.Popen(  # noqa: S603  (fixed programs, our own arguments)
            args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Start with the desktop session (XDG autostart)
# ---------------------------------------------------------------------------
def _autostart_file() -> Path:
    base = Path(os.getenv('XDG_CONFIG_HOME') or str(Path.home() / '.config'))
    return base / 'autostart' / DESKTOP_ID


def _launcher() -> Optional[str]:
    """The command an installed copy starts with; None from a checkout."""

    return shutil.which('dannify')


def autostart_state() -> dict:
    return {'available': _launcher() is not None, 'on': _autostart_file().is_file()}


def set_autostart(on: bool) -> None:
    path = _autostart_file()
    if not on:
        path.unlink(missing_ok=True)
        return
    command = _launcher()
    if command is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # Started minimised: signing in should not throw a window in anyone's
    # face, the music is one click on the tray away.
    path.write_text(
        '[Desktop Entry]\n'
        'Type=Application\n'
        'Name=Dannify\n'
        f'Exec={command} --minimized\n'
        'Icon=dannify\n'
        'X-GNOME-Autostart-enabled=true\n'
        'NoDisplay=false\n',
        encoding='utf-8',
    )


# ---------------------------------------------------------------------------
# The file manager
# ---------------------------------------------------------------------------
def reveal(target: Path) -> bool:
    """Open the file manager with *target* selected.

    The FileManager1 D-Bus call is what Nautilus, Dolphin, Nemo and Caja
    answer; without it the folder opens, unselected.
    """

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(
            'org.freedesktop.FileManager1', '/org/freedesktop/FileManager1',
            'org.freedesktop.FileManager1', 'ShowItems',
            GLib.Variant('(ass)', ([Path(target).as_uri()], '')),
            None, Gio.DBusCallFlags.NONE, 3000, None,
        )
        return True
    except Exception:
        return open_folder(Path(target).parent)


def open_folder(folder: Path) -> bool:
    try:
        return bool(Gio.AppInfo.launch_default_for_uri(Path(folder).as_uri(), None))
    except Exception:
        return _spawn(['xdg-open', str(folder)])


def open_url(url: str) -> bool:
    try:
        return bool(Gio.AppInfo.launch_default_for_uri(url, None))
    except Exception:
        return _spawn(['xdg-open', url])


def open_sound_settings() -> bool:
    """The desktop's own page for outputs and per-app volume."""

    desktop = (os.getenv('XDG_CURRENT_DESKTOP') or '').lower()
    choices = [
        ['gnome-control-center', 'sound'],
        ['systemsettings', 'kcm_pulseaudio'],
        ['kcmshell6', 'kcm_pulseaudio'],
        ['kcmshell5', 'kcm_pulseaudio'],
        ['cinnamon-settings', 'sound'],
        ['mate-volume-control'],
        ['xfce4-pulseaudio-plugin'],
        ['pavucontrol'],
    ]
    if 'kde' in desktop:
        choices.insert(0, choices.pop(1))
    for args in choices:
        if shutil.which(args[0]) and _spawn(args):
            return True
    return False


# ---------------------------------------------------------------------------
# The dock's progress bar (Unity LauncherEntry: Ubuntu Dock, Dash to Dock,
# Plank and KDE's task manager all read it)
# ---------------------------------------------------------------------------
def launcher_progress(value: float, visible: bool) -> None:
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        props = {
            'progress': GLib.Variant('d', max(0.0, min(1.0, float(value)))),
            'progress-visible': GLib.Variant('b', bool(visible)),
        }
        bus.emit_signal(
            None, '/com/dannify/launcher', 'com.canonical.Unity.LauncherEntry', 'Update',
            GLib.Variant('(sa{sv})', (f'application://{DESKTOP_ID}', props)),
        )
    except Exception:
        logger.opt(exception=True).debug('no dock progress')


# ---------------------------------------------------------------------------
# Global shortcuts (X11 only: Wayland lets no app grab keys for itself; the
# media keys still work there, through MPRIS)
# ---------------------------------------------------------------------------
class Hotkeys:
    def __init__(self, on_command: Callable[[str], None]) -> None:
        self._on_command = on_command
        self._bound: list[str] = []
        self._keybinder = None

    def _load(self):
        if self._keybinder is None:
            try:
                import gi

                gi.require_version('Keybinder', '3.0')
                from gi.repository import Keybinder

                Keybinder.init()
                self._keybinder = Keybinder
            except Exception:
                self._keybinder = False
        return self._keybinder or None

    def register(self) -> list[str]:
        """GTK thread. Returns the shortcuts that could not be taken."""

        self.unregister()
        # Keybinder grabs keys through X11; on a Wayland display it can not.
        display = Gdk.Display.get_default()
        on_x11 = display is not None and 'X11' in type(display).__name__
        kb = self._load() if on_x11 else None
        if kb is None:
            return [label for _, _, label in HOTKEYS]
        taken = []
        for command, key, label in HOTKEYS:
            accel = f'<Ctrl><Alt>{key}'
            if kb.bind(accel, lambda _keystring, c=command: self._on_command(c)):
                self._bound.append(accel)
            else:
                taken.append(label)
        return taken

    def unregister(self) -> None:
        kb = self._keybinder or None
        for accel in self._bound:
            try:
                kb.unbind(accel)
            except Exception:
                pass
        self._bound = []


def prefer_dark(dark: bool) -> None:
    """GTK thread. Dark or light window decorations and dialogs."""

    settings = Gtk.Settings.get_default()
    if settings is not None:
        settings.set_property('gtk-application-prefer-dark-theme', bool(dark))


def system_prefers_light() -> bool:
    try:
        settings = Gio.Settings.new('org.gnome.desktop.interface')
        return settings.get_string('color-scheme') == 'prefer-light'
    except Exception:
        return False
