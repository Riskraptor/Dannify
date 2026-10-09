"""The tray icon (an AppIndicator, which GNOME, KDE, Cinnamon, XFCE and
MATE all show), with the same menu the Windows tray has.

AppIndicators only have a menu, no click of their own, so "Open Dannify" is
the menu's first command. Without any indicator support (a bare GNOME
without the extension) the tray is unavailable, and closing the window
quits instead of hiding it somewhere nobody could get it back from.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import gi
from loguru import logger

from ..core import APP_TITLE, DEFAULT_LABELS, track_label, tray_menu
from .gtk import Gtk


def _indicator_module():
    for name in ('AyatanaAppIndicator3', 'AppIndicator3'):
        try:
            gi.require_version(name, '0.1')
            return __import__('gi.repository', fromlist=[name]).__dict__[name]
        except (ValueError, ImportError, KeyError):
            continue
    return None


class Tray:
    def __init__(self, icon: Path, on_command: Callable[[str], None]) -> None:
        self._icon = icon
        self._on_command = on_command
        self._indicator = None
        self.labels = dict(DEFAULT_LABELS)
        self._track = ''
        self._playing = False
        self._has_track = False

    @property
    def available(self) -> bool:
        return self._indicator is not None

    def install(self) -> bool:
        """GTK thread. True when the icon is (now) showing."""

        if self._indicator is not None:
            return True
        module = _indicator_module()
        if module is None:
            return False
        try:
            indicator = module.Indicator.new(
                'dannify', str(self._icon), module.IndicatorCategory.APPLICATION_STATUS,
            )
            indicator.set_title(APP_TITLE)
            indicator.set_status(module.IndicatorStatus.ACTIVE)
            self._module = module
            self._indicator = indicator
            self._rebuild()
            return True
        except Exception:
            logger.opt(exception=True).info('the tray icon is not available')
            self._indicator = None
            return False

    def _rebuild(self) -> None:
        if self._indicator is None:
            return
        menu = Gtk.Menu()
        rows = tray_menu(self.labels, self._track, self._playing, self._has_track)
        # The window first: an indicator has no click of its own.
        rows = [rows[-2], None] + rows[:-2] + [rows[-1]]
        for row in rows:
            if row is None:
                menu.append(Gtk.SeparatorMenuItem())
                continue
            command, text, enabled = row
            item = Gtk.MenuItem(label=text)
            item.set_sensitive(bool(enabled))
            if command != 'track':
                item.connect('activate', lambda _w, c=command: self._on_command(c))
            menu.append(item)
        menu.show_all()
        self._indicator.set_menu(menu)

    def apply_labels(self, labels: dict) -> None:
        self.labels = labels
        self._rebuild()

    def set_track(self, title: str, artist: str, playing: bool, has_track: bool) -> None:
        state = (track_label(title, artist), playing, has_track)
        if state == (self._track, self._playing, self._has_track):
            return
        self._track, self._playing, self._has_track = state
        self._rebuild()

    def dispose(self) -> None:
        if self._indicator is not None:
            try:
                self._indicator.set_status(self._module.IndicatorStatus.PASSIVE)
            except Exception:
                pass
        self._indicator = None
