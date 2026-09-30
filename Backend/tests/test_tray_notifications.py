"""The tray icon: what it says, what its menu offers, and how often it talks.

Each of these was a real annoyance in the shell: a tooltip that kept naming
the previous song whenever the current one had a long title, a menu that ate
the "&" out of artist names, and a "still running here" balloon that came
back at the first close of every single session.
"""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

_NAMES = (
    'APP_TITLE',
    '_TRAY_TIP_MAX',
    '_MENU_TEXT_MAX',
    '_fit_text',
    '_track_label',
    '_tray_tooltip',
    '_menu_text',
    '_tray_menu',
    '_Tray',
)


def _load_from_desktop(*names: str, **extra) -> dict:
    """Pull top-level definitions out of desktop.py without importing it
    (importing it starts setting up the desktop shell)."""

    source = (BACKEND / 'desktop.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    wanted = [
        node for node in tree.body
        if (isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names)
        or (isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in names for t in node.targets
        ))
    ]
    namespace: dict = {'logger': _QuietLogger(), **extra}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), 'desktop.py', 'exec'), namespace)
    return namespace


class _QuietLogger:
    def opt(self, *args, **kwargs):
        return self

    def debug(self, *args, **kwargs):
        pass


@pytest.fixture()
def tray_ns():
    return _load_from_desktop(*_NAMES)


LABELS = {
    'nowPlaying': 'Nothing playing',
    'play': 'Play',
    'pause': 'Pause',
    'prev': 'Previous',
    'next': 'Next',
    'show': 'Open Dannify',
    'quit': 'Quit Dannify',
    'hidden': 'Dannify is still running here.',
}


# ---------------------------------------------------------------------------
# The tooltip
# ---------------------------------------------------------------------------
class _NetFx48Icon:
    """Stands in for WinForms' NotifyIcon on .NET Framework 4.8, which is
    what pythonnet loads: Text longer than 63 characters throws."""

    def __init__(self):
        self._text = ''
        self.balloons: list[tuple[str, str, int]] = []

    @property
    def Text(self):  # noqa: N802  (the .NET name)
        return self._text

    @Text.setter
    def Text(self, value):  # noqa: N802
        if len(value) > 63:
            raise ValueError('ArgumentOutOfRangeException: Text')
        self._text = value

    def ShowBalloonTip(self, timeout):  # noqa: N802
        self.balloons.append((self.BalloonTipTitle, self.BalloonTipText, timeout))


def test_tooltip_names_the_app_then_the_song(tray_ns):
    tip = tray_ns['_tray_tooltip']('Yellow · Coldplay', 'Nothing playing')
    assert tip == 'Dannify\nYellow · Coldplay'
    assert tray_ns['_tray_tooltip']('', 'Nothing playing') == 'Dannify\nNothing playing'


def test_a_long_song_is_shortened_to_what_windows_accepts(tray_ns):
    track = tray_ns['_track_label'](
        'Bohemian Rhapsody (Remastered 2011) [Live at Wembley Stadium, July 1986]',
        'Queen',
    )
    tip = tray_ns['_tray_tooltip'](track, 'Nothing playing')
    assert len(tip) == 63
    assert tip.startswith('Dannify\nBohemian Rhapsody')
    assert tip.endswith('…')


def test_the_tooltip_follows_every_song_even_long_ones(tray_ns):
    # The bug: the old tooltip was cut at 127, the setter threw past 63, the
    # throw was swallowed and the tooltip kept the previous song's name.
    tray = tray_ns['_Tray'](api=None)
    tray._icon = _NetFx48Icon()

    tray.set_track('Short', 'Artist', True, True)
    assert tray._icon.Text == 'Dannify\nShort · Artist'

    tray.set_track('A title long enough that the old tooltip gave up on it', 'Someone Else', True, True)
    assert tray._icon.Text.startswith('Dannify\nA title long enough')
    assert 'Short' not in tray._icon.Text


def test_line_breaks_in_tags_do_not_reach_the_tooltip(tray_ns):
    assert tray_ns['_track_label']('Line one\nline two', ' The\tBand ') == 'Line one line two · The Band'
    assert tray_ns['_track_label']('Only a title', '') == 'Only a title'
    assert tray_ns['_track_label']('', 'Only an artist') == ''


def test_tooltip_fits_what_windows_forms_really_accepts(tray_ns):
    """The same check against the real NotifyIcon, where .NET is present."""

    if sys.platform != 'win32':
        pytest.skip('Windows only')
    try:
        import clr

        clr.AddReference('System.Windows.Forms')
        from System.Windows.Forms import NotifyIcon
    except Exception:
        pytest.skip('pythonnet / WinForms not available')

    icon = NotifyIcon()  # never made visible: nothing reaches the tray
    try:
        for track in ('', 'x' * 10, 'y' * 55, 'z' * 56, 'w' * 300):
            icon.Text = tray_ns['_tray_tooltip'](track, 'Nothing playing')
    finally:
        icon.Dispose()


# ---------------------------------------------------------------------------
# The menu
# ---------------------------------------------------------------------------
def _rows(menu):
    return [row for row in menu if row is not None]


def test_menu_offers_the_basic_controls(tray_ns):
    menu = tray_ns['_tray_menu'](LABELS, 'Yellow · Coldplay', False, True)
    commands = [row[0] for row in _rows(menu)]
    assert commands == ['track', 'toggle', 'prev', 'next', 'show', 'quit']
    # Separators after the song and before Open / Quit.
    assert menu[1] is None and menu[5] is None
    by_command = {row[0]: row for row in _rows(menu)}
    assert by_command['track'][2] is False  # context, not a command
    assert by_command['show'][3] is True  # the default (bold) item
    assert by_command['quit'][2] is True


def test_play_and_pause_follow_the_player(tray_ns):
    paused = {r[0]: r for r in _rows(tray_ns['_tray_menu'](LABELS, 'Song', False, True))}
    playing = {r[0]: r for r in _rows(tray_ns['_tray_menu'](LABELS, 'Song', True, True))}
    assert paused['toggle'][1] == 'Play'
    assert playing['toggle'][1] == 'Pause'


def test_transport_is_greyed_with_nothing_loaded(tray_ns):
    menu = {r[0]: r for r in _rows(tray_ns['_tray_menu'](LABELS, '', False, False))}
    assert menu['track'][1] == 'Nothing playing'
    assert not menu['toggle'][2] and not menu['prev'][2] and not menu['next'][2]
    assert menu['show'][2] and menu['quit'][2]


def test_ampersands_survive_the_menu(tray_ns):
    menu = {r[0]: r for r in _rows(tray_ns['_tray_menu'](LABELS, 'The Boxer · Simon & Garfunkel', True, True))}
    # "&&" is how a Windows menu shows one "&".
    assert menu['track'][1] == 'The Boxer · Simon && Garfunkel'


def test_long_menu_rows_are_shortened_visibly(tray_ns):
    text = tray_ns['_menu_text']('n' * 200)
    assert len(text) == 64 and text.endswith('…')


# ---------------------------------------------------------------------------
# The "still running here" notice
# ---------------------------------------------------------------------------
@pytest.fixture()
def fake_winforms(monkeypatch):
    forms = types.ModuleType('System.Windows.Forms')
    forms.ToolTipIcon = types.SimpleNamespace(Info='Info', None_='None')
    windows = types.ModuleType('System.Windows')
    windows.Forms = forms
    system = types.ModuleType('System')
    system.Windows = windows
    monkeypatch.setitem(sys.modules, 'System', system)
    monkeypatch.setitem(sys.modules, 'System.Windows', windows)
    monkeypatch.setitem(sys.modules, 'System.Windows.Forms', forms)
    return forms


def _tray_with_prefs(hint_shown: bool):
    written: list[dict] = []
    ns = _load_from_desktop(*_NAMES, _write_prefs=written.append)
    tray = ns['_Tray'](api=None, hint_shown=hint_shown)
    tray.apply_labels(LABELS)
    tray._icon = _NetFx48Icon()
    return tray, written


def test_the_notice_is_shown_once_and_remembered(fake_winforms):
    tray, written = _tray_with_prefs(hint_shown=False)

    tray.notify_hidden()
    tray.notify_hidden()
    tray.notify_hidden()

    assert len(tray._icon.balloons) == 1
    assert tray._icon.balloons[0][1] == 'Dannify is still running here.'
    # Written down, so the next launch does not say it again.
    assert written == [{'tray_hint_shown': True}]


def test_a_later_launch_does_not_repeat_the_notice(fake_winforms):
    tray, written = _tray_with_prefs(hint_shown=True)

    tray.notify_hidden()

    assert tray._icon.balloons == []
    assert written == []


def test_no_notice_without_a_tray_icon(fake_winforms):
    tray, written = _tray_with_prefs(hint_shown=False)
    tray._icon = None

    tray.notify_hidden()

    # Nothing was shown, so nothing is marked as seen.
    assert written == []
    assert tray._told_user is False
