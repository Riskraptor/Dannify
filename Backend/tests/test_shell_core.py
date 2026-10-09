"""What every desktop shell shares (dannify/shell/core.py, instance.py)."""

from __future__ import annotations

import os
import tempfile

import pytest

# The shell's core picks its data folder (and the log beside it) when first
# imported: a throwaway one here, and nothing left behind for other tests.
_saved = {k: os.environ.get(k) for k in ('DANNIFY_DATA_DIR', 'DANNIFY_LOG_FILE')}
os.environ['DANNIFY_DATA_DIR'] = tempfile.mkdtemp(prefix='dannify-shell-')
from dannify.shell import core  # noqa: E402

for _key, _value in _saved.items():
    if _value is None:
        os.environ.pop(_key, None)
    else:
        os.environ[_key] = _value


def test_tray_menu_follows_the_player():
    labels = dict(core.DEFAULT_LABELS)
    rows = core.tray_menu(labels, '', playing=False, has_track=False)
    commands = [r[0] for r in rows if r]
    assert commands == ['track', 'toggle', 'prev', 'next', 'show', 'quit']
    assert rows[0][1] == 'Nothing playing' and rows[0][2] is False
    assert rows[2] == ('toggle', 'Play', False)
    playing = core.tray_menu(labels, core.track_label('Inauma', 'Bien'), playing=True, has_track=True)
    assert playing[0][1] == 'Inauma \N{MIDDLE DOT} Bien'
    assert playing[2] == ('toggle', 'Pause', True)


def test_labels_from_the_interface_are_kept_to_what_we_know():
    merged = core.merge_labels(core.DEFAULT_LABELS, {'play': 'Lire', 'evil': 'x', 'quit': '', 'show': 'O' * 99})
    assert merged['play'] == 'Lire' and 'evil' not in merged
    assert merged['quit'] == core.DEFAULT_LABELS['quit']  # empty is not a label
    assert len(merged['show']) == core.MENU_TEXT_MAX
    assert core.merge_labels(merged, 'nonsense') is merged


def test_only_our_own_downloads_are_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'UPDATES_DIR', tmp_path / 'updates')
    (tmp_path / 'updates').mkdir()
    deb = tmp_path / 'updates' / 'linux-dannify_4.8.0_amd64.deb'
    deb.write_bytes(b'!')
    outside = tmp_path / 'evil.deb'
    outside.write_bytes(b'!')
    assert core.vetted_update(str(deb), '.deb') == deb.resolve()
    assert core.vetted_update(str(outside), '.deb') is None
    assert core.vetted_update(str(tmp_path / 'updates' / '..' / 'evil.deb'), '.deb') is None
    assert core.vetted_update(str(deb), '.zip') is None  # wrong kind for this platform
    assert core.vetted_update('', '.deb') is None


def test_a_file_handed_over_is_found_among_the_switches(tmp_path):
    song = tmp_path / 'song.dnf'
    song.write_bytes(b'x')
    assert core.file_argument(['--minimized', str(song)]) == str(song.resolve())
    assert core.file_argument([song.as_uri()]) == str(song.resolve())
    assert core.file_argument(['--minimized', str(tmp_path / 'missing.mp3')]) == ''


def test_the_splash_paints_in_the_theme():
    assert core.THEME_BG['light'] in core.splash_html('light')
    assert core.THEME_BG['dark'] in core.splash_html('dark')
    assert 'could not start' in core.failed_html('dark')


@pytest.mark.skipif(not hasattr(__import__('socket'), 'AF_UNIX') or os.name == 'nt',
                    reason='Unix sockets (Linux and macOS)')
def test_a_second_copy_hands_over_and_a_stale_socket_is_replaced(tmp_path, monkeypatch):
    from dannify.shell import instance

    monkeypatch.setattr(instance, 'DATA_DIR', tmp_path)
    (tmp_path / 'instance.sock').write_text('left by a crash')
    first = instance.Instance()
    got = []
    first.handler = lambda m: (got.append(m), {'ok': True, 'seen': m.get('cmd')})[1]
    assert first.claim() is True
    second = instance.Instance()
    assert second.claim() is False  # one copy only
    assert instance.send({'cmd': 'show', 'file': ''}) == {'ok': True, 'seen': 'show'}
    assert got == [{'cmd': 'show', 'file': ''}]
    assert (tmp_path / 'instance.sock').stat().st_mode & 0o077 == 0
    first.release()
    assert instance.send({'cmd': 'ping'}) is None
