"""Special days: the dates, and the splash that greets them."""

import datetime
import os
import tempfile

import pytest

from dannify import occasions

# The shell's core reads its data folder (and sets the log file) when it is
# first imported: a throwaway one here, and nothing left behind for other
# tests, as test_shell_core.py does.
_saved = {k: os.environ.get(k) for k in ('DANNIFY_DATA_DIR', 'DANNIFY_LOG_FILE')}
os.environ['DANNIFY_DATA_DIR'] = tempfile.mkdtemp(prefix='dannify-occasions-')
from dannify.shell import core  # noqa: E402

# The Windows splash, only where its window can be: its module reaches for
# Windows itself when imported.
places = None
if os.name == 'nt':
    from dannify.shell.windows import places  # noqa: E402

for _key, _value in _saved.items():
    if _value is None:
        os.environ.pop(_key, None)
    else:
        os.environ[_key] = _value


@pytest.mark.parametrize(('day', 'name'), [
    ('2026-12-17', ''),
    ('2026-12-18', 'christmas'),
    ('2026-12-25', 'christmas'),
    ('2026-12-26', 'christmas'),
    ('2026-12-27', ''),
    ('2026-12-30', ''),
    ('2026-12-31', 'newyear'),
    ('2027-01-01', 'newyear'),
    ('2027-01-02', 'newyear'),
    ('2027-01-03', ''),
    ('2026-07-04', ''),
])
def test_the_days_and_what_they_are(day, name):
    assert occasions.today(datetime.date.fromisoformat(day)) == name


def test_an_ordinary_day_adds_nothing_to_the_splash():
    assert occasions.splash_extras(datetime.date(2026, 10, 20)) == ('', '', '')


def test_christmas_brings_a_greeting_and_snow_and_keeps_still_for_reduced_motion():
    hint, css, fx = occasions.splash_extras(datetime.date(2026, 12, 24), seed=1)
    assert hint.startswith('Merry Christmas')
    assert fx.count("class='f'") == 22
    assert 'prefers-reduced-motion' in css and 'rotate' not in css


def test_the_new_year_brings_confetti():
    hint, css, fx = occasions.splash_extras(datetime.date(2027, 1, 1), seed=1)
    assert hint.startswith('Happy New Year')
    assert 'rotate(540deg)' in css and 'background:#' in fx


def _splashes():
    pages = [core.splash_html('dark')]
    if places is not None:
        pages.append(places._splash_html('dark', True))
    return pages


def test_both_splashes_wear_it(monkeypatch):
    monkeypatch.setattr(occasions, 'today', lambda now=None: 'christmas')
    for page in _splashes():
        assert 'Merry Christmas' in page and "class='fx'" in page
    # A page with its own words (could not start) keeps them.
    failed = core.failed_html('dark')
    assert 'Merry Christmas' not in failed and 'could not start' in failed
    assert "class='fx'" not in failed


def test_turned_off_the_splash_is_plain_again(monkeypatch):
    monkeypatch.setattr(occasions, 'today', lambda now=None: 'christmas')
    monkeypatch.setattr(core, 'read_prefs', lambda: {'seasonal': False})
    if places is not None:
        monkeypatch.setattr(places, '_read_prefs', lambda: {'seasonal': False})
    for page in _splashes():
        assert 'Merry Christmas' not in page and "class='fx'" not in page
        assert 'Starting your music' in page


@pytest.mark.skipif(os.name != 'nt', reason="the Windows shell's own call")
def test_the_switch_is_kept_where_the_splash_reads_it(monkeypatch):
    from dannify.shell.windows import actions

    kept = {}
    monkeypatch.setattr(actions, '_read_prefs', lambda: dict(kept))
    monkeypatch.setattr(actions, '_write_prefs', lambda patch: kept.update(patch))
    api = object.__new__(actions.ActionsMixin)
    api.app_set_seasonal(False)
    assert kept == {'seasonal': False}
    api.app_set_seasonal(True)
    assert kept == {'seasonal': True}
