"""The notification-area icon, its tooltip and its menu."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from .base import (
    APP_TITLE,
    _app_icon,
    _write_prefs,
    logger_print,
)
from .menu import _NativeMenu

if TYPE_CHECKING:
    from .api import DesktopApi


# --- What the tray says ------------------------------------------------------
#
# Plain functions, so the wording and the limits can be tested without a
# window, a tray or .NET.

# NotifyIcon.Text refuses anything longer than 63 characters on the .NET
# Framework the app runs on (4.8, which is what pythonnet loads; the 127 of
# newer .NET does not apply). The tooltip used to be cut at 127, so any
# title and artist longer than about 55 characters made the setter throw, the
# throw was swallowed, and the tooltip went on naming whatever had played
# before. "Dannify" plus the song has to fit in 63, and a long one is
# shortened with an ellipsis instead.
_TRAY_TIP_MAX = 63


_MENU_TEXT_MAX = 64


def _fit_text(text: str, limit: int) -> str:
    """One line, at most *limit* characters, the cut marked with an ellipsis.

    Tags read from files can carry line breaks and tabs, which a tooltip or a
    menu row would otherwise print as they are.
    """

    flat = ' '.join(str(text or '').split())
    if len(flat) <= limit:
        return flat
    return flat[: max(0, limit - 1)].rstrip() + '\N{HORIZONTAL ELLIPSIS}'


def _track_label(title: str, artist: str) -> str:
    """How the tray names a song: "Title · Artist".

    It used to be "Title: Artist", which reads like a label and its value.
    The middle dot is what the interface puts between details elsewhere.
    """

    title = ' '.join(str(title or '').split())
    artist = ' '.join(str(artist or '').split())
    if title and artist:
        return f'{title} \N{MIDDLE DOT} {artist}'
    return title


def _tray_tooltip(track: str, idle: str) -> str:
    """The hover text: the app's name, then what is playing (or not)."""

    head = APP_TITLE + chr(10)
    return head + _fit_text(track or idle, _TRAY_TIP_MAX - len(head))


def _menu_text(label: str) -> str:
    """A menu row's text, safe to hand to AppendMenuW.

    Windows reads "&" in a menu item as "underline the next character", so a
    song by Simon & Garfunkel appeared in the tray menu with the ampersand
    gone and the space after it underlined. Doubling it is how a menu shows a
    real one.
    """

    return _fit_text(label, _MENU_TEXT_MAX).replace('&', '&&')


def _tray_menu(labels: dict, track: str, playing: bool, has_track: bool) -> list:
    """The right-click menu, as (command, text, enabled, default) rows.

    None is a separator. Built from the current state every time it opens,
    so Play and Pause can never be the wrong way round.
    """

    return [
        # The song is context, not a command: a greyed row at the top, as in
        # every other player's tray menu.
        ('track', _menu_text(track or labels['nowPlaying']), False, False),
        None,
        ('toggle', _menu_text(labels['pause' if playing else 'play']), has_track, False),
        ('prev', _menu_text(labels['prev']), has_track, False),
        ('next', _menu_text(labels['next']), has_track, False),
        None,
        ('show', _menu_text(labels['show']), True, True),
        ('quit', _menu_text(labels['quit']), True, False),
    ]


class _Tray:
    LABEL_KEYS = ('nowPlaying', 'play', 'pause', 'prev', 'next', 'show', 'quit', 'hidden')

    def __init__(self, api: 'DesktopApi', hint_shown: bool = False):
        self._api = api
        self._icon = None  # WinForms.NotifyIcon
        # An invisible window that owns the right-click menu (see install).
        self._menu_owner = None
        self._track = ''
        self._playing = False
        self._has_track = False
        # Whether the "still running here" notice has ever been shown. Kept
        # with the window settings: it is said once, not once per launch.
        self._told_user = bool(hint_shown)
        self.labels = {
            'nowPlaying': 'Nothing playing',
            'play': 'Play',
            'pause': 'Pause',
            'prev': 'Previous',
            'next': 'Next',
            'show': 'Open Dannify',
            'quit': 'Quit Dannify',
            'hidden': 'Dannify is still running here. Click the icon to open it, '
                      'or right-click it to quit.',
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
            # Clicking the one-time notice opens the window, as clicking any
            # app's notification does. It used to do nothing at all.
            icon.BalloonTipClicked += EventHandler(
                lambda s, e: self._api._show_from_tray()
            )
            icon.Visible = True
            self._icon = icon
            self._make_menu_owner()
            # Say what is playing straight away. A tray switched on in
            # Settings mid-song used to read just "Dannify" until the next
            # track, because the song arrived while there was no icon to tell.
            self.refresh()
            return True
        except Exception as exc:
            logger_print('tray icon unavailable:', exc)
            return False

    def _make_menu_owner(self) -> None:
        """An invisible window of our own for the menu to belong to.

        A popup menu only closes on an outside click if its owner is the
        foreground window (see _NativeMenu.show). It used to borrow the main
        window for that, and making the main window the foreground window
        brings it to the front: right-clicking the tray icon while Dannify sat
        behind other windows pulled the whole app over them just to show a
        menu. NotifyIcon does its own menus this same way, with a window
        nobody sees. If this fails the main window is still there to use.
        """

        if self._menu_owner is not None:
            return
        try:
            from System.Windows.Forms import CreateParams, NativeWindow

            owner = NativeWindow()
            owner.CreateHandle(CreateParams())
            self._menu_owner = owner
        except Exception:
            logger.opt(exception=True).debug('tray menu owner unavailable')

    def _menu_hwnd(self) -> int:
        owner = self._menu_owner
        if owner is not None:
            try:
                handle = int(owner.Handle.ToInt64())
                if handle:
                    return handle
            except Exception:
                pass
        return self._api._hwnd or 0

    def _popup_menu(self) -> None:
        """Right-click: show the real Windows menu."""

        actions = {
            'toggle': lambda: self._api._media('toggle'),
            'prev': lambda: self._api._media('prev'),
            'next': lambda: self._api._media('next'),
            'show': self._api._show_from_tray,
            'quit': self._api._quit,
        }
        menu = _NativeMenu()
        for row in _tray_menu(self.labels, self._track, self._playing, self._has_track):
            if row is None:
                menu.add_separator()
                continue
            command, text, enabled, default = row
            menu.add(text, actions.get(command), enabled=enabled, default=default)
        menu.show(self._menu_hwnd())

    def apply_labels(self, labels: dict) -> None:
        for key in self.LABEL_KEYS:
            value = labels.get(key)
            if isinstance(value, str) and value:
                self.labels[key] = value[:80]
        self.refresh()

    def set_track(self, title: str, artist: str, playing: bool, has_track: bool) -> None:
        self._track = _track_label(title, artist)
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
            self._icon.Text = _tray_tooltip(self._track, self.labels['nowPlaying'])
        except Exception:
            logger.opt(exception=True).debug('tray tooltip not updated')

    def notify_hidden(self) -> None:
        """Say where the window went: once, ever.

        It used to be once per run, so anyone who closes the window out of
        habit got the same balloon at the first close of every session, and
        on Windows 10 and 11 each one also went to sit in the notification
        centre. The first time is the one that explains; after that it is
        known, so it is remembered with the window settings.
        """
        if self._icon is None or self._told_user:
            return
        self._told_user = True
        _write_prefs({'tray_hint_shown': True})
        try:
            from System.Windows.Forms import ToolTipIcon

            self._icon.BalloonTipIcon = ToolTipIcon.Info
            self._icon.BalloonTipTitle = APP_TITLE
            self._icon.BalloonTipText = self.labels['hidden']
            self._icon.ShowBalloonTip(4000)
        except Exception:
            pass

    def dispose(self) -> None:
        owner, self._menu_owner = self._menu_owner, None
        if owner is not None:
            try:
                owner.DestroyHandle()
            except Exception:
                pass
        icon, self._icon = self._icon, None
        if icon is None:
            return
        try:
            icon.Visible = False
            icon.Dispose()
        except Exception:
            pass
