"""Your Soundtrack's card saved as a picture (share.py)."""

import pytest

from dannify import share

PNG = share.PNG + b'\x00' * 32


def test_a_png_is_saved_and_never_over_another(tmp_path):
    first = share.save_png('My 2026 Soundtrack', PNG, tmp_path)
    second = share.save_png('My 2026 Soundtrack', PNG, tmp_path)
    assert first.name == 'My 2026 Soundtrack.png'
    assert second.name == 'My 2026 Soundtrack (2).png'
    assert first.read_bytes() == PNG


def test_only_a_png_is_taken(tmp_path):
    with pytest.raises(ValueError):
        share.save_png('x', b'MZ\x90\x00 not a picture', tmp_path)
    with pytest.raises(ValueError):
        share.save_png('x', share.PNG + b'\x00' * share.MAX_BYTES, tmp_path)


def test_a_name_cannot_lead_anywhere_else(tmp_path):
    path = share.save_png('..\\..\\Windows/System32/evil', PNG, tmp_path)
    assert path.parent == tmp_path
    assert '/' not in path.name and '\\' not in path.name
    assert share.safe_name('') == 'Dannify'
    assert share.safe_name('Ma semaine, octobre') == 'Ma semaine, octobre'
