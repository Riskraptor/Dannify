"""Unit tests for the _sanitize() filesystem-name helper."""

from __future__ import annotations

import pytest

from dannify.downloader import _sanitize


@pytest.mark.parametrize('char', list(r'\/:*?"<>|'))
def test_sanitize_removes_filesystem_unsafe_chars(char):
    assert char not in _sanitize(f'name{char}test')


def test_sanitize_normal_string_unchanged():
    assert _sanitize('Arctic Monkeys') == 'Arctic Monkeys'


def test_sanitize_empty_string_returns_unknown():
    assert _sanitize('') == 'unknown'


def test_sanitize_none_treated_as_empty():
    assert _sanitize(None) == 'unknown'  # type: ignore[arg-type]


def test_sanitize_strips_leading_trailing_whitespace():
    assert _sanitize('  hello  ') == 'hello'


def test_sanitize_strips_leading_dot():
    assert _sanitize('.hidden') == 'hidden'


def test_sanitize_strips_trailing_dot():
    assert _sanitize('file.') == 'file'


def test_sanitize_all_unsafe_returns_unknown():
    assert _sanitize('???') == 'unknown'


def test_sanitize_control_chars_removed():
    assert _sanitize('title\x00\x1f') == 'title'


def test_sanitize_unicode_letters_kept():
    assert _sanitize('Sigur Rós') == 'Sigur Rós'


def test_sanitize_numbers_kept():
    assert _sanitize('2Pac') == '2Pac'


def test_sanitize_hyphen_kept():
    assert _sanitize('Post-Malone') == 'Post-Malone'


def test_sanitize_marks_a_device_name_before_its_dot():
    # The device is whatever comes before the first dot.
    assert _sanitize('Con.Air - Theme') == 'Con_.Air - Theme'
    assert _sanitize('Aux') == 'Aux_'
    assert _sanitize('Auxiliary') == 'Auxiliary'


def test_sanitize_caps_the_length_on_a_word_boundary():
    long_name = ', '.join(['Some Orchestra Member'] * 10) + ' - Symphony No. 9 in D minor'
    out = _sanitize(long_name)
    assert len(out) <= 120
    assert not out.endswith((' ', ',', '.'))
    assert _sanitize('x' * 400, 80) == 'x' * 80


def test_sanitize_keeps_letters_in_any_script():
    assert _sanitize('Beyoncé') == 'Beyoncé'
    assert _sanitize('米津玄師') == '米津玄師'
    assert _sanitize('P!nk') == 'P!nk'
