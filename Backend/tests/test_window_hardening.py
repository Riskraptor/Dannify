"""The window stays an app: nothing decrypted is left on disk by it, and its
browser cannot be opened up from outside."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from tests._shell_source import windows_tree

BACKEND = Path(__file__).resolve().parents[1]


def _load(*names: str, **extra) -> dict:
    tree = windows_tree()
    wanted = [
        node for node in tree.body
        if (isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names)
        or (isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in names for t in node.targets
        ))
    ]
    namespace: dict = {'Path': Path, 'os': os, **extra}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), 'desktop.py', 'exec'), namespace)
    return namespace


def test_the_old_cache_is_emptied_once_and_the_rest_kept(tmp_path):
    ns = _load('_purge_window_cache', '_CACHE_GENERATION', _WEBVIEW_STORAGE=tmp_path)
    default = tmp_path / 'EBWebView' / 'Default'
    (default / 'Cache' / 'Cache_Data').mkdir(parents=True)
    (default / 'Cache' / 'Cache_Data' / 'f_000001').write_bytes(b'decrypted audio')
    (default / 'Local Storage').mkdir()
    (default / 'Local Storage' / 'leveldb').write_bytes(b'settings')

    ns['_purge_window_cache']()
    assert not (default / 'Cache').exists()
    assert (default / 'Local Storage' / 'leveldb').exists(), 'the window keeps its own settings'

    # Once: a cache made since stays.
    (default / 'Cache').mkdir()
    (default / 'Cache' / 'cover').write_bytes(b'picture')
    ns['_purge_window_cache']()
    assert (default / 'Cache' / 'cover').exists()


def test_the_view_is_locked_to_an_app():
    ns = _load('_lock_view_settings')

    class FakeSettings:
        IsZoomControlEnabled = True
        IsPinchZoomEnabled = True
        IsPasswordAutosaveEnabled = True
        IsGeneralAutofillEnabled = True
        IsSwipeNavigationEnabled = True

    class Core:
        Settings = FakeSettings()

    core = Core()
    ns['_lock_view_settings'](core)
    s = core.Settings
    assert not any((s.IsZoomControlEnabled, s.IsPinchZoomEnabled, s.IsPasswordAutosaveEnabled,
                    s.IsGeneralAutofillEnabled, s.IsSwipeNavigationEnabled))

    class Older:  # a runtime without some of these: no error
        Settings = object()

    ns['_lock_view_settings'](Older())


def test_debugger_variables_are_dropped_before_the_browser_starts(monkeypatch):
    ns = _load('_webview_untampered', '_WEBVIEW_ENV', '_RISKY_SWITCHES', _WIN=False, logger_print=print)
    monkeypatch.setenv('WEBVIEW2_BROWSER_EXECUTABLE_FOLDER', r'C:\evil')
    monkeypatch.setenv('WEBVIEW2_PIPE_FOR_SCRIPT_DEBUGGER', 'x')
    assert ns['_webview_untampered']() is True
    assert 'WEBVIEW2_BROWSER_EXECUTABLE_FOLDER' not in os.environ
    assert 'WEBVIEW2_PIPE_FOR_SCRIPT_DEBUGGER' not in os.environ


def test_saved_songs_reach_the_window_marked_never_to_be_stored():
    source = (BACKEND / 'dannify' / 'served.py').read_text(encoding='utf-8')
    start = source.index('length = max(0, end - start + 1)')
    block = source[start:start + 1200]
    assert "'Cache-Control': 'no-store'" in block
    assert 'no-cache' not in block.split('headers = {', 1)[1].split('}', 1)[0]
    stream = (BACKEND / 'dannify' / 'streaming.py').read_text(encoding='utf-8')
    assert "'public, max-age" not in stream


def test_songs_are_worked_on_in_the_app_folder_and_leftovers_swept(tmp_path, monkeypatch):
    import tempfile

    from dannify import bench

    system_tmp = tmp_path / 'systemp'
    system_tmp.mkdir()
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(system_tmp))
    bench.set_root(tmp_path / 'work')
    try:
        made = bench.make('dnf-dl-')
        assert made.parent == tmp_path / 'work'
        old_here = bench.make('dnf-repair-')
        old_there = system_tmp / 'dnf-dl-old'
        old_there.mkdir()
        unrelated = system_tmp / 'someone-else'
        unrelated.mkdir()
        past = 1_000_000
        os.utime(old_here, (past, past))
        os.utime(old_there, (past, past))
        assert bench.sweep() == 2
        assert made.exists() and unrelated.exists()
        assert not old_here.exists() and not old_there.exists()
    finally:
        bench._root = None


def test_a_shipped_copy_updates_only_from_where_it_was_built_to(tmp_path, monkeypatch):
    import sys

    from dannify import support, updates

    (tmp_path / 'updates.json').write_text('{"repo": "someone/else"}', encoding='utf-8')
    (tmp_path / 'support.json').write_text('{"link": "https://example.com/pay-me"}', encoding='utf-8')
    monkeypatch.setenv('DANNIFY_UPDATE_REPO', 'attacker/repo')
    monkeypatch.setenv('DANNIFY_SUPPORT_LINK', 'https://example.com/other')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    try:
        assert support.config_paths(tmp_path, 'updates.json') == []
        updates.init(tmp_path)
        assert updates.repo() == updates.DEFAULT_REPO
        support.init(tmp_path)
        assert support.config()['link'] == support._DEFAULTS['link']
    finally:
        monkeypatch.delattr(sys, 'frozen', raising=False)
        support.init(tmp_path / 'nothing-here')
        updates._settings['repo'] = ''


def test_a_file_handed_over_to_an_earlier_run_is_not_played_again():
    from typing import Any

    ns = _load('_file_from_note', Any=Any)
    pick = ns['_file_from_note']
    started = 1_000_000
    assert pick({'path': 'C:/Music/new.dnf', 'n': started + 5}, started) == 'C:/Music/new.dnf'
    # Left on disk by the run before: Dannify used to start playing it.
    assert pick({'path': 'C:/Music/old.dnf', 'n': started - 5}, started) == ''
    assert pick({'path': 'C:/Music/x.dnf', 'n': 'garbage'}, started) == ''
    assert pick(['not', 'a', 'note'], started) == ''
