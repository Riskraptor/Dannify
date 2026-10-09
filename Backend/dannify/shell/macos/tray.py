"""The menu bar item, with the same menu the Windows tray has.

A menu bar item is always available on macOS, so closing the window can
always keep Dannify playing there; the Dock icon brings the window back too.
The Dock icon's own menu carries the playback rows as well.
"""

from __future__ import annotations

from typing import Callable, Optional

from loguru import logger

from ..core import APP_TITLE, DEFAULT_LABELS, TRAY_TIP_MAX, fit_text, track_label, tray_menu
from .cocoa import AppKit, Foundation

_target_class = None


def _target(on_command: Callable[[str], None]):
    """An object the menu items can call back, carrying their command."""

    global _target_class
    if _target_class is None:
        class DannifyMenuTarget(Foundation.NSObject):
            def menuAction_(self, sender) -> None:  # noqa: ANN001
                command = sender.representedObject()
                if command:
                    try:
                        self.callback(str(command))
                    except Exception:
                        logger.opt(exception=True).debug('menu command failed')

        _target_class = DannifyMenuTarget
    target = _target_class.alloc().init()
    target.callback = on_command
    return target


def build_menu(rows: list, target) -> 'AppKit.NSMenu':  # noqa: ANN001
    """An NSMenu from core.tray_menu rows (None is a separator)."""

    menu = AppKit.NSMenu.alloc().initWithTitle_(APP_TITLE)
    menu.setAutoenablesItems_(False)
    for row in rows:
        if row is None:
            menu.addItem_(AppKit.NSMenuItem.separatorItem())
            continue
        command, text, enabled = row
        action = None if command == 'track' else 'menuAction:'
        item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(text, action, '')
        if action:
            item.setTarget_(target)
            item.setRepresentedObject_(command)
        item.setEnabled_(bool(enabled))
        menu.addItem_(item)
    return menu


class Tray:
    def __init__(self, on_command: Callable[[str], None]) -> None:
        self._target = _target(on_command)
        self._item = None
        self.labels = dict(DEFAULT_LABELS)
        self._track = ''
        self._playing = False
        self._has_track = False

    @property
    def available(self) -> bool:
        return True

    @property
    def showing(self) -> bool:
        return self._item is not None

    def rows(self) -> list:
        return tray_menu(self.labels, self._track, self._playing, self._has_track)

    def install(self) -> bool:
        """Main thread. True when the item is (now) in the menu bar."""

        if self._item is not None:
            return True
        try:
            item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(
                AppKit.NSVariableStatusItemLength)
            button = item.button()
            image: Optional[object] = None
            try:
                # A symbol drawn as a template follows the menu bar's colour.
                image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                    'music.note', APP_TITLE)
            except Exception:
                image = None
            if image is not None:
                image.setTemplate_(True)
                button.setImage_(image)
            else:
                button.setTitle_('\N{BEAMED EIGHTH NOTES}')
            self._item = item
            self._rebuild()
            return True
        except Exception:
            logger.opt(exception=True).info('the menu bar item is not available')
            self._item = None
            return False

    def _rebuild(self) -> None:
        if self._item is None:
            return
        self._item.setMenu_(build_menu(self.rows(), self._target))
        tip = self._track or APP_TITLE
        self._item.button().setToolTip_(fit_text(tip, TRAY_TIP_MAX))

    def dock_menu(self):
        """The Dock icon's menu: the song and its controls. The Dock adds its
        own Show and Quit."""

        rows = [row for row in self.rows() if row is None or row[0] not in ('show', 'quit')]
        while rows and rows[-1] is None:
            rows.pop()
        return build_menu(rows, self._target)

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
        if self._item is not None:
            try:
                AppKit.NSStatusBar.systemStatusBar().removeStatusItem_(self._item)
            except Exception:
                pass
        self._item = None
