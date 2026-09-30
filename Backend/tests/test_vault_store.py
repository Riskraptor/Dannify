"""Where the keys live, and why a library can no longer be cut off from them.

The case these tests are built around happened: two copies of Dannify on the
same PC and account ended up with different keys (one had been started inside
another app's sandbox, which gets a private AppData), and songs sealed by one
could not be opened by the other. The fix is that a music folder keeps every
key its songs were sealed with, and each copy joins the folder on its terms.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

import pytest

from dannify import account, library, vault

MP3 = b'ID3\x03\x00\x00\x00\x00\x00\x0f' + b'\xff\xfb\x90\x64' + bytes(range(256)) * 40


@pytest.fixture(autouse=True)
def fresh_module_state():
    saved = (vault._master, vault._keys, vault._state, vault._key_path, vault._library, vault._busy)
    vault._master, vault._keys, vault._state = None, [], 'unknown'
    vault._key_path = vault._library = None
    vault._busy = False
    with vault._opened_lock:
        vault._opened.clear()
    library.invalidate_cache()
    yield
    (vault._master, vault._keys, vault._state, vault._key_path, vault._library, vault._busy) = saved
    library.invalidate_cache()


def seal_with(master: bytes, folder: Path, name: str, payload: bytes = MP3) -> Path:
    """A song sealed with *master*, whatever the module currently holds."""

    before = (vault._master, vault._keys)
    vault._master, vault._keys = master, []
    try:
        folder.mkdir(parents=True, exist_ok=True)
        plain = folder / (Path(name).stem + '.mp3')
        plain.write_bytes(payload)
        return vault.seal(plain, folder / name, {'title': Path(name).stem, 'artist': 'A'})
    finally:
        vault._master, vault._keys = before


def start(data: Path, music: Path) -> None:
    """What a copy of Dannify does at startup."""

    vault._master, vault._keys, vault._state = None, [], 'unknown'
    with vault._opened_lock:
        vault._opened.clear()
    vault.init(data)
    vault.attach(music)


def hidden(path: Path) -> bool:
    if os.name != 'nt':
        return path.name.startswith('.')
    import ctypes

    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    return attrs != -1 and bool(attrs & 0x2)


# ---------------------------------------------------------------------------
# The installation's own store
# ---------------------------------------------------------------------------
def test_a_fresh_installation_makes_one_key_in_its_store(tmp_path):
    vault.init(tmp_path)
    assert vault.ready() and vault.state() == 'ready'
    entries = list((tmp_path / vault.STORE).glob('*.dat'))
    assert len(entries) == 1
    marker = json.loads((tmp_path / vault.STORE / 'store.json').read_text())
    assert marker['primary'] == vault._fp(vault._master)
    assert not (tmp_path / 'vault.key').exists()


def test_a_restart_uses_the_same_key(tmp_path):
    vault.init(tmp_path)
    first = vault._master
    vault._master = None
    vault.init(tmp_path)
    assert vault._master == first


def test_the_old_key_file_is_moved_into_the_store_and_only_then_removed(tmp_path):
    key = secrets.token_bytes(32)
    (tmp_path / 'vault.key').write_bytes(vault._protect(key))
    vault.init(tmp_path)
    assert vault._master == key
    assert not (tmp_path / 'vault.key').exists()
    loaded, named, _ = vault._load_store(tmp_path / vault.STORE)
    assert loaded[0] == key and named


def test_an_old_key_that_will_not_open_is_left_alone_and_none_is_made(tmp_path):
    junk = b'DPA2' + secrets.token_bytes(200)
    (tmp_path / 'vault.key').write_bytes(junk)
    vault.init(tmp_path)
    assert not vault.ready() and vault.state() == 'unreadable'
    assert (tmp_path / 'vault.key').read_bytes() == junk  # untouched
    assert not list((tmp_path / vault.STORE).glob('*.dat'))  # nothing new to orphan it


def test_the_old_spare_holding_the_same_key_is_folded_in(tmp_path):
    key = secrets.token_bytes(32)
    (tmp_path / 'vault.key').write_bytes(vault._protect(key))
    (tmp_path / 'vault.key.bak').write_bytes(b'RAW0' + key)
    vault.init(tmp_path)
    assert vault._master == key and vault._keys == []
    assert not (tmp_path / 'vault.key').exists() and not (tmp_path / 'vault.key.bak').exists()


def test_an_old_spare_with_a_different_key_is_kept_and_its_songs_play(tmp_path):
    main, other = secrets.token_bytes(32), secrets.token_bytes(32)
    (tmp_path / 'vault.key').write_bytes(vault._protect(main))
    (tmp_path / 'vault.key.bak').write_bytes(vault._protect(other))
    song = seal_with(other, tmp_path / 'm', 'A - Old.dnf')
    vault.init(tmp_path)
    assert vault._master == main and vault._keys == [other]
    assert vault.inspect(song)[1] == ''


def test_a_store_entry_that_is_not_what_its_name_says_is_never_overwritten(tmp_path):
    one, two = secrets.token_bytes(32), secrets.token_bytes(32)
    folder = tmp_path / 'store'
    folder.mkdir()
    wrong = folder / f'{vault._fp(one)}.dat'
    wrong.write_bytes(vault._protect(two))
    before = wrong.read_bytes()
    assert vault._store_key(folder, one) is False
    assert wrong.read_bytes() == before


# ---------------------------------------------------------------------------
# The music folder's store
# ---------------------------------------------------------------------------
def test_a_new_music_folder_is_given_the_key_and_it_is_hidden(tmp_path):
    start(tmp_path / 'data', tmp_path / 'music')
    shelf = tmp_path / 'music' / vault.LIBRARY_STORE
    assert (shelf / f'{vault._fp(vault._master)}.dat').is_file()
    assert json.loads((shelf / 'store.json').read_text())['primary'] == vault._fp(vault._master)
    assert hidden(shelf)


def test_a_folder_with_its_own_key_is_joined_on_its_terms(tmp_path):
    music = tmp_path / 'music'
    start(tmp_path / 'first', music)
    theirs = vault._master
    start(tmp_path / 'second', music)  # another copy, a key of its own
    assert vault._master == theirs  # seals the way the folder's songs are
    assert len(vault._keys) == 1  # and still holds its own
    ours = vault._keys[0]
    for store in (music / vault.LIBRARY_STORE, tmp_path / 'second' / vault.STORE):
        found, _, _ = vault._load_store(store)
        assert {theirs, ours} <= set(found)


def test_the_split_that_happened_heals_without_downloading_anything(tmp_path):
    """Songs sealed by a sandboxed copy, then the real copy finds them."""

    music = tmp_path / 'music'
    inside, outside = tmp_path / 'inside', tmp_path / 'outside'
    inside.mkdir()
    outside.mkdir()
    k_inside, k_real = secrets.token_bytes(32), secrets.token_bytes(32)
    # Before this version: each kept a bare key file, and the sandboxed copy
    # sealed songs in the shared music folder with its own.
    (inside / 'vault.key').write_bytes(vault._protect(k_inside))
    (outside / 'vault.key').write_bytes(vault._protect(k_real))
    songs = [seal_with(k_inside, music / 'A', f'A - {n}.dnf') for n in range(3)]

    # The real copy updates first: it cannot open them yet.
    start(outside, music)
    assert vault._master == k_real
    assert all(vault.inspect(s)[1] == vault.LOCKED for s in songs)

    # The sandboxed copy runs once: it joins the folder on the folder's terms
    # and leaves its key there.
    start(inside, music)
    assert vault._master == k_real and k_inside in vault._keys

    # The real copy's next start opens everything, and moves it onto its key.
    start(outside, music)
    assert all(vault.inspect(s)[1] == '' for s in songs)
    done = vault.repair(music)
    assert done['repaired'] == 3 and done['failed'] == 0
    vault._keys = []  # the real key alone now opens every one
    for s in songs:
        assert vault.inspect(s)[1] == ''
        assert b''.join(vault.open_range(s)) == MP3


def test_a_folder_whose_named_key_does_not_open_here_is_not_taken_over(tmp_path):
    music = tmp_path / 'music'
    shelf = music / vault.LIBRARY_STORE
    shelf.mkdir(parents=True)
    foreign = secrets.token_bytes(32)
    (shelf / f'{vault._fp(foreign)}.dat').write_bytes(b'DPA2' + secrets.token_bytes(64))
    (shelf / 'store.json').write_text(json.dumps({'primary': vault._fp(foreign)}))
    start(tmp_path / 'data', music)
    assert vault.ready() and vault._master != foreign
    assert json.loads((shelf / 'store.json').read_text())['primary'] == vault._fp(foreign)
    assert (shelf / f'{vault._fp(vault._master)}.dat').is_file()


def test_no_key_anywhere_is_rescued_by_the_folder(tmp_path):
    """The installation's key will not open, but the folder has one that does."""

    music = tmp_path / 'music'
    start(tmp_path / 'good', music)
    good = vault._master
    broken = tmp_path / 'broken'
    broken.mkdir()
    (broken / 'vault.key').write_bytes(b'DPA2' + secrets.token_bytes(100))
    start(broken, music)
    assert vault.ready() and vault._master == good


# ---------------------------------------------------------------------------
# Opening songs with whichever key fits
# ---------------------------------------------------------------------------
def test_a_song_on_a_second_key_streams_and_seeks_correctly(tmp_path):
    main, other = secrets.token_bytes(32), secrets.token_bytes(32)
    payload = bytes((i * 7) % 256 for i in range(50_000))
    song = seal_with(other, tmp_path, 'A - Seek.dnf', payload=b'ID3\x03' + payload)
    vault._master, vault._keys = main, [other]
    whole = b''.join(vault.open_range(song))
    assert whole == b'ID3\x03' + payload
    for start_at, length in ((0, 10), (1000, 777), (63, 130), (49_990, 100)):
        assert b''.join(vault.open_range(song, start_at, length)) == whole[start_at:start_at + length]
    assert vault._opened_with(song) == other


def test_a_replaced_file_is_not_opened_with_a_remembered_key(tmp_path):
    one, two = secrets.token_bytes(32), secrets.token_bytes(32)
    vault._master, vault._keys = one, [two]
    song = seal_with(two, tmp_path, 'A - Swap.dnf')
    assert vault.inspect(song)[1] == ''
    assert vault._opened_with(song) == two
    fresh = seal_with(one, tmp_path / 'x', 'A - Swap.dnf', payload=MP3 + b'!')
    os.replace(fresh, song)
    assert b''.join(vault.open_range(song)) == MP3 + b'!'
    assert vault._opened_with(song) == one


def test_the_store_is_never_mistaken_for_music(tmp_path):
    music = tmp_path / 'music'
    start(tmp_path / 'data', music)
    seal_with(vault._master, music / 'A', 'A - Song.dnf')
    tracks = library.library(music)['tracks']
    assert [t['file'] for t in tracks] == ['A/A - Song.dnf']


# ---------------------------------------------------------------------------
# The index, and other things that used to sit in the open
# ---------------------------------------------------------------------------
def test_old_index_files_are_folded_into_the_hidden_one_and_removed(tmp_path):
    music = tmp_path / 'music'
    (music / 'Artist').mkdir(parents=True)
    (music / vault.INDEX).write_text(json.dumps({
        'Artist/Artist - One.dnf': {'title': 'One', 'artist': 'Artist', 'video_id': ''},
    }))
    (music / 'Artist' / vault.INDEX).write_text(json.dumps({
        'Artist - One.dnf': {'title': 'One', 'artist': 'Artist', 'video_id': 'ONEONEONEON'},
        'Artist - Two.dnf': {'title': 'Two', 'artist': 'Artist', 'video_id': 'TWOTWOTWOTW'},
    }))
    start(tmp_path / 'data', music)
    merged = vault.read_index(vault.index_path(music))
    assert merged['Artist/Artist - One.dnf']['video_id'] == 'ONEONEONEON'
    assert merged['Artist/Artist - Two.dnf']['title'] == 'Two'
    assert not (music / vault.INDEX).exists()
    assert not (music / 'Artist' / vault.INDEX).exists()
    assert vault.lookup(music, music / 'Artist' / 'Artist - Two.dnf')['video_id'] == 'TWOTWOTWOTW'


def test_the_conversion_lock_lives_in_the_store(tmp_path):
    lock = vault._claim(tmp_path)
    try:
        assert lock == tmp_path / vault.LIBRARY_STORE / 'busy'
        assert not (tmp_path / '.dannify-converting').exists()
    finally:
        vault._release(lock)


def test_an_old_lock_left_by_a_run_that_is_gone_is_cleared(tmp_path):
    old = tmp_path / '.dannify-converting'
    old.write_text('999999')  # no such process
    vault._clear_old_lock(tmp_path)
    assert not old.exists()


# ---------------------------------------------------------------------------
# The YouTube sign-in
# ---------------------------------------------------------------------------
COOKIES = {'__Secure-3PAPISID': 'secret-session-value-1234', 'SID': 'another-secret-5678'}


@pytest.fixture
def signed_out():
    saved = dict(account._state)
    account._state.update(cookies={}, profile={}, path=None)
    yield
    account._state.clear()
    account._state.update(saved)


def test_a_plain_sign_in_is_encrypted_and_the_plain_file_removed(tmp_path, signed_out):
    (tmp_path / 'account.json').write_text(json.dumps({'cookies': COOKIES, 'profile': {'name': 'D'}}))
    account.init(tmp_path)
    assert account.is_signed_in() if hasattr(account, 'is_signed_in') else account._state['cookies'] == COOKIES
    assert account._state['cookies'] == COOKIES
    stored = (tmp_path / 'account.dat').read_bytes()
    assert b'secret-session-value' not in stored  # not readable as it sits
    assert not (tmp_path / 'account.json').exists()


def test_an_encrypted_sign_in_survives_a_restart(tmp_path, signed_out):
    (tmp_path / 'account.json').write_text(json.dumps({'cookies': COOKIES, 'profile': {}}))
    account.init(tmp_path)
    account._state.update(cookies={}, profile={})
    account.init(tmp_path)
    assert account._state['cookies'] == COOKIES


def test_signing_out_leaves_no_copy_of_the_session(tmp_path, signed_out):
    (tmp_path / 'account.json').write_text(json.dumps({'cookies': COOKIES, 'profile': {}}))
    account.init(tmp_path)
    account.sign_out()
    assert not (tmp_path / 'account.dat').exists()
    assert not (tmp_path / 'account.json').exists()


def test_migrate_only_seals_what_this_app_downloaded(tmp_path):
    """Pointing the app at an existing Music folder must not seal (and delete)
    somebody's own collection. Only files carrying the app's download tag are
    converted."""

    from mutagen.id3 import ID3, TIT2

    from dannify import downloader

    data, music = tmp_path / 'data', tmp_path / 'Music'
    start(data, music)

    # A file from some other program, with ordinary tags and no video id.
    theirs = music / 'iTunes' / 'Adele' / '01 Rolling in the Deep.mp3'
    theirs.parent.mkdir(parents=True)
    theirs.write_bytes(MP3)
    tags = ID3()
    tags.add(TIT2(encoding=3, text='Rolling in the Deep'))
    tags.save(theirs)
    playlist = music / 'mine.m3u'
    playlist.write_text('iTunes/Adele/01 Rolling in the Deep.mp3\n', encoding='utf-8')

    # One of ours, from before containers existed.
    ours = music / 'Sauti Sol' / 'Sauti Sol - Suzanna.mp3'
    ours.parent.mkdir(parents=True)
    # Real MPEG frames (MPEG-1 layer III, 128 kbps, 44.1 kHz: 417 bytes each),
    # so the tag writer accepts it as an MP3.
    ours.write_bytes((bytes.fromhex('fffb9064') + bytes(413)) * 20)
    downloader.embed_video_id(ours, 'KNEd-OkExKY')
    assert library._read_video_id_tag(ours) == 'KNEd-OkExKY'

    done = vault.migrate(music)

    assert done['sealed'] == 1
    assert theirs.is_file() and not theirs.with_suffix('.dnf').exists()
    assert not ours.exists() and ours.with_suffix('.dnf').is_file()
    assert playlist.read_text(encoding='utf-8') == 'iTunes/Adele/01 Rolling in the Deep.mp3\n'
