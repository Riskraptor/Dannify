"""A file named by the window must be a file in the music folder."""

from __future__ import annotations

import pytest

from dannify import api

BS = chr(92)


@pytest.fixture
def library(tmp_path, monkeypatch):
    (tmp_path / 'A').mkdir()
    (tmp_path / 'A' / 'x.dnf').write_bytes(b'x')
    monkeypatch.setattr(api.state, 'download_dir', tmp_path)
    return tmp_path


@pytest.mark.parametrize('name', ['A/x.dnf', 'A' + BS + 'x.dnf'])
def test_inside_is_found(library, name):
    assert api._library_file(name) == (library / 'A' / 'x.dnf').resolve()


@pytest.mark.parametrize('name', [
    '../secret.txt',
    'C:/Windows/win.ini',
    BS * 2 + 'host' + BS + 'share' + BS + 'x.mp3',
    '//host/share/x.mp3',
    'C:foo',
    'A/x.dnf:stream',
    '/etc/passwd',
    '',
])
def test_anything_else_is_refused(library, name):
    assert api._library_file(name) is None


def test_storage_counts_the_library_and_clearing_keeps_music(tmp_path, monkeypatch):
    import asyncio

    from dannify import lyrics

    music, data = tmp_path / 'Music', tmp_path / 'data'
    (music / 'A').mkdir(parents=True)
    (music / 'A' / 'A - x.dnf').write_bytes(b'x' * 1000)
    (music / 'A' / 'A - x.lrc').write_text('[00:01.00]mine', encoding='utf-8')
    (data / 'ytdlp-cache').mkdir(parents=True)
    (data / 'ytdlp-cache' / 'player.js').write_bytes(b'y' * 500)
    (data / 'lyrics_cache.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(api.state, 'download_dir', music)
    monkeypatch.setattr(api.state, 'data_dir', data)
    lyrics.init_cache(data)

    got = asyncio.run(api.storage_endpoint())
    assert got['songs'] == 1 and got['bytes'] == 1000
    assert got['caches'] >= 502

    asyncio.run(api.clear_caches_endpoint())
    assert (music / 'A' / 'A - x.dnf').read_bytes() == b'x' * 1000
    assert (music / 'A' / 'A - x.lrc').read_text(encoding='utf-8') == '[00:01.00]mine'
    assert list((data / 'ytdlp-cache').iterdir()) == []


def test_lyrics_are_not_written_for_a_song_that_is_gone(library):
    gone = library / 'A' / 'A - deleted.dnf'
    api._persist_lyrics(gone, 'A', 'deleted', '[00:01.00]la')
    assert not gone.with_suffix('.lrc').exists()
    here = library / 'A' / 'x.dnf'
    api._persist_lyrics(here, 'A', 'x', '[00:01.00]la')
    assert here.with_suffix('.lrc').read_text(encoding='utf-8') == '[00:01.00]la'
