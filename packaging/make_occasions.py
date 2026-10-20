"""The calendar of special days, made once and kept in the repository.

    Backend/.venv/Scripts/python packaging/make_occasions.py

Needs ``holidays``, ``tzdata`` and ``tzlocal`` (pip install holidays==0.107 tzdata tzlocal), here
only: what it writes is plain data, so Dannify itself carries neither, works
offline and asks no one where it is. Run again to move the years on.

One calendar, written three times so each reader has it where it looks:
the window (frontend/src/model/occasions.json, fetched when first needed),
the splash (Backend/dannify/occasions_table.py) and the installer
(installer/UI/Occasions.json). A test checks the three are the same.

What it holds:

- ``occasions``: days kept around the world or in a region (the New Year,
  Lunar New Year, Ramadan and the two Eids, Diwali, Holi, Easter, Hanukkah,
  Christmas, ...), each with the dates it starts on, year by year, how many
  days it lasts, how it looks, and where it is kept.
- ``national``: each country's own celebration days (Kenya's Madaraka,
  Mashujaa and Jamhuri Days, ...), picked by hand so that only days people
  celebrate are greeted, never one of mourning; the exact date each year and
  the name in the country's languages come from ``holidays``.
- ``flags``: each country's colours, for the confetti on its days.
- ``zones``: the countries each time zone is used in, for telling where
  someone is when their computer's region was never set.
- ``windows``: Windows' names for time zones and the zone each stands for,
  for the installer and the splash, which see only Windows' name.
"""

from __future__ import annotations

import datetime as dt
import importlib.resources
import json
import re
import sys
from pathlib import Path

import holidays
from dateutil.easter import EASTER_ORTHODOX, EASTER_WESTERN, easter
from holidays import calendars

ROOT = Path(__file__).resolve().parents[1]
# As far as every calendar it draws on reaches (the Hindu one ends in 2035).
FIRST, LAST = 2026, 2035
YEARS = range(FIRST, LAST + 1)
# The languages Dannify speaks, and how ``holidays`` names them.
APP_LANGS = ('en', 'fr', 'sw', 'es', 'pt', 'de')

# --- Where days are kept ------------------------------------------------------
MUSLIM = [
    'AF', 'AL', 'AZ', 'BH', 'BD', 'BJ', 'BN', 'BF', 'CM', 'TD', 'KM', 'CI', 'DJ', 'EG', 'GA', 'GM', 'GN',
    'GW', 'GY', 'ID', 'IR', 'IQ', 'JO', 'KZ', 'KW', 'KG', 'LB', 'LY', 'MY', 'MV', 'ML', 'MR', 'MA', 'MZ',
    'NE', 'NG', 'OM', 'PK', 'PS', 'QA', 'SA', 'SN', 'SL', 'SO', 'SD', 'SR', 'SY', 'TJ', 'TG', 'TN', 'TR',
    'TM', 'UG', 'AE', 'UZ', 'YE', 'BA', 'XK', 'KE', 'TZ', 'ET', 'ER', 'IN', 'LK', 'SG', 'MU', 'PH', 'ZA',
]
ORTHODOX = ['GR', 'CY', 'RU', 'UA', 'BY', 'RS', 'ME', 'MK', 'BG', 'RO', 'MD', 'GE', 'ET', 'ER']
WESTERN_CHRISTIAN = [
    # Europe
    'AD', 'AT', 'BE', 'CH', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI', 'FR', 'GB', 'HR', 'HU', 'IE', 'IS', 'IT',
    'LI', 'LT', 'LU', 'LV', 'MC', 'MT', 'NL', 'NO', 'PL', 'PT', 'SE', 'SI', 'SK', 'SM', 'VA', 'AL',
    # The Americas
    'AG', 'AR', 'BB', 'BO', 'BR', 'BS', 'BZ', 'CA', 'CL', 'CO', 'CR', 'CU', 'DM', 'DO', 'EC', 'GD', 'GT',
    'GY', 'HN', 'HT', 'JM', 'KN', 'LC', 'MX', 'NI', 'PA', 'PE', 'PR', 'PY', 'SR', 'SV', 'TT', 'US', 'UY',
    'VC', 'VE',
    # Africa
    'AO', 'BI', 'BJ', 'BW', 'CD', 'CF', 'CG', 'CI', 'CM', 'CV', 'GA', 'GH', 'GQ', 'KE', 'LR', 'LS', 'MG',
    'MW', 'MZ', 'NA', 'NG', 'RW', 'SC', 'SL', 'SS', 'ST', 'SZ', 'TG', 'TZ', 'UG', 'ZA', 'ZM', 'ZW',
    # Asia and the Pacific
    'PH', 'TL', 'AU', 'NZ', 'PG', 'FJ', 'SB', 'VU', 'WS', 'TO', 'KI', 'KR', 'SG',
]
CHINESE = ['CN', 'TW', 'HK', 'MO', 'SG', 'MY', 'VN', 'KR', 'ID', 'PH', 'BN', 'TH']
SOUTH_ASIAN_HINDU = ['IN', 'NP', 'LK', 'MY', 'SG', 'MU', 'FJ', 'GY', 'SR', 'TT']
BUDDHIST = ['LK', 'TH', 'MM', 'KH', 'LA', 'NP', 'BT', 'SG', 'MY', 'ID', 'VN']
PERSIAN_NEW_YEAR = ['IR', 'AF', 'AZ', 'TJ', 'UZ', 'KZ', 'KG', 'TM']
# Not greeted where the day is not marked, or is frowned on.
NO_CHRISTMAS = ['AF', 'IR', 'SA', 'SO', 'MV', 'YE', 'KP', 'MR', 'BN']
NO_VALENTINES = ['AF', 'IR', 'PK', 'SA']

# --- How days look ------------------------------------------------------------
# shape: what each piece is; motion: fall, rise, twinkle, burst or drift.
LOOKS = {
    # Each day its own shape and movement (frontend Particles.vue lists the
    # movements). Two dates of one holiday (Orthodox Christmas, Canadian
    # Thanksgiving) share their twin's.
    'snow': {'shape': 'dot', 'motion': 'sway', 'palette': ['#ffffff']},
    'fireworks': {'shape': 'spark', 'motion': 'burst', 'palette': ['#ffd166', '#ef476f', '#3fa9f5', '#1ed760', '#c77dff']},
    'confetti': {'shape': 'ribbon', 'motion': 'fall', 'palette': ['#1ed760', '#ffd166', '#ef476f', '#3fa9f5', '#c77dff']},
    'hearts': {'shape': 'heart', 'motion': 'rise', 'palette': ['#ff4d6d', '#ff8fa3', '#c9184a', '#ffb3c1']},
    'lanterns': {'shape': 'lantern', 'motion': 'swing', 'palette': ['#e63946', '#d62828', '#ffb703']},
    'moonlanterns': {'shape': 'lantern', 'motion': 'rise', 'palette': ['#f4a261', '#ffd166', '#e76f51']},
    'lotus': {'shape': 'lotus', 'motion': 'bob', 'palette': ['#ffc8dd', '#ffffff', '#ffd166', '#ffafcc']},
    'crescent': {'shape': 'crescent', 'motion': 'twinkle', 'palette': ['#ffd166', '#fff3b0', '#e9c46a']},
    'goldstars': {'shape': 'star', 'motion': 'shimmer', 'palette': ['#ffd166', '#2a9d8f', '#fff3b0', '#e9c46a']},
    'fanous': {'shape': 'lantern', 'motion': 'bob', 'palette': ['#e9c46a', '#2a9d8f', '#f4a261']},
    'lights': {'shape': 'flame', 'motion': 'flicker', 'palette': ['#ffb703', '#fb8500', '#ffd166']},
    'bluelights': {'shape': 'flame', 'motion': 'rise', 'palette': ['#4cc9f0', '#ffffff', '#4361ee']},
    'honey': {'shape': 'drop', 'motion': 'fall', 'palette': ['#f4a261', '#e9c46a', '#d4a017', '#c1121f']},
    'colour': {'shape': 'puff', 'motion': 'drift', 'palette': ['#ff006e', '#fb5607', '#ffbe0b', '#3a86ff', '#8338ec', '#06d6a0']},
    'notes': {'shape': 'note', 'motion': 'spiral', 'palette': ['#1ed760', '#3fa9f5', '#c77dff', '#ffd166']},
    'eggs': {'shape': 'egg', 'motion': 'sway', 'palette': ['#ffafcc', '#bde0fe', '#fff3b0', '#cdb4db', '#b9fbc0']},
    'redeggs': {'shape': 'egg', 'motion': 'bob', 'palette': ['#c1121f', '#e63946', '#ffd166']},
    'flowers': {'shape': 'flower', 'motion': 'sway', 'palette': ['#ff8fab', '#ffc2d1', '#fb6f92', '#ffe5ec']},
    'violet': {'shape': 'petal', 'motion': 'spiral', 'palette': ['#7b2cbf', '#c77dff', '#e0aaff', '#ffffff']},
    'spring': {'shape': 'leaf', 'motion': 'flutter', 'palette': ['#80ed99', '#38b000', '#ffafcc', '#fff3b0']},
    'marigold': {'shape': 'petal', 'motion': 'flutter', 'palette': ['#ff9f1c', '#ffbf69', '#f77f00', '#d62828']},
    'leaves': {'shape': 'leaf', 'motion': 'sway', 'palette': ['#e76f51', '#f4a261', '#e9c46a', '#bc6c25']},
    'bats': {'shape': 'bat', 'motion': 'flit', 'palette': ['#9d4edd', '#ff7b00', '#5a189a', '#ff9e00']},
    'stars': {'shape': 'star', 'motion': 'rise', 'palette': ['#3a86ff', '#ffd166', '#8ecae6', '#023e8a']},
    'shamrock': {'shape': 'clover', 'motion': 'sway', 'palette': ['#2d6a4f', '#40916c', '#52b788', '#95d5b2']},
}
# Above the others when two fall together: a country's own day first, then a
# family's, then one kept in a region, then one kept everywhere.
PRIORITY = {'national': 40, 'family': 30, 'regional': 20, 'global': 10}


def md(d: dt.date) -> str:
    return d.strftime('%m-%d')


def nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """The *n*th *weekday* (0 Monday) of a month; n = -1 for the last."""

    if n > 0:
        first = dt.date(year, month, 1)
        return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


SUN, MON, THU = 6, 0, 3
_CHINESE = calendars._ChineseLunisolar()
_ISLAMIC = calendars._IslamicLunar()
_HINDU = calendars._HinduLunisolar()
_HEBREW = calendars._HebrewLunisolar()
_BUDDHIST = calendars._BuddhistLunisolar()


def _dates(found) -> list[dt.date]:
    """Every date a calendar gives, whichever way it gives them: one date, a
    set of them, (date, estimated) pairs, or a generator of those."""

    if found is None:
        return []
    if isinstance(found, dt.date):
        return [found]
    if isinstance(found, tuple) and len(found) == 2 and isinstance(found[1], bool):
        return _dates(found[0])
    out = []
    for item in found:
        out.extend(_dates(item))
    return sorted(out)


def _in(year: int, *found) -> dt.date | None:
    """The first of a calendar's dates that falls in *year*."""

    dates = [d for f in found for d in _dates(f) if d.year == year]
    return min(dates) if dates else None


_NOT_THE_DAY = re.compile(r"observed|\beve\b|in lieu|day after|following|second day|third day|fourth day", re.I)


def named_day(cc: str, year: int, pattern: str, near: dt.date | None = None) -> dt.date | None:
    """The day a country's calendar names so, that year: the one nearest
    *near* when there are several (the Fourth of July, not Juneteenth, for
    "Independence Day"), never the eve, the day after or a day in lieu."""

    rx = re.compile(pattern, re.I)
    try:
        days = holidays.country_holidays(cc, years=year, language='en_US')
    except Exception:
        days = holidays.country_holidays(cc, years=year)
    hits = sorted(d for d, name in days.items() if rx.search(name) and not _NOT_THE_DAY.search(name))
    if not hits:
        return None
    if near is None:
        return hits[0]
    return min(hits, key=lambda d: (abs((d - near).days), d))


def nowruz(year: int) -> dt.date:
    return named_day('IR', year, r'nowruz|norouz|new year') or dt.date(year, 3, 21)


# --- The days kept around the world and in regions ---------------------------
# (id, kind, look, where, except, before, days, rule)
OCCASIONS = [
    # The day is 1 January; it starts on New Year's Eve.
    ('newyear', 'global', 'fireworks', '*', [], 1, 3, lambda y: dt.date(y, 1, 1)),
    ('orthodox_christmas', 'regional', 'snow', ORTHODOX + ['EG'], [], 1, 2, lambda y: dt.date(y, 1, 7)),
    ('lunar_new_year', 'regional', 'lanterns', CHINESE, [], 1, 4, lambda y: _in(y, _CHINESE.lunar_new_year_date(y))),
    ('valentines', 'global', 'hearts', '*', NO_VALENTINES, 1, 2, lambda y: dt.date(y, 2, 14)),
    ('womens_day', 'global', 'violet', '*', [], 0, 1, lambda y: dt.date(y, 3, 8)),
    ('holi', 'regional', 'colour', SOUTH_ASIAN_HINDU, ['LK', 'MY', 'SG'], 1, 2, lambda y: _in(y, _HINDU.holi_date(y))),
    ('nowruz', 'regional', 'spring', PERSIAN_NEW_YEAR, [], 0, 3, nowruz),
    ('ramadan', 'regional', 'crescent', MUSLIM, [], 0, 3, lambda y: _in(y, _ISLAMIC.ramadan_beginning_dates(y))),
    ('eid_fitr', 'regional', 'goldstars', MUSLIM, [], 0, 3, lambda y: _in(y, _ISLAMIC.eid_al_fitr_dates(y))),
    ('easter', 'regional', 'eggs', WESTERN_CHRISTIAN, [], 1, 3, lambda y: easter(y, EASTER_WESTERN)),
    ('orthodox_easter', 'regional', 'redeggs', ORTHODOX, [], 1, 3, lambda y: easter(y, EASTER_ORTHODOX)),
    ('vesak', 'regional', 'lotus', BUDDHIST, [], 0, 1, lambda y: _in(y, _BUDDHIST.vesak_may_date(y))),
    ('world_music_day', 'global', 'notes', '*', [], 0, 1, lambda y: dt.date(y, 6, 21)),
    ('eid_adha', 'regional', 'fanous', MUSLIM, [], 0, 3, lambda y: _in(y, _ISLAMIC.eid_al_adha_dates(y))),
    ('mid_autumn', 'regional', 'moonlanterns', ['CN', 'TW', 'HK', 'MO', 'SG', 'MY', 'VN'], [], 0, 2,
     lambda y: _in(y, _CHINESE.mid_autumn_date(y))),
    ('rosh_hashanah', 'regional', 'honey', ['IL'], [], 0, 2, lambda y: _in(y, _HEBREW.rosh_hashanah_date(y))),
    ('diwali', 'regional', 'lights', SOUTH_ASIAN_HINDU, [], 1, 3, lambda y: _in(y, _HINDU.diwali_india_date(y))),
    ('halloween', 'regional', 'bats', ['US', 'CA', 'GB', 'IE', 'AU', 'NZ', 'NL', 'DE', 'JP'], [], 1, 2,
     lambda y: dt.date(y, 10, 31)),
    ('day_of_dead', 'regional', 'marigold', ['MX', 'GT'], [], 0, 2, lambda y: dt.date(y, 11, 1)),
    ('thanksgiving', 'regional', 'leaves', ['US'], [], 0, 1, lambda y: nth_weekday(y, 11, THU, 4)),
    ('thanksgiving_ca', 'regional', 'leaves', ['CA'], [], 0, 1, lambda y: nth_weekday(y, 10, MON, 2)),
    ('hanukkah', 'regional', 'bluelights', ['IL', 'US', 'CA', 'GB', 'FR', 'AR', 'AU'], [], 0, 8,
     lambda y: _in(y, _HEBREW.hanukkah_date(y), _HEBREW.hanukkah_date(y + 1))),
    ('christmas', 'global', 'snow', '*', NO_CHRISTMAS, 7, 9, lambda y: dt.date(y, 12, 25)),
]

# Days whose date differs from country to country (the moon is sighted, or
# the full moon is chosen, differently): each country's own calendar is
# asked, where ``holidays`` has one. 'later' keeps the calendar's day unless
# the country's is after it (a holiday that starts the day before Eid is
# not Eid yet); 'country' takes the country's day as it is.
BY_COUNTRY = {
    'lunar_new_year': (r'lunar new year$|chinese new year|spring festival|\btet\b|seollal', 'country'),
    'holi': (r'^holi\b', 'country'),
    'eid_fitr': (r'fitr|idd-ul-fitr|hari raya puasa|ramadan feast|ramazan bayram', 'later'),
    'eid_adha': (r'adha|idd-ul-azha|hari raya haji|feast of sacrifice|kurban bayram|tabaski', 'later'),
    'vesak': (r'vesak|visakha|buddha', 'country'),
    'diwali': (r'diwali|deepavali|tihar', 'country'),
}


# --- Mother's Day and Father's Day, where they fall ---------------------------
SECOND_SUNDAY_MAY = [
    'US', 'CA', 'AU', 'NZ', 'KE', 'UG', 'ZA', 'ZW', 'ZM', 'GH', 'IN', 'PK', 'JP', 'CN', 'TW', 'HK', 'SG', 'MY',
    'PH', 'DE', 'AT', 'CH', 'IT', 'NL', 'BE', 'DK', 'FI', 'TR', 'BR', 'CL', 'CO', 'PE', 'VE', 'EC', 'CU', 'GR',
    'HR', 'IS', 'EE', 'LV', 'JM', 'TT', 'BB', 'BS', 'SK', 'CZ', 'UA', 'BD', 'LK', 'NP',
]
MOTHERS = [
    (SECOND_SUNDAY_MAY, lambda y: nth_weekday(y, 5, SUN, 2)),
    (['GB', 'IE', 'NG'], lambda y: easter(y, EASTER_WESTERN) - dt.timedelta(days=21)),
    (['MX', 'SV', 'GT'], lambda y: dt.date(y, 5, 10)),
    (['ES', 'PT', 'LT', 'HU', 'RO'], lambda y: nth_weekday(y, 5, SUN, 1)),
    (['SE'], lambda y: nth_weekday(y, 5, SUN, -1)),
    (['FR'], lambda y: (lambda last, pentecost: last if last != pentecost else last + dt.timedelta(days=7))(
        nth_weekday(y, 5, SUN, -1), easter(y, EASTER_WESTERN) + dt.timedelta(days=49))),
    (['EG', 'LB', 'JO', 'IQ', 'SA', 'AE', 'KW', 'QA', 'BH', 'OM', 'SD'], lambda y: dt.date(y, 3, 21)),
    (['AR'], lambda y: nth_weekday(y, 10, SUN, 3)),
    (['ID'], lambda y: dt.date(y, 12, 22)),
    (['TH'], lambda y: dt.date(y, 8, 12)),
    (['KR'], lambda y: dt.date(y, 5, 8)),
]
FATHERS = [
    (['US', 'CA', 'GB', 'IE', 'IN', 'PK', 'JP', 'SG', 'MY', 'PH', 'HK', 'KE', 'UG', 'ZA', 'ZW', 'NG', 'GH', 'FR',
      'NL', 'TR', 'MX', 'AR', 'CL', 'CO', 'PE', 'VE', 'EC', 'GR', 'JM', 'TT', 'CN', 'BD', 'LK', 'ZM'],
     lambda y: nth_weekday(y, 6, SUN, 3)),
    (['IT', 'ES', 'PT', 'HR', 'BO'], lambda y: dt.date(y, 3, 19)),
    (['DE'], lambda y: easter(y, EASTER_WESTERN) + dt.timedelta(days=39)),
    (['AU', 'NZ', 'FJ', 'PG'], lambda y: nth_weekday(y, 9, SUN, 1)),
    (['BR'], lambda y: nth_weekday(y, 8, SUN, 2)),
    (['TW'], lambda y: dt.date(y, 8, 8)),
    (['TH'], lambda y: dt.date(y, 12, 5)),
    (['SE', 'FI', 'NO', 'EE', 'IS'], lambda y: nth_weekday(y, 11, SUN, 2)),
    (['BE', 'AT'], lambda y: nth_weekday(y, 6, SUN, 2)),
    (['EG', 'LB', 'JO', 'AE'], lambda y: dt.date(y, 6, 21)),
    (['KR'], lambda y: dt.date(y, 5, 8)),
]

# --- Each country's own days ---------------------------------------------------
# (month-day it usually falls on, what its name in ``holidays`` looks like,
# the name to use when ``holidays`` does not know the country). Only days of
# celebration: independence, the nation's day, a festival everyone keeps.
NATIONAL = {
    'AL': [('11-28', r'independence', 'Independence Day')],
    'DZ': [('07-05', r'independence', 'Independence Day')],
    'AD': [('09-08', r'meritxell|national', 'National Day')],
    'AO': [('11-11', r'independence', 'Independence Day')],
    'AG': [('11-01', r'independence', 'Independence Day')],
    'AR': [('07-09', r'independence', 'Independence Day'), ('05-25', r'may revolution', 'May Revolution Day')],
    'AM': [('09-21', r'independence', 'Independence Day')],
    'AT': [('10-26', r'national', 'National Day')],
    'AZ': [('05-28', r'independence', 'Independence Day')],
    'BS': [('07-10', r'independence', 'Independence Day')],
    'BH': [('12-16', r'national', 'National Day')],
    'BD': [('03-26', r'independence', 'Independence Day'), ('12-16', r'victory', 'Victory Day')],
    'BB': [('11-30', r'independence', 'Independence Day')],
    'BY': [('07-03', r'independence', 'Independence Day')],
    'BE': [('07-21', r'national', 'National Day')],
    'BZ': [('09-21', r'independence', 'Independence Day')],
    'BJ': [('08-01', r'independence', 'Independence Day')],
    'BT': [('12-17', r'national', 'National Day')],
    'BO': [('08-06', r'independence', 'Independence Day')],
    'BA': [('03-01', r'independence', 'Independence Day')],
    'BW': [('09-30', r'botswana', 'Botswana Day')],
    'BR': [('09-07', r'independence', 'Independence Day')],
    'BN': [('02-23', r'national', 'National Day')],
    'BG': [('03-03', r'liberation', 'Liberation Day')],
    'BF': [('12-11', r'independence|proclamation', 'Independence Day')],
    'BI': [('07-01', r'independence', 'Independence Day')],
    'CV': [('07-05', r'independence', 'Independence Day')],
    'KH': [('11-09', r'independence', 'Independence Day')],
    'CM': [('05-20', r'national', 'National Day')],
    'CA': [('07-01', r'canada', 'Canada Day')],
    'CF': [('12-01', r'republic', 'Republic Day')],
    'TD': [('08-11', r'independence', 'Independence Day')],
    'CL': [('09-18', r'independence|national', 'Independence Day')],
    'CN': [('10-01', r'national', 'National Day')],
    'CO': [('07-20', r'independence', 'Independence Day')],
    'KM': [('07-06', r'independence', 'Independence Day')],
    'CG': [('08-15', r'independence', 'Independence Day')],
    'CD': [('06-30', r'independence', 'Independence Day')],
    'CR': [('09-15', r'independence', 'Independence Day')],
    'CI': [('08-07', r'independence|national', 'Independence Day')],
    'HR': [('05-30', r'statehood', 'Statehood Day')],
    'CY': [('10-01', r'independence', 'Independence Day')],
    'CZ': [('10-28', r'independent|czechoslovak', 'Independence Day')],
    'DK': [('06-05', r'constitution', 'Constitution Day')],
    'DJ': [('06-27', r'independence', 'Independence Day')],
    'DM': [('11-03', r'independence', 'Independence Day')],
    'DO': [('02-27', r'independence', 'Independence Day')],
    'EC': [('08-10', r'independence|first cry', 'Independence Day')],
    'EG': [('07-23', r'revolution', 'Revolution Day')],
    'SV': [('09-15', r'independence', 'Independence Day')],
    'GQ': [('10-12', r'independence', 'Independence Day')],
    'ER': [('05-24', r'independence', 'Independence Day')],
    'EE': [('02-24', r'independence', 'Independence Day')],
    'SZ': [('09-06', r'independence', 'Independence Day')],
    'ET': [('03-02', r'adwa', 'Adwa Victory Day')],
    'FJ': [('10-10', r'fiji', 'Fiji Day')],
    'FI': [('12-06', r'independence', 'Independence Day')],
    'FR': [('07-14', r'national|bastille', 'Bastille Day')],
    'GA': [('08-17', r'independence', 'Independence Day')],
    'GM': [('02-18', r'independence', 'Independence Day')],
    'GE': [('05-26', r'independence', 'Independence Day')],
    'DE': [('10-03', r'unity', 'German Unity Day')],
    'GH': [('03-06', r'independence', 'Independence Day')],
    'GR': [('03-25', r'independence', 'Independence Day')],
    'GD': [('02-07', r'independence', 'Independence Day')],
    'GT': [('09-15', r'independence', 'Independence Day')],
    'GN': [('10-02', r'independence', 'Independence Day')],
    'GW': [('09-24', r'independence', 'Independence Day')],
    'GY': [('05-26', r'independence', 'Independence Day'), ('02-23', r'republic|mashramani', 'Republic Day')],
    'HN': [('09-15', r'independence', 'Independence Day')],
    'HU': [('08-20', r'stephen|state foundation|national', 'State Foundation Day')],
    'IS': [('06-17', r'national', 'National Day')],
    'IN': [('08-15', r'independence', 'Independence Day'), ('01-26', r'republic', 'Republic Day')],
    'ID': [('08-17', r'independence', 'Independence Day')],
    'IQ': [('10-03', r'national', 'National Day')],
    'IE': [('03-17', r'patrick', "Saint Patrick's Day")],
    'IL': [('05-01', r'independence', 'Independence Day')],
    'IT': [('06-02', r'republic', 'Republic Day')],
    'JM': [('08-06', r'independence', 'Independence Day')],
    'JP': [('02-11', r'foundation', 'National Foundation Day')],
    'JO': [('05-25', r'independence', 'Independence Day')],
    'KZ': [('10-25', r'republic', 'Republic Day')],
    'KE': [('06-01', r'madaraka', 'Madaraka Day'), ('10-20', r'mashujaa', 'Mashujaa Day'),
           ('12-12', r'jamhuri', 'Jamhuri Day')],
    'KI': [('07-12', r'independence', 'Independence Day')],
    'KR': [('08-15', r'liberation', 'Liberation Day')],
    'KW': [('02-25', r'national', 'National Day')],
    'KG': [('08-31', r'independence', 'Independence Day')],
    'LA': [('12-02', r'national', 'National Day')],
    'LV': [('11-18', r'proclamation|independence', 'Proclamation Day')],
    'LB': [('11-22', r'independence', 'Independence Day')],
    'LS': [('10-04', r'independence', 'Independence Day')],
    'LR': [('07-26', r'independence', 'Independence Day')],
    'LY': [('12-24', r'independence', 'Independence Day')],
    'LI': [('08-15', r'national', 'National Day')],
    'LT': [('02-16', r'restoration of the state|statehood|independence', 'Restoration of the State Day')],
    'LU': [('06-23', r'national', 'National Day')],
    'MG': [('06-26', r'independence', 'Independence Day')],
    'MW': [('07-06', r'independence', 'Independence Day')],
    'MY': [('08-31', r'national', 'National Day'), ('09-16', r'malaysia day', 'Malaysia Day')],
    'MV': [('07-26', r'independence', 'Independence Day')],
    'ML': [('09-22', r'independence', 'Independence Day')],
    'MT': [('09-21', r'independence', 'Independence Day')],
    'MR': [('11-28', r'independence', 'Independence Day')],
    'MU': [('03-12', r'independence|republic', 'Independence Day')],
    'MX': [('09-16', r'independence', 'Independence Day')],
    'MD': [('08-27', r'independence', 'Independence Day')],
    'MC': [('11-19', r'national|prince', 'National Day')],
    'MN': [('07-11', r'naadam|national', 'Naadam')],
    'ME': [('07-13', r'statehood', 'Statehood Day')],
    'MA': [('11-18', r'independence', 'Independence Day')],
    'MZ': [('06-25', r'independence', 'Independence Day')],
    'MM': [('01-04', r'independence', 'Independence Day')],
    'NA': [('03-21', r'independence', 'Independence Day')],
    'NL': [('04-27', r"king'?s day", "King's Day")],
    'NZ': [('02-06', r'waitangi', 'Waitangi Day')],
    'NI': [('09-15', r'independence', 'Independence Day')],
    'NE': [('08-03', r'independence', 'Independence Day')],
    'NG': [('10-01', r'national|independence', 'Independence Day')],
    'MK': [('09-08', r'independence', 'Independence Day')],
    'NO': [('05-17', r'constitution', 'Constitution Day')],
    'OM': [('11-20', r'national', 'National Day')],
    'PK': [('08-14', r'independence', 'Independence Day')],
    'PA': [('11-03', r'separation|independence', 'Independence Day')],
    'PG': [('09-16', r'independence', 'Independence Day')],
    'PY': [('05-15', r'independence', 'Independence Day')],
    'PE': [('07-28', r'independence', 'Independence Day')],
    'PH': [('06-12', r'independence', 'Independence Day')],
    'PL': [('11-11', r'independence', 'Independence Day')],
    'PT': [('06-10', r'portugal', 'Portugal Day')],
    'QA': [('12-18', r'national', 'National Day')],
    'RO': [('12-01', r'national|union', 'Great Union Day')],
    'RU': [('06-12', r'russia', 'Russia Day')],
    'RW': [('07-01', r'independence', 'Independence Day')],
    'KN': [('09-19', r'independence', 'Independence Day')],
    'LC': [('02-22', r'independence', 'Independence Day')],
    'VC': [('10-27', r'independence', 'Independence Day')],
    'WS': [('06-01', r'independence', 'Independence Day')],
    'SM': [('09-03', r'foundation', 'Foundation Day')],
    'ST': [('07-12', r'independence', 'Independence Day')],
    'SA': [('09-23', r'national', 'National Day')],
    'SN': [('04-04', r'independence', 'Independence Day')],
    'RS': [('02-15', r'statehood', 'Statehood Day')],
    'SC': [('06-29', r'independence', 'Independence Day')],
    'SL': [('04-27', r'independence', 'Independence Day')],
    'SG': [('08-09', r'national', 'National Day')],
    'SI': [('06-25', r'statehood', 'Statehood Day')],
    'SB': [('07-07', r'independence', 'Independence Day')],
    'SO': [('07-01', r'independence', 'Independence Day')],
    'ZA': [('04-27', r'freedom', 'Freedom Day')],
    'SS': [('07-09', r'independence', 'Independence Day')],
    'ES': [('10-12', r'national', 'National Day')],
    'LK': [('02-04', r'independence|national', 'Independence Day')],
    'SR': [('11-25', r'independence', 'Independence Day')],
    'SE': [('06-06', r'national', 'National Day')],
    'CH': [('08-01', r'national', 'Swiss National Day')],
    'TW': [('10-10', r'national', 'National Day')],
    'TJ': [('09-09', r'independence', 'Independence Day')],
    'TZ': [('12-09', r'independence|uhuru', 'Independence Day')],
    'TH': [('12-05', r'national|father', 'National Day')],
    'TG': [('04-27', r'independence', 'Independence Day')],
    'TT': [('08-31', r'independence', 'Independence Day')],
    'TN': [('03-20', r'independence', 'Independence Day')],
    'TR': [('10-29', r'republic', 'Republic Day')],
    'TM': [('09-27', r'independence', 'Independence Day')],
    'UG': [('10-09', r'independence', 'Independence Day')],
    'UA': [('08-24', r'independence', 'Independence Day')],
    'AE': [('12-02', r'national', 'National Day')],
    'US': [('07-04', r'independence', 'Independence Day')],
    'UY': [('08-25', r'independence', 'Independence Day')],
    'UZ': [('09-01', r'independence', 'Independence Day')],
    'VU': [('07-30', r'independence', 'Independence Day')],
    'VE': [('07-05', r'independence', 'Independence Day')],
    'VN': [('09-02', r'national', 'National Day')],
    'YE': [('05-22', r'unity|national', 'Unity Day')],
    'ZM': [('10-24', r'independence', 'Independence Day')],
    'ZW': [('04-18', r'independence', 'Independence Day')],
}

FLAGS = {
    'AL': ['#E41E20', '#000000'], 'DZ': ['#006233', '#FFFFFF', '#D21034'], 'AD': ['#10069F', '#FEDF00', '#D50032'],
    'AO': ['#CC092F', '#000000', '#FFCB00'], 'AG': ['#CE1126', '#000000', '#0072C6', '#FCD116', '#FFFFFF'],
    'AR': ['#74ACDF', '#FFFFFF', '#F6B40E'], 'AM': ['#D90012', '#0033A0', '#F2A800'], 'AT': ['#ED2939', '#FFFFFF'],
    'AZ': ['#0092BC', '#E4002B', '#00AF66'], 'BS': ['#00ABC9', '#FAE042', '#000000'], 'BH': ['#CE1126', '#FFFFFF'],
    'BD': ['#006A4E', '#F42A41'], 'BB': ['#00267F', '#FFC726', '#000000'], 'BY': ['#C8313E', '#4AA657', '#FFFFFF'],
    'BE': ['#000000', '#FDDA24', '#EF3340'], 'BZ': ['#003F87', '#CE1126', '#FFFFFF'],
    'BJ': ['#008751', '#FCD116', '#E8112D'], 'BT': ['#FFD520', '#FF4E12', '#FFFFFF'],
    'BO': ['#D52B1E', '#F9E300', '#007934'], 'BA': ['#002395', '#FECB00', '#FFFFFF'],
    'BW': ['#75AADB', '#FFFFFF', '#000000'], 'BR': ['#009C3B', '#FFDF00', '#002776', '#FFFFFF'],
    'BN': ['#F7E017', '#FFFFFF', '#000000', '#CF1126'], 'BG': ['#FFFFFF', '#00966E', '#D62612'],
    'BF': ['#EF2B2D', '#009E49', '#FCD116'], 'BI': ['#CE1126', '#1EB53A', '#FFFFFF'],
    'CV': ['#003893', '#FFFFFF', '#CF2027', '#F7D116'], 'KH': ['#032EA1', '#E00025', '#FFFFFF'],
    'CM': ['#007A5E', '#CE1126', '#FCD116'], 'CA': ['#FF0000', '#FFFFFF'],
    'CF': ['#003082', '#FFFFFF', '#289728', '#FFCE00', '#D21034'], 'TD': ['#002664', '#FECB00', '#C60C30'],
    'CL': ['#0039A6', '#FFFFFF', '#D52B1E'], 'CN': ['#EE1C25', '#FFFF00'], 'CO': ['#FCD116', '#003893', '#CE1126'],
    'KM': ['#FFC61E', '#FFFFFF', '#CE1126', '#3A75C4', '#3D8E33'], 'CG': ['#009543', '#FBDE4A', '#DC241F'],
    'CD': ['#007FFF', '#F7D618', '#CE1021'], 'CR': ['#002B7F', '#FFFFFF', '#CE1126'],
    'CI': ['#F77F00', '#FFFFFF', '#009E60'], 'HR': ['#FF0000', '#FFFFFF', '#171796'],
    'CY': ['#FFFFFF', '#D57800', '#4E5B31'], 'CZ': ['#FFFFFF', '#D7141A', '#11457E'], 'DK': ['#C8102E', '#FFFFFF'],
    'DJ': ['#6AB2E7', '#12AD2B', '#FFFFFF', '#D7141A'], 'DM': ['#006B3F', '#FCD116', '#000000', '#FFFFFF', '#D41C30'],
    'DO': ['#002D62', '#CE1126', '#FFFFFF'], 'EC': ['#FFDD00', '#034EA2', '#ED1C24'],
    'EG': ['#CE1126', '#FFFFFF', '#000000', '#C09300'], 'SV': ['#0F47AF', '#FFFFFF'],
    'GQ': ['#3E9A00', '#FFFFFF', '#E32118', '#0073CE'], 'ER': ['#EA0437', '#4189DD', '#12AD2B', '#FFC726'],
    'EE': ['#0072CE', '#000000', '#FFFFFF'], 'SZ': ['#3E5EB9', '#FFD900', '#B10C0C', '#FFFFFF', '#000000'],
    'ET': ['#078930', '#FCDD09', '#DA121A', '#0F47AF'], 'FJ': ['#68BFE5', '#FFFFFF', '#CE1126', '#002868'],
    'FI': ['#FFFFFF', '#002F6C'], 'FR': ['#002395', '#FFFFFF', '#ED2939'], 'GA': ['#009E60', '#FCD116', '#3A75C4'],
    'GM': ['#CE1126', '#0C1C8C', '#3A7728', '#FFFFFF'], 'GE': ['#FFFFFF', '#FF0000'],
    'DE': ['#000000', '#DD0000', '#FFCE00'], 'GH': ['#CE1126', '#FCD116', '#006B3F', '#000000'],
    'GR': ['#0D5EAF', '#FFFFFF'], 'GD': ['#CE1126', '#007A5E', '#FCD116'], 'GT': ['#4997D0', '#FFFFFF'],
    'GN': ['#CE1126', '#FCD116', '#009460'], 'GW': ['#CE1126', '#FCD116', '#009E49', '#000000'],
    'GY': ['#009E49', '#FCD116', '#CE1126', '#000000', '#FFFFFF'], 'HN': ['#0073CF', '#FFFFFF'],
    'HU': ['#CD2A3E', '#FFFFFF', '#436F4D'], 'IS': ['#02529C', '#FFFFFF', '#DC1E35'],
    'IN': ['#FF9933', '#FFFFFF', '#138808', '#000080'], 'ID': ['#FF0000', '#FFFFFF'],
    'IQ': ['#CE1126', '#FFFFFF', '#000000', '#007A3D'], 'IE': ['#169B62', '#FFFFFF', '#FF883E'],
    'IL': ['#0038B8', '#FFFFFF'], 'IT': ['#009246', '#FFFFFF', '#CE2B37'], 'JM': ['#009B3A', '#FED100', '#000000'],
    'JP': ['#FFFFFF', '#BC002D'], 'JO': ['#000000', '#FFFFFF', '#007A3D', '#CE1126'], 'KZ': ['#00AFCA', '#FEC50C'],
    'KE': ['#000000', '#BB0000', '#006600', '#FFFFFF'], 'KI': ['#CE1126', '#FCD116', '#003F87', '#FFFFFF'],
    'KR': ['#FFFFFF', '#CD2E3A', '#0047A0', '#000000'], 'KW': ['#007A3D', '#FFFFFF', '#CE1126', '#000000'],
    'KG': ['#E8112D', '#FFEF00'], 'LA': ['#CE1126', '#002868', '#FFFFFF'], 'LV': ['#9E3039', '#FFFFFF'],
    'LB': ['#ED1C24', '#FFFFFF', '#00A651'], 'LS': ['#00209F', '#FFFFFF', '#009543', '#000000'],
    'LR': ['#BF0A30', '#FFFFFF', '#002868'], 'LY': ['#E70013', '#000000', '#239E46', '#FFFFFF'],
    'LI': ['#002B7F', '#CE1126', '#FFD83D'], 'LT': ['#FDB913', '#006A44', '#C1272D'],
    'LU': ['#ED2939', '#FFFFFF', '#00A1DE'], 'MG': ['#FFFFFF', '#FC3D32', '#007E3A'],
    'MW': ['#000000', '#CE1126', '#339E35'], 'MY': ['#CC0001', '#FFFFFF', '#010066', '#FFCC00'],
    'MV': ['#D21034', '#007E3A', '#FFFFFF'], 'ML': ['#14B53A', '#FCD116', '#CE1126'], 'MT': ['#FFFFFF', '#CF142B'],
    'MR': ['#006233', '#FFC400', '#D01C1F'], 'MU': ['#EA2839', '#1A206D', '#FFD500', '#00A551'],
    'MX': ['#006847', '#FFFFFF', '#CE1126'], 'MD': ['#0046AE', '#FFD200', '#CC092F'], 'MC': ['#CE1126', '#FFFFFF'],
    'MN': ['#C4272F', '#015197', '#F9CF02'], 'ME': ['#C40308', '#D3AE3B'], 'MA': ['#C1272D', '#006233'],
    'MZ': ['#007168', '#000000', '#FCE100', '#D21034', '#FFFFFF'], 'MM': ['#FECB00', '#34B233', '#EA2839', '#FFFFFF'],
    'NA': ['#003580', '#D21034', '#009543', '#FFCE00', '#FFFFFF'], 'NL': ['#FF6F00', '#AE1C28', '#FFFFFF', '#21468B'],
    'NZ': ['#012169', '#FFFFFF', '#C8102E'], 'NI': ['#0067C6', '#FFFFFF'], 'NE': ['#E05206', '#FFFFFF', '#0DB02B'],
    'NG': ['#008751', '#FFFFFF'], 'MK': ['#D20000', '#FFE600'], 'NO': ['#BA0C2F', '#FFFFFF', '#00205B'],
    'OM': ['#DB161B', '#FFFFFF', '#008000'], 'PK': ['#01411C', '#FFFFFF'], 'PA': ['#DA121A', '#FFFFFF', '#072357'],
    'PG': ['#000000', '#CE1126', '#FCD116', '#FFFFFF'], 'PY': ['#D52B1E', '#FFFFFF', '#0038A8'],
    'PE': ['#D91023', '#FFFFFF'], 'PH': ['#0038A8', '#CE1126', '#FFFFFF', '#FCD116'], 'PL': ['#FFFFFF', '#DC143C'],
    'PT': ['#006600', '#FF0000', '#FFCC00'], 'QA': ['#8A1538', '#FFFFFF'], 'RO': ['#002B7F', '#FCD116', '#CE1126'],
    'RU': ['#FFFFFF', '#0039A6', '#D52B1E'], 'RW': ['#00A1DE', '#FAD201', '#20603D'],
    'KN': ['#009E49', '#FCD116', '#CE1126', '#000000'], 'LC': ['#66CCFF', '#FCD116', '#000000', '#FFFFFF'],
    'VC': ['#002674', '#FCD022', '#009E60'], 'WS': ['#CE1126', '#002B7F', '#FFFFFF'], 'SM': ['#5EB6E4', '#FFFFFF'],
    'ST': ['#12AD2B', '#FFCE00', '#D21034', '#000000'], 'SA': ['#006C35', '#FFFFFF'],
    'SN': ['#00853F', '#FDEF42', '#E31B23'], 'RS': ['#C6363C', '#0C4076', '#FFFFFF'],
    'SC': ['#003F87', '#FCD856', '#D62828', '#FFFFFF', '#007A3D'], 'SL': ['#1EB53A', '#FFFFFF', '#0072C6'],
    'SG': ['#EF3340', '#FFFFFF'], 'SI': ['#FFFFFF', '#005DA4', '#ED1C24'], 'SB': ['#0051BA', '#215B33', '#FCD116'],
    'SO': ['#4189DD', '#FFFFFF'], 'ZA': ['#007A4D', '#FFB612', '#DE3831', '#002395', '#000000', '#FFFFFF'],
    'SS': ['#000000', '#DA121A', '#078930', '#0F47AF', '#FCDD09', '#FFFFFF'], 'ES': ['#AA151B', '#F1BF00'],
    'LK': ['#FFB700', '#8D2029', '#00534E', '#EB7400'], 'SR': ['#377E3F', '#FFFFFF', '#B40A2D', '#ECC81D'],
    'SE': ['#006AA7', '#FECC00'], 'CH': ['#DA291C', '#FFFFFF'], 'TW': ['#FE0000', '#000095', '#FFFFFF'],
    'TJ': ['#CC0000', '#FFFFFF', '#006600', '#F8C300'], 'TZ': ['#1EB53A', '#FCD116', '#000000', '#00A3DD'],
    'TH': ['#A51931', '#F4F5F8', '#2D2A4A'], 'TG': ['#006A4E', '#FFCE00', '#D21034', '#FFFFFF'],
    'TT': ['#CE1126', '#FFFFFF', '#000000'], 'TN': ['#E70013', '#FFFFFF'], 'TR': ['#E30A17', '#FFFFFF'],
    'TM': ['#00843D', '#D22630', '#FFFFFF'], 'UG': ['#000000', '#FCDC04', '#D90000', '#FFFFFF'],
    'UA': ['#0057B7', '#FFD700'], 'AE': ['#00732F', '#FFFFFF', '#000000', '#FF0000'],
    'US': ['#B22234', '#FFFFFF', '#3C3B6E'], 'UY': ['#0038A8', '#FFFFFF', '#FCD116'],
    'UZ': ['#0099B5', '#FFFFFF', '#1EB53A', '#CE1126'], 'VU': ['#D21034', '#009543', '#000000', '#FDCE12'],
    'VE': ['#FFCC00', '#00247D', '#CF142B'], 'VN': ['#DA251D', '#FFFF00'], 'YE': ['#CE1126', '#FFFFFF', '#000000'],
    'ZM': ['#198A00', '#DE2010', '#000000', '#EF7D00'], 'ZW': ['#006400', '#FFD200', '#D40000', '#000000', '#FFFFFF'],
}


def compact(dates: dict[int, dt.date]) -> dict:
    """A date that is the same every year is kept once."""

    days = {md(d) for d in dates.values()}
    if len(days) == 1:
        return {'md': days.pop()}
    return {'on': {str(y): d.isoformat() for y, d in sorted(dates.items())}}


def _country_day(cc: str, year: int, pattern: str, usual: dt.date, prefer: str) -> dt.date:
    found = named_day(cc, year, pattern, near=usual)
    if found is None or abs((found - usual).days) > 40:
        return usual
    return max(found, usual) if prefer == 'later' else found


def occasion_rows() -> list[dict]:
    out = []
    for oid, kind, look, where, unless, before, days, rule in OCCASIONS:
        usual = {}
        for y in YEARS:
            day = rule(y)
            if day is None:
                raise SystemExit(f'{oid}: no date in {y}')
            usual[y] = day
        row = {'id': oid, 'kind': kind, 'look': look, 'priority': PRIORITY[kind],
               **({'unless': unless} if unless else {}), 'days': days, 'day': before}
        if oid not in BY_COUNTRY or where == '*':
            out.append({**row, 'where': where,
                        **compact({y: d - dt.timedelta(days=before) for y, d in usual.items()})})
            continue
        # Countries whose days agree share a row.
        pattern, prefer = BY_COUNTRY[oid]
        groups: dict[tuple, list[str]] = {}
        for cc in where:
            try:
                holidays.country_holidays(cc)
                days_of = tuple(_country_day(cc, y, pattern, usual[y], prefer) for y in YEARS)
            except Exception:
                days_of = tuple(usual[y] for y in YEARS)
            groups.setdefault(days_of, []).append(cc)
        for days_of, ccs in groups.items():
            out.append({**row, 'where': sorted(ccs),
                        **compact({y: d - dt.timedelta(days=before) for y, d in zip(YEARS, days_of)})})
    for oid, rules, look in (('mothers_day', MOTHERS, 'flowers'), ('fathers_day', FATHERS, 'stars')):
        for i, (where, rule) in enumerate(rules):
            out.append({'id': oid, 'kind': 'family', 'look': look, 'priority': PRIORITY['family'],
                        'where': where, 'days': 1, 'day': 0, **compact({y: rule(y) for y in YEARS})})
    return out


def _language(cc: str, lang: str, supported: tuple) -> str | None:
    """How ``holidays`` names one of Dannify's languages for a country."""

    want = [f'{lang}_{cc}', lang] + ([f'{lang}_US', f'{lang}_GB'] if lang == 'en' else []) \
        + ([f'{lang}_BR', f'{lang}_PT'] if lang == 'pt' else []) + ([f'{lang}_ES'] if lang == 'es' else [])
    return next((w for w in want if w in supported), None)


def national_rows() -> dict:
    out: dict[str, list] = {}
    for cc, days in NATIONAL.items():
        try:
            supported = holidays.country_holidays(cc).supported_languages or ()
        except Exception:
            supported = None
        rows = []
        for i, (usual, pattern, fallback) in enumerate(days):
            rx = re.compile(pattern, re.I)
            dates, names = {}, {}
            for y in YEARS:
                found = None
                usual_day = dt.date(y, int(usual[:2]), int(usual[3:]))
                if supported is not None:
                    found = named_day(cc, y, pattern, near=usual_day)
                    # A different day of that name (a second "Independence
                    # Day" in another month) is not the one meant.
                    if found and abs((found - usual_day).days) > 45:
                        found = None
                dates[y] = found or usual_day
            if supported is not None:
                y = FIRST
                # A day that is two holidays at once is named "A; B": the
                # part that is this day, in every language alike.
                which = 0
                for lang in APP_LANGS:
                    code = _language(cc, lang, tuple(supported)) if supported else None
                    if code is None and lang != 'en':
                        continue
                    try:
                        cal = holidays.country_holidays(cc, years=y, language=code) if code else \
                            holidays.country_holidays(cc, years=y)
                    except Exception:
                        continue
                    name = cal.get(dates[y])
                    if not name:
                        continue
                    parts = [p.strip() for p in name.split(';')]
                    if lang == 'en':
                        which = next((i for i, p in enumerate(parts) if rx.search(p)), 0)
                    pick = parts[which] if which < len(parts) else parts[0]
                    names[lang] = re.sub(r'\s*\((estimated|observed)\)', '', pick, flags=re.I).strip()
            if 'en' not in names or not rx.search(names['en']):
                names['en'] = fallback
            rows.append({'id': f'{cc.lower()}-{i}', 'names': names, **compact(dates)})
        out[cc] = rows
    return out


def zone_rows() -> dict:
    base = importlib.resources.files('tzdata') / 'zoneinfo'
    primary = {}
    for line in (base / 'zone.tab').read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#'):
            cc, _, zone = line.split('\t')[:3]
            primary.setdefault(zone, cc)
    zones = {}
    for line in (base / 'zone1970.tab').read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#'):
            ccs, _, zone = line.split('\t')[:3]
            ccs = ccs.split(',')
            first = primary.get(zone, ccs[0])
            zones[zone] = [first] + [c for c in ccs if c != first]
    # Names of zones kept for old times' sake still point somewhere.
    for zone, cc in primary.items():
        zones.setdefault(zone, [cc])
    return zones


def windows_rows() -> dict:
    from tzlocal.windows_tz import win_tz

    return dict(sorted(win_tz.items()))


def build() -> dict:
    return {
        'v': 1,
        'years': [FIRST, LAST],
        'looks': LOOKS,
        'occasions': occasion_rows(),
        'national': national_rows(),
        'flags': FLAGS,
        'zones': zone_rows(),
        'windows': windows_rows(),
    }


def main() -> int:
    data = build()
    text = json.dumps(data, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    targets = {
        ROOT / 'frontend' / 'src' / 'model' / 'occasions.json': text,
        ROOT / 'installer' / 'UI' / 'Occasions.json': text,
        ROOT / 'Backend' / 'dannify' / 'occasions_table.py': (
            '"""The calendar of special days, made by packaging/make_occasions.py: do not\n'
            'edit by hand. See frontend/src/model/occasions.json for the same, readable."""\n\n'
            'import json\n\nDATA = json.loads(' + repr(text) + ')\n'
        ),
    }
    for path, body in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8', newline='\n')
        print(f'wrote {path.relative_to(ROOT)} ({len(body.encode()) // 1024} KB)')
    national = data['national']
    print(f"{len(data['occasions'])} occasion rows, {len(national)} countries with their own days, "
          f"{len(data['zones'])} time zones")
    return 0


if __name__ == '__main__':
    sys.exit(main())
