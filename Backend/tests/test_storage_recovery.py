"""Getting saved music back from the message that says it is not there.

When no key here opens on this account, nothing can be saved and nothing can
be repaired. The window used to say a restart might help, which it never did
for a new PC or a new account. These are the two ways out it offers now: look
again (a keyring that was locked at login is open a minute later), or start
fresh, which adds a key and takes nothing away.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path

import pytest
from fastapi import HTTPException

from dannify import library, vault
from dannify.routes import system
from dannify.routes.common import state

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


def start(data: Path, music: Path) -> None:
    """What a copy of Dannify does at startup."""

    vault._master, vault._keys, vault._state = None, [], 'unknown'
    with vault._opened_lock:
        vault._opened.clear()
    vault.init(data)
    vault.attach(music)


def unreadable_install(tmp_path: Path) -> tuple[Path, Path, bytes]:
    """An installation whose only key was wrapped on some other account."""

    data, music = tmp_path / 'data', tmp_path / 'music'
    store = data / vault.STORE
    store.mkdir(parents=True)
    foreign = secrets.token_bytes(32)
    junk = b'DPA2' + secrets.token_bytes(120)
    (store / f'{vault._fp(foreign)}.dat').write_bytes(junk)
    (store / 'store.json').write_text(json.dumps({'v': 1, 'primary': vault._fp(foreign)}))
    music.mkdir()
    return data, music, junk


def seal_song(folder: Path, name: str) -> Path:
    plain = folder / (Path(name).stem + '.mp3')
    plain.write_bytes(MP3)
    return vault.seal(plain, folder / name, {'title': Path(name).stem, 'artist': 'A'})


# ---------------------------------------------------------------------------
# start_fresh
# ---------------------------------------------------------------------------
def test_keys_that_will_not_open_can_be_started_afresh_without_losing_any(tmp_path):
    data, music, junk = unreadable_install(tmp_path)
    start(data, music)
    assert vault.state() == 'unreadable' and not vault.ready()

    assert vault.start_fresh(data, music) == 'ready'

    assert vault.ready()
    store = data / vault.STORE
    # The old entry is exactly as it was: back on its own account, it opens.
    old = [p for p in store.glob('*.dat') if p.read_bytes() == junk]
    assert len(old) == 1
    assert len(list(store.glob('*.dat'))) == 2
    # The music folder knows the new key too, so its songs open from either.
    assert (music / vault.LIBRARY_STORE / f'{vault._fp(vault._master)}.dat').is_file()
    # And songs save and play again.
    song = seal_song(music, 'A - New.dnf')
    assert vault.inspect(song)[1] == ''
    assert b''.join(vault.open_range(song)) == MP3


def test_a_fresh_start_is_still_there_after_a_restart(tmp_path):
    data, music, _ = unreadable_install(tmp_path)
    start(data, music)
    vault.start_fresh(data, music)
    fresh = vault._master
    song = seal_song(music, 'A - Kept.dnf')

    start(data, music)

    assert vault.ready() and vault._master == fresh
    assert vault.inspect(song)[1] == ''


def test_songs_from_before_stay_where_they_are_for_a_repair(tmp_path):
    data, music, _ = unreadable_install(tmp_path)
    # A song sealed with a key this account cannot open.
    vault._master = secrets.token_bytes(32)
    old_song = seal_song(music, 'A - Before.dnf')
    before = old_song.read_bytes()
    start(data, music)

    vault.start_fresh(data, music)

    assert old_song.read_bytes() == before
    assert vault.inspect(old_song) == (None, vault.LOCKED)


@pytest.mark.parametrize('current', ['ready', 'unwritable', 'unknown'])
def test_start_fresh_is_only_for_keys_that_will_not_open(tmp_path, current):
    data = tmp_path / 'data'
    vault._state = current
    vault._master = secrets.token_bytes(32) if current == 'ready' else None
    held = vault._master

    assert vault.start_fresh(data, None) == current

    assert vault._master == held
    assert not (data / vault.STORE).exists()


def test_start_fresh_that_cannot_write_changes_nothing(tmp_path, monkeypatch):
    data, music, _ = unreadable_install(tmp_path)
    start(data, music)
    monkeypatch.setattr(vault, '_store_key', lambda *a, **k: False)

    assert vault.start_fresh(data, music) == 'unreadable'
    assert not vault.ready()


# ---------------------------------------------------------------------------
# reopen
# ---------------------------------------------------------------------------
def test_looking_again_finds_a_key_that_was_out_of_reach_at_startup(tmp_path, monkeypatch):
    data, music = tmp_path / 'data', tmp_path / 'music'
    start(data, music)
    mine = vault._master
    song = seal_song(music, 'A - Mine.dnf')

    # At the next login the keyring is still locked: nothing opens.
    real = vault._unprotect

    def locked(stored):
        raise OSError('the key store is not available')

    monkeypatch.setattr(vault, '_unprotect', locked)
    start(data, music)
    assert vault.state() == 'unreadable'

    # A minute later it is open, and nobody had to restart anything.
    monkeypatch.setattr(vault, '_unprotect', real)
    assert vault.reopen(data, music) == 'ready'
    assert vault._master == mine
    assert vault.inspect(song)[1] == ''


def test_looking_again_while_still_locked_says_so(tmp_path):
    data, music, _ = unreadable_install(tmp_path)
    start(data, music)
    assert vault.reopen(data, music) == 'unreadable'
    assert not vault.ready()


# ---------------------------------------------------------------------------
# The endpoint and the health check
# ---------------------------------------------------------------------------
class Sockets:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def broadcast(self, message: dict) -> None:
        self.sent.append(message)


@pytest.fixture
def app_state(tmp_path, monkeypatch):
    data, music, _ = unreadable_install(tmp_path)
    start(data, music)
    sockets = Sockets()
    monkeypatch.setattr(state, 'data_dir', data)
    monkeypatch.setattr(state, 'download_dir', music)
    monkeypatch.setattr(state, 'connections', sockets)
    monkeypatch.setattr(state, 'downloader', None)
    return data, music, sockets


def recover(action):
    return asyncio.run(system.recover_storage_endpoint({'action': action}))


def test_the_window_can_start_fresh(app_state):
    _, _, sockets = app_state
    assert recover('fresh') == {'ok': True, 'state': 'ready'}
    assert {'type': 'library_changed'} in sockets.sent


def test_trying_again_that_does_not_work_says_so_honestly(app_state):
    _, _, sockets = app_state
    assert recover('retry') == {'ok': False, 'state': 'unreadable'}
    assert sockets.sent == []


def test_nothing_is_done_when_saved_music_already_works(app_state):
    recover('fresh')
    fresh = vault._master
    assert recover('fresh') == {'ok': True, 'state': 'ready'}
    assert vault._master == fresh


@pytest.mark.parametrize('payload', [None, {}, {'action': 'wipe'}])
def test_only_the_two_ways_out_are_accepted(app_state, payload):
    with pytest.raises(HTTPException) as caught:
        asyncio.run(system.recover_storage_endpoint(payload))
    assert caught.value.status_code == 400


def test_the_health_check_says_which_way_it_is_unavailable(app_state):
    problems = system.health()['problems']
    storage = [p for p in problems if p['code'] == 'storage_unavailable']
    assert storage == [{'code': 'storage_unavailable', 'state': 'unreadable'}]

    recover('fresh')
    codes = [p['code'] for p in system.health()['problems']]
    assert 'storage_unavailable' not in codes
