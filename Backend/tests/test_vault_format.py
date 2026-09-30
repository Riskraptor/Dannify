"""The sealed file format: DNF2, and DNF1 files from before it.

DNF1 encrypted a song's header and its audio with the same key, both from
block zero, so laying one ciphertext over the other gave away the header to
anyone who could guess the first bytes of the audio (and audio files start
with well known bytes). DNF2 gives the header a key of its own. Every file
sealed from 4.0 is DNF2; every DNF1 file must still open exactly as before.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

import pytest

from dannify import vault

MP3 = b'ID3\x03\x00\x00\x00\x00\x00\x0f' + b'\xff\xfb\x90\x64' + bytes(range(256)) * 60


@pytest.fixture(autouse=True)
def key():
    saved = (vault._master, vault._keys, vault._state)
    vault._master, vault._keys, vault._state = secrets.token_bytes(32), [], 'ready'
    with vault._opened_lock:
        vault._opened.clear()
    yield vault._master
    vault._master, vault._keys, vault._state = saved
    with vault._opened_lock:
        vault._opened.clear()


def _seal(tmp_path: Path, name: str = 'Song.dnf') -> Path:
    plain = tmp_path / 'Song.mp3'
    plain.write_bytes(MP3)
    return vault.seal(plain, tmp_path / name, {'title': 'Song', 'artist': 'Someone', 'album': 'An Album'})


def _seal_v1(tmp_path: Path, master: bytes, head: dict) -> Path:
    """A file exactly as Dannify 3.x wrote it."""

    nonce = secrets.token_bytes(vault.NONCE_LEN)
    k = vault._derive(master, nonce)
    blob = vault._xor(k, nonce, json.dumps(head).encode('utf-8'), 0)
    path = tmp_path / 'Old.dnf'
    path.write_bytes(
        vault.MAGIC_V1 + nonce + len(blob).to_bytes(4, 'little') + blob + vault._xor(k, nonce, MP3, 0)
    )
    return path


def test_new_files_are_dnf2_and_everything_reads_them(tmp_path):
    path = _seal(tmp_path)
    assert path.read_bytes()[:4] == b'DNF2'
    assert vault.is_sealed(path)
    head, problem = vault.inspect(path)
    assert problem == '' and head['album'] == 'An Album'
    assert vault.read_header(path)['title'] == 'Song'
    assert b''.join(vault.open_range(path)) == MP3
    assert b''.join(vault.open_range(path, 1000, 500)) == MP3[1000:1500]


def test_files_from_before_still_open(tmp_path, key):
    path = _seal_v1(tmp_path, key, {'title': 'Old one', 'ext': '.mp3', 'size': len(MP3), 'v': 2})
    assert vault.is_sealed(path)
    head, problem = vault.inspect(path)
    assert problem == '' and head['title'] == 'Old one'
    assert vault.read_header(path)['title'] == 'Old one'
    with vault._opened_lock:
        vault._opened.clear()  # and when the key has to be found again
    assert b''.join(vault.open_range(path, 300, 700)) == MP3[300:1000]


def test_the_header_can_no_longer_be_read_off_the_audio(tmp_path):
    path = _seal(tmp_path)
    data = path.read_bytes()
    length = int.from_bytes(data[4 + vault.NONCE_LEN:4 + vault.NONCE_LEN + 4], 'little')
    start = 4 + vault.NONCE_LEN + 4
    header_ct = data[start:start + length]
    audio_ct = data[start + length:start + 2 * length]
    # With one keystream for both, header XOR audio (both encrypted) equals
    # header XOR audio in the clear, so knowing the audio's first bytes gives
    # the header away. With two, it is noise.
    guess = bytes(a ^ b ^ c for a, b, c in zip(header_ct, audio_ct, MP3))
    assert not guess.startswith(b'{"')


def test_a_file_from_another_key_is_locked_in_both_formats(tmp_path, key):
    new = _seal(tmp_path, 'New.dnf')
    old = _seal_v1(tmp_path, key, {'title': 'Old', 'ext': '.mp3', 'size': len(MP3)})
    vault._master = secrets.token_bytes(32)
    with vault._opened_lock:
        vault._opened.clear()
    assert vault.inspect(new)[1] == vault.LOCKED
    assert vault.inspect(old)[1] == vault.LOCKED


def test_something_else_with_the_extension_is_not_a_song(tmp_path):
    path = tmp_path / 'x.dnf'
    path.write_bytes(b'DNF3' + bytes(100))
    assert not vault.is_sealed(path)
    assert vault.read_header(path) is None
    assert vault.inspect(path)[1] == vault.DAMAGED
    with pytest.raises(ValueError):
        b''.join(vault.open_range(path))


def test_a_paused_stream_does_not_hold_the_file(tmp_path):
    """Half-way through a response (a paused player stops reading), the song
    can still be deleted: Windows refuses while a handle is open."""

    import secrets as _secrets

    from dannify import vault as _vault

    saved = (_vault._master, _vault._keys, _vault._state)
    _vault._master, _vault._keys, _vault._state = _secrets.token_bytes(32), [], 'ready'
    try:
        plain = tmp_path / 'A - x.mp3'
        audio = bytes(range(256)) * 4096  # 1 MiB: several pieces
        plain.write_bytes(b'ID3' + audio)
        sealed = _vault.seal(plain, tmp_path / 'A - x.dnf', {'title': 'x'})
        stream = _vault.open_range(sealed, 0)
        first = next(stream)
        assert first[:3] == b'ID3'
        sealed.unlink()  # used to raise PermissionError [WinError 32]
        assert not sealed.exists()
        stream.close()
    finally:
        _vault._master, _vault._keys, _vault._state = saved


def test_ranges_still_decrypt_correctly(tmp_path):
    import secrets as _secrets

    from dannify import vault as _vault

    saved = (_vault._master, _vault._keys, _vault._state)
    _vault._master, _vault._keys, _vault._state = _secrets.token_bytes(32), [], 'ready'
    try:
        payload = b'ID3' + _secrets.token_bytes(700_001)
        plain = tmp_path / 'B - y.mp3'
        plain.write_bytes(payload)
        sealed = _vault.seal(plain, tmp_path / 'B - y.dnf', {'title': 'y'})
        assert b''.join(_vault.open_range(sealed, 0)) == payload
        for start, length in ((0, 10), (5, 1000), (262_139, 70_000), (699_990, None)):
            got = b''.join(_vault.open_range(sealed, start, length))
            want = payload[start:] if length is None else payload[start:start + length]
            assert got == want, (start, length)
    finally:
        _vault._master, _vault._keys, _vault._state = saved
