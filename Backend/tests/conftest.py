"""Shared test setup."""

from __future__ import annotations

import pytest

from dannify import updates


@pytest.fixture(autouse=True)
def _private_key_store(monkeypatch, tmp_path_factory):
    # Linux and macOS wrap secrets with a key from the system keyring. Tests
    # must never write into the real one, so they get a file of their own.
    from dannify import keystore

    monkeypatch.setenv('DANNIFY_KEYSTORE', 'file')
    monkeypatch.setenv('DANNIFY_KEYWRAP_FILE', str(tmp_path_factory.mktemp('keys') / '.keywrap'))
    keystore.forget_cache()
    yield
    keystore.forget_cache()


@pytest.fixture(autouse=True)
def _unsigned_test_releases(monkeypatch):
    # The release key in updates.py is the real one, whose private half no
    # test has. The update tests build releases of their own, so signatures
    # are off by default here; the signing tests switch them on with a key
    # they hold (see test_update_signing.py).
    monkeypatch.setattr(updates, 'PUBLIC_KEY', '')


@pytest.fixture(autouse=True)
def _windows_updater(request, monkeypatch):
    # The older updater tests are about the Windows updater (its setup and
    # package files), so on Linux and macOS they run as Windows would.
    # test_update_platforms covers every platform itself.
    name = request.module.__name__
    if 'update' not in name or name.endswith('test_update_platforms'):
        return
    from dannify import osenv, release_assets

    for module in (osenv, release_assets):
        monkeypatch.setattr(module, 'IS_WINDOWS', True)
        monkeypatch.setattr(module, 'IS_MAC', False)
    monkeypatch.setattr(osenv, 'IS_LINUX', False)
    monkeypatch.setattr(osenv, 'PLATFORM', 'windows')
