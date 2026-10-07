"""Shared test setup."""

from __future__ import annotations

import pytest

from dannify import updates


@pytest.fixture(autouse=True)
def _unsigned_test_releases(monkeypatch):
    # The release key in updates.py is the real one, whose private half no
    # test has. The update tests build releases of their own, so signatures
    # are off by default here; the signing tests switch them on with a key
    # they hold (see test_update_signing.py).
    monkeypatch.setattr(updates, 'PUBLIC_KEY', '')
