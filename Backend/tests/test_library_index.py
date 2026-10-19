"""The library opens at once: what each song is, kept between runs, read
again only for a song that changed, and never trusted with other keys."""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path

import pytest

from dannify import library, vault

MP3 = b'ID3\x03\x00\x00\x00\x00\x00\x0f' + b'\xff\xfb\x90\x64' + bytes(range(256)) * 40


@pytest.fixture(autouse=True)
def state(tmp_path):
    saved = (vault._master, vault._keys, vault._state)
    vault._master, vault._keys, vault._state = secrets.token_bytes(32), [], 'ready'
    library.invalidate_cache()
    yield
    vault._master, vault._keys, vault._state = saved
    library._index_path = None
    library._index.update({'ring': None, 'entries': {}, 'square': {}})
    library.invalidate_cache()


def song(folder: Path, name: str, **meta) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    plain = folder / (Path(name).stem + '.mp3')
    plain.write_bytes(MP3)
    head = {'title': Path(name).stem.split(' - ')[-1], 'artist': 'Sauti Sol', 'album': 'LP'}
    head.update(meta)
    return vault.seal(plain, folder / name, head)


@pytest.fixture
def reads(monkeypatch):
    seen: list[str] = []
    real = library._read_tags

    def counting(path):
        seen.append(Path(path).name)
        return real(path)

    monkeypatch.setattr(library, '_read_tags', counting)
    return seen


def restart(data: Path) -> None:
    """What a new run of the app does: nothing in memory, the index on disk."""

    library.init(data)
    library.invalidate_cache()


def test_a_second_run_reads_no_song_again(tmp_path, reads):
    music, data = tmp_path / 'Music', tmp_path / 'data'
    for n in range(4):
        song(music, f'Sauti Sol - Song {n}.dnf')
    restart(data)
    first = library.library(music)
    assert len(reads) == 4
    assert (data / library.INDEX_FILE).is_file()

    reads.clear()
    restart(data)
    again = library.library(music)
    assert reads == []
    assert [t['title'] for t in again['tracks']] == [t['title'] for t in first['tracks']]
    assert again['tracks'][0]['album'] == 'LP'


def test_only_a_song_that_changed_is_read_again(tmp_path, reads):
    music, data = tmp_path / 'Music', tmp_path / 'data'
    keep = song(music, 'Sauti Sol - Keep.dnf')
    change = song(music, 'Sauti Sol - Change.dnf')
    restart(data)
    library.library(music)

    reads.clear()
    time.sleep(0.01)
    song(music, 'Sauti Sol - Change.dnf', album='Deluxe')
    song(music, 'Sauti Sol - New.dnf')
    restart(data)
    tracks = {t['title']: t for t in library.library(music)['tracks']}
    assert sorted(reads) == ['Sauti Sol - Change.dnf', 'Sauti Sol - New.dnf']
    assert tracks['Change']['album'] == 'Deluxe'
    assert keep.is_file() and change.is_file()


def test_a_removed_song_leaves_the_index(tmp_path):
    music, data = tmp_path / 'Music', tmp_path / 'data'
    gone = song(music, 'Sauti Sol - Gone.dnf')
    song(music, 'Sauti Sol - Stays.dnf')
    restart(data)
    library.library(music)
    gone.unlink()
    restart(data)
    assert [t['title'] for t in library.library(music)['tracks']] == ['Stays']
    kept = json.loads((data / library.INDEX_FILE).read_text(encoding='utf-8'))['entries']
    assert not any(k.endswith('Gone.dnf') for k in kept)


def test_other_keys_mean_every_song_is_read_again(tmp_path, reads):
    music, data = tmp_path / 'Music', tmp_path / 'data'
    song(music, 'Sauti Sol - Locked.dnf')
    # Read once with no key that opens it: it does not play.
    mine = vault._master
    vault._master = secrets.token_bytes(32)
    restart(data)
    assert library.library(music)['tracks'][0]['problem'] == vault.LOCKED

    # The key turns up (a keyring unlocked, the library joined): what the
    # index says about the song is wrong now, and is not believed.
    vault._master = mine
    reads.clear()
    restart(data)
    assert library.library(music)['tracks'][0]['problem'] == ''
    assert reads == ['Sauti Sol - Locked.dnf']


def test_a_damaged_index_is_read_past(tmp_path, reads):
    music, data = tmp_path / 'Music', tmp_path / 'data'
    song(music, 'Sauti Sol - One.dnf')
    data.mkdir()
    (data / library.INDEX_FILE).write_text('{"v": 1, "entries": [broken', encoding='utf-8')
    restart(data)
    assert [t['title'] for t in library.library(music)['tracks']] == ['One']
    assert reads == ['Sauti Sol - One.dnf']
    assert json.loads((data / library.INDEX_FILE).read_text(encoding='utf-8'))['v'] == 1


def test_clearing_caches_forgets_the_index(tmp_path, reads):
    music, data = tmp_path / 'Music', tmp_path / 'data'
    song(music, 'Sauti Sol - One.dnf')
    restart(data)
    library.library(music)
    library.forget_index()
    assert not (data / library.INDEX_FILE).exists()
    reads.clear()
    library.library(music)
    assert reads == ['Sauti Sol - One.dnf']


def test_each_album_cover_is_looked_at_once(tmp_path, monkeypatch):
    music, data = tmp_path / 'Music', tmp_path / 'data'
    song(music, 'Sauti Sol - One.dnf', track_number=1)
    song(music, 'Sauti Sol - Two.dnf', track_number=2)
    looked: list[str] = []
    real = vault.cover

    def cover(path):
        looked.append(Path(path).name)
        return real(path)

    monkeypatch.setattr(vault, 'cover', cover)
    restart(data)
    library.library(music)
    assert looked  # the first run looks
    looked.clear()
    restart(data)
    library.library(music)
    assert looked == []  # the next one remembers


def test_without_a_data_folder_nothing_is_kept(tmp_path, reads):
    music = tmp_path / 'Music'
    song(music, 'Sauti Sol - One.dnf')
    library._index_path = None
    library.library(music)
    library.invalidate_cache()
    library.library(music)
    assert reads == ['Sauti Sol - One.dnf', 'Sauti Sol - One.dnf']
    assert not any(p.name == library.INDEX_FILE for p in tmp_path.rglob('*'))


def test_the_index_holds_no_audio_and_no_artwork(tmp_path):
    music, data = tmp_path / 'Music', tmp_path / 'data'
    song(music, 'Sauti Sol - One.dnf')
    restart(data)
    library.library(music)
    raw = (data / library.INDEX_FILE).read_bytes()
    assert MP3[20:60] not in raw
    assert os.path.getsize(data / library.INDEX_FILE) < 4096


def test_a_burst_of_questions_looks_at_the_folder_once(tmp_path, monkeypatch):
    music, data = tmp_path / 'Music', tmp_path / 'data'
    song(music, 'Sauti Sol - One.dnf')
    restart(data)
    looks = []
    real = library._signature
    monkeypatch.setattr(library, '_signature', lambda base: looks.append(1) or real(base))
    library.library(music)
    library.artists(music)
    library.albums(music)
    assert len(looks) == 1
    # Anything the app changes itself says so, and is seen at once.
    song(music, 'Sauti Sol - Two.dnf')
    library.invalidate_cache()
    assert len(library.library(music)['tracks']) == 2
