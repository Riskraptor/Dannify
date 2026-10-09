"""Linux and macOS keep secrets wrapped with a key from the system keyring
(keystore.py); here it is a file of the test's own (see conftest)."""

from __future__ import annotations

import os

import pytest

from dannify import keystore, vault


def test_a_wrapped_secret_reads_back_and_is_not_readable_as_it_sits():
    raw = b'secret-session-value' * 20
    wrapped = vault._keystore_wrap(raw)
    assert wrapped[:4] == b'FKW1' and b'secret-session-value' not in wrapped
    assert vault._unprotect(wrapped) == raw
    assert vault._keystore_wrap(raw) != wrapped  # a fresh nonce every time


def test_a_tampered_or_foreign_wrapping_is_refused(monkeypatch, tmp_path):
    wrapped = bytearray(vault._keystore_wrap(b'k' * 32))
    wrapped[-1] ^= 1
    with pytest.raises(ValueError):
        vault._unprotect(bytes(wrapped))
    good = vault._keystore_wrap(b'k' * 32)
    # Another machine's key store: same format, different key.
    monkeypatch.setenv('DANNIFY_KEYWRAP_FILE', str(tmp_path / 'other'))
    keystore.forget_cache()
    keystore.wrapping_key('file')
    with pytest.raises(ValueError):
        vault._unprotect(good)


def test_the_key_file_is_only_for_this_user():
    keystore.wrapping_key('file')
    path = keystore._fallback_file()
    assert path.is_file()
    if os.name != 'nt':
        assert path.stat().st_mode & 0o077 == 0


def test_a_store_that_loses_what_it_was_given_is_not_trusted(monkeypatch):
    monkeypatch.setitem(keystore._STORES, 'file', (lambda: None, lambda value: True))
    keystore.forget_cache()
    assert keystore.wrapping_key('file') is None
    assert vault._keystore_wrap(b'x') is None  # so _protect falls back, never loses it


def test_plain_entries_from_before_still_open():
    assert vault._unprotect(b'RAW0' + b'k' * 32) == b'k' * 32
