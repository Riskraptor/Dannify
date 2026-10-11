"""The name a Linux desktop knows Dannify's window by.

GTK gives a window its app id (Wayland) and its WM_CLASS (X11) from the
program's name, and the desktop looks for a launcher of that name to find the
icon, the app's name and its place on the dock. Left alone the name is the
script's, "desktop.py": the window then belonged to no app, showed a blank
icon and could not be pinned.

Read from the source, the way _shell_source does for Windows: importing the
Linux shell needs GTK, which no test machine has to have.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHELL = ROOT / 'Backend' / 'dannify' / 'shell' / 'linux'
PACKAGING = ROOT / 'packaging' / 'linux'


def _gtk_statements() -> list[ast.stmt]:
    return ast.parse((SHELL / 'gtk.py').read_text(encoding='utf-8')).body


def _app_id() -> str:
    for node in _gtk_statements():
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == 'APP_ID' for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError('gtk.py names no APP_ID')


def _launcher(key: str) -> str:
    text = (PACKAGING / f'{_app_id()}.desktop').read_text(encoding='utf-8')
    found = re.search(rf'^{key}=(.*)$', text, re.MULTILINE)
    return found.group(1).strip() if found else ''


def test_the_program_is_named_before_gtk_starts():
    # GDK copies the name when it is imported; naming the program after that
    # changes nothing the desktop sees.
    named = starts = None
    for index, node in enumerate(_gtk_statements()):
        if named is None and 'set_prgname(APP_ID)' in ast.unparse(node):
            named = index
        if starts is None and isinstance(node, ast.ImportFrom) and node.module == 'gi.repository':
            if {'Gtk', 'Gdk'} & {alias.name for alias in node.names}:
                starts = index
    assert named is not None, 'gtk.py never names the program'
    assert starts is not None and named < starts


def test_the_name_is_the_launchers():
    app_id = _app_id()
    assert (PACKAGING / f'{app_id}.desktop').is_file()  # Wayland: matched by file name
    # X11: GDK's class is the name with its first letter in capitals.
    assert _launcher('StartupWMClass') == app_id[:1].upper() + app_id[1:]
    assert _launcher('Icon') == app_id


def test_the_rest_of_the_shell_goes_by_the_same_name():
    app_id = _app_id()
    desktop = (SHELL / 'desktop.py').read_text(encoding='utf-8')
    assert "DESKTOP_ID = f'{APP_ID}.desktop'" in desktop  # the dock's progress bar
    mpris = (SHELL / 'mpris.py').read_text(encoding='utf-8')
    entry = re.search(r"'DesktopEntry': GLib\.Variant\('s', '([^']+)'\)", mpris)
    assert entry and entry.group(1) == app_id  # the media panel's icon
    build = (PACKAGING / 'build-deb.sh').read_text(encoding='utf-8')
    assert f'packaging/linux/{app_id}.desktop' in build
    assert f'apps/{app_id}.png' in build
