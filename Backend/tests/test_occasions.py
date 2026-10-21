"""Special days: the calendar, where someone is, and the splash that greets
the day. The window (frontend/src/__tests__/occasions.test.js) is tested on
the same days, and must decide them the same way."""

import datetime
import json
import os
import tempfile
from pathlib import Path

import pytest

from dannify import occasions, occasions_table

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

ROOT = Path(__file__).resolve().parents[2]


def _day(iso: str) -> datetime.date:
    return datetime.date.fromisoformat(iso)


def _name(found) -> str:
    if found is None:
        return ''
    return f"national:{found['names']['en']}" if found.get('kind') == 'national' else found['id']


def test_the_window_the_splash_and_the_installer_read_one_calendar():
    window = json.loads((ROOT / 'frontend' / 'src' / 'model' / 'occasions.json').read_text(encoding='utf-8'))
    installer = json.loads((ROOT / 'installer' / 'UI' / 'Occasions.json').read_text(encoding='utf-8'))
    assert window == occasions_table.DATA == installer
    assert occasions_table.DATA['years'][0] <= datetime.date.today().year <= occasions_table.DATA['years'][1]


# The same days as the window's test.
@pytest.mark.parametrize(('iso', 'region', 'want'), [
    ('2026-06-01', 'KE', 'national:Madaraka Day'),
    ('2026-10-20', 'KE', 'national:Mashujaa Day'),
    ('2026-12-12', 'KE', 'national:Jamhuri Day'),
    ('2026-10-21', 'KE', ''),
    ('2026-03-20', 'KE', 'eid_fitr'),
    ('2026-05-27', 'KE', 'eid_adha'),
    ('2026-04-05', 'KE', 'easter'),
    ('2026-12-17', 'KE', ''),
    ('2026-12-18', 'KE', 'christmas'),
    ('2026-12-26', 'KE', 'christmas'),
    ('2026-12-27', 'KE', ''),
    ('2026-12-31', 'KE', 'newyear'),
    ('2027-01-02', 'KE', 'newyear'),
    ('2027-01-03', 'KE', ''),
    ('2026-02-14', 'KE', 'valentines'),
    ('2026-03-21', 'SG', 'eid_fitr'),
    ('2026-02-17', 'CN', 'lunar_new_year'),
    ('2026-11-08', 'IN', 'diwali'),
    ('2026-03-04', 'IN', 'holi'),
    ('2026-04-12', 'GR', 'orthodox_easter'),
    ('2026-07-04', 'US', 'national:Independence Day'),
    ('2026-11-26', 'US', 'thanksgiving'),
    ('2026-12-05', 'IL', 'hanukkah'),
    ('2026-10-31', 'US', 'halloween'),
    ('2026-03-17', 'IE', "national:Saint Patrick's Day"),
    ('2026-06-21', 'DE', 'world_music_day'),
    ('2026-06-21', 'KE', 'fathers_day'),
    ('2026-05-10', 'KE', 'mothers_day'),
    ('2026-02-14', 'PK', ''),
    ('2026-12-25', 'SA', ''),
    ('2026-10-31', 'KE', ''),
    ('2026-12-25', '', 'christmas'),
    ('2026-12-12', '', ''),
])
def test_the_days_all_year_where_they_are_kept(iso, region, want):
    assert _name(occasions.today(_day(iso), region)) == want


@pytest.mark.parametrize(('zone', 'system', 'languages', 'want'), [
    ('Africa/Nairobi', 'US', (), 'KE'),
    ('Africa/Nairobi', 'TZ', (), 'TZ'),
    ('Africa/Nairobi', 'US', ('sw-UG', 'en'), 'UG'),
    ('America/New_York', 'US', (), 'US'),
    ('Europe/Paris', 'US', ('fr-FR',), 'FR'),
    ('Etc/UTC', 'de', (), 'DE'),
    ('', '', ('pt-BR',), 'BR'),
    ('', '', (), ''),
])
def test_where_someone_is_the_same_reckoning_as_the_window(zone, system, languages, want):
    assert occasions.detect_region(zone, system, languages) == want


def test_windows_zone_names_lead_to_the_zone(monkeypatch):
    assert occasions_table.DATA['windows']['E. Africa Standard Time'] == 'Africa/Nairobi'
    monkeypatch.setattr(occasions, 'time_zone', lambda: 'Africa/Nairobi')
    monkeypatch.setattr(occasions, 'system_region', lambda: 'US')
    assert occasions.guess_region() == 'KE'


def test_a_countrys_day_greets_by_name_with_its_flag():
    jamhuri = occasions.today(_day('2026-12-12'), 'KE')
    assert occasions.title_of(jamhuri) == 'Happy Jamhuri Day'
    assert occasions.title_of(jamhuri, 'sw') == 'Happy Siku ya Jamhuri'
    assert occasions.look_of(jamhuri)['palette'] == occasions_table.DATA['flags']['KE']


def test_an_ordinary_day_adds_nothing_to_the_splash():
    assert occasions.splash_extras(_day('2026-10-21'), region='KE') == ('', '', '')


@pytest.mark.parametrize(('iso', 'region', 'greeting', 'piece'), [
    ('2026-12-24', 'KE', 'Merry Christmas', 'border-radius:50%'),
    ('2027-01-01', 'KE', 'Happy New Year', 'box-shadow'),
    ('2026-12-12', 'KE', 'Happy Jamhuri Day', 'background:#BB0000'),
    ('2026-02-14', 'KE', 'Happy Valentine’s Day', '♥'),
    ('2026-06-21', 'DE', 'Happy World Music Day', '♪'),
    ('2026-03-04', 'IN', 'Happy Holi', 'radial-gradient'),
])
def test_each_day_its_greeting_and_its_look_on_the_splash(iso, region, greeting, piece):
    hint, css, fx = occasions.splash_extras(_day(iso), seed=1, region=region)
    assert hint.startswith(greeting)
    assert fx.count("class='f'") == 26
    assert piece in fx


def test_less_motion_holds_it_still_instead_of_hiding_it():
    _, css, fx = occasions.splash_extras(_day('2026-12-24'), seed=1, region='KE')
    assert '@media (prefers-reduced-motion:reduce){.f{animation:none' in css
    assert 'display:none' not in css


def test_white_pieces_go_pale_blue_on_a_light_splash():
    _, _, dark = occasions.splash_extras(_day('2026-12-24'), seed=1, region='KE')
    _, _, light = occasions.splash_extras(_day('2026-12-24'), seed=1, region='KE', light=True)
    assert '#ffffff' in dark and '#ffffff' not in light and '#96b4d7' in light


def _splashes():
    pages = [core.splash_html('dark')]
    if places is not None:
        pages.append(places._splash_html('dark', True))
    return pages


def test_both_splashes_wear_it_where_the_window_said_we_are(monkeypatch):
    monkeypatch.setattr(occasions, 'today', lambda now=None, region='': (
        occasions.occasions_on(_day('2026-12-12'), region) or [None])[0])
    monkeypatch.setattr(core, 'read_prefs', lambda: {'region': 'KE'})
    if places is not None:
        monkeypatch.setattr(places, '_read_prefs', lambda: {'region': 'KE'})
    for page in _splashes():
        assert 'Happy Jamhuri Day' in page and "class='fx'" in page
    # A page with its own words (could not start) keeps them.
    failed = core.failed_html('dark')
    assert 'Jamhuri' not in failed and 'could not start' in failed
    assert "class='fx'" not in failed


def test_before_the_window_has_said_the_computer_is_asked(monkeypatch):
    monkeypatch.setattr(occasions, 'today', lambda now=None, region='': (
        occasions.occasions_on(_day('2026-12-12'), region) or [None])[0])
    monkeypatch.setattr(occasions, 'guess_region', lambda: 'KE')
    monkeypatch.setattr(core, 'read_prefs', lambda: {})
    assert 'Happy Jamhuri Day' in core.splash_html('dark')


@pytest.mark.skipif(os.name != 'nt', reason="the Windows shell's own call")
def test_the_region_is_kept_where_the_splash_reads_it(monkeypatch):
    from dannify.shell.windows import actions

    kept = {}
    monkeypatch.setattr(actions, '_read_prefs', lambda: dict(kept))
    monkeypatch.setattr(actions, '_write_prefs', lambda patch: kept.update(patch))
    api = object.__new__(actions.ActionsMixin)
    api.app_set_region('ke')
    assert kept == {'region': 'KE'}
    api.app_set_region('not a country')
    assert kept == {'region': 'KE'}


# The words the window sends, in its own language, for the next start.
_SW = {
    'lang': 'sw',
    'starting': 'Muziki wako unaanza…',
    'national': 'Heri ya {name}!',
    'titles': {'christmas': 'Krismasi Njema', 'newyear': 'Heri ya Mwaka Mpya {year}'},
}


def test_the_window_s_words_are_kept_only_as_short_plain_texts():
    assert occasions.clean_words(None) == {}
    assert occasions.clean_words('Krismasi') == {}
    clean = occasions.clean_words({
        **_SW,
        'lang': 'not a language',
        'starting': 'Muziki\nwako   unaanza…',
        'titles': {'christmas': 'x' * 500, 'made_up_day': 'Hello', 'easter': 42},
        'script': '<script>',
    })
    assert 'lang' not in clean and 'script' not in clean
    assert clean['starting'] == 'Muziki wako unaanza…'
    assert clean['titles'] == {'christmas': 'x' * 80}


def test_the_splash_greets_in_the_window_s_language():
    hint, _, _ = occasions.splash_extras(_day('2026-12-24'), seed=1, region='KE', words=_SW)
    assert hint == 'Krismasi Njema · Muziki wako unaanza…'
    hint, _, _ = occasions.splash_extras(_day('2027-01-01'), seed=1, region='KE', words=_SW)
    assert hint.startswith('Heri ya Mwaka Mpya 2027')
    # A country's own day, under its name in that language.
    hint, _, _ = occasions.splash_extras(_day('2026-12-12'), seed=1, region='KE', words=_SW)
    assert hint.startswith('Heri ya Siku ya Jamhuri!')
    # A day the window sent no words for: English, rather than nothing.
    hint, _, _ = occasions.splash_extras(_day('2026-02-14'), seed=1, region='KE', words=_SW)
    assert hint.startswith('Happy Valentine’s Day · Muziki')


def test_the_splash_s_words_cannot_write_into_the_page():
    words = {'starting': '<img src=x onerror=alert(1)>', 'titles': {'christmas': '<b>Hi</b>'}}
    hint, _, _ = occasions.splash_extras(_day('2026-12-24'), seed=1, region='KE', words=words)
    assert '<' not in hint and '&lt;b&gt;' in hint
    assert '<img' not in occasions.starting_words(words)


def test_an_ordinary_day_s_splash_speaks_the_window_s_language(monkeypatch):
    monkeypatch.setattr(occasions, 'today', lambda now=None, region='': None)
    prefs = {'region': 'KE', 'splash': _SW}
    monkeypatch.setattr(core, 'read_prefs', lambda: prefs)
    if places is not None:
        monkeypatch.setattr(places, '_read_prefs', lambda: prefs)
    for page in _splashes():
        assert 'Muziki wako unaanza…' in page and 'Starting your music' not in page
    monkeypatch.setattr(core, 'read_prefs', lambda: {})
    assert 'Starting your music…' in core.splash_html('dark')


@pytest.mark.skipif(os.name != 'nt', reason="the Windows shell's own call")
def test_the_splash_words_are_kept_where_the_splash_reads_them(monkeypatch):
    from dannify.shell.windows import actions

    kept, writes = {}, []
    monkeypatch.setattr(actions, '_read_prefs', lambda: dict(kept))
    monkeypatch.setattr(actions, '_write_prefs', lambda patch: (writes.append(patch), kept.update(patch)))
    api = object.__new__(actions.ActionsMixin)
    api.app_set_splash_words(_SW)
    assert kept['splash'] == occasions.clean_words(_SW)
    # The same words again: nothing written.
    api.app_set_splash_words(_SW)
    assert len(writes) == 1
    api.app_set_splash_words('nonsense')
    assert len(writes) == 1


# Two dates of one holiday, which may look alike.
_TWINS = {'orthodox_christmas': 'christmas', 'thanksgiving_ca': 'thanksgiving'}
_REPO = Path(__file__).resolve().parents[2]


def test_every_special_day_has_a_look_of_its_own():
    looks = occasions_table.DATA['looks']
    seen = {}
    for row in occasions_table.DATA['occasions']:
        look = looks[row['look']]
        pair = (look['shape'], look['motion'])
        oid = _TWINS.get(row['id'], row['id'])
        assert seen.setdefault(pair, oid) == oid, f"{row['id']} looks like {seen[pair]}"


def test_every_movement_and_shape_is_drawn_by_the_window_the_splash_and_the_installer():
    looks = occasions_table.DATA['looks'].values()
    motions = {look['motion'] for look in looks} | {'flutter'}  # a country's flag
    shapes = {look['shape'] for look in looks}
    particles = (_REPO / 'frontend/src/components/ui/Particles.vue').read_text(encoding='utf-8')
    season = (_REPO / 'installer/UI/Season.cs').read_text(encoding='utf-8')
    for motion in motions:
        assert motion in occasions._MOTIONS, motion
        assert f'go-{motion}' in particles or motion in ('fall', 'rise', 'twinkle', 'drift', 'burst'), motion
        assert f'"{motion}"' in season, f'installer: {motion}'
    for shape in shapes - {'spark'}:
        assert f'is-{shape}' in particles, shape
    for shape in shapes:
        assert f'"{shape}"' in season, f'installer: {shape}'
