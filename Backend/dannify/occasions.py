"""Special days, all year round, wherever someone is: the New Year, Lunar New
Year, Ramadan and the Eids, Diwali, Holi, Easter, Christmas, a country's own
days, and more.

The calendar is made by packaging/make_occasions.py (occasions_table.py) and
is the very one the window (frontend/src/model/occasions.js) and the
installer (installer/UI/Season.cs) read; this decides the same way they do.
Here it is for the splash, the moment the app opens, and for telling the
window which country the computer is set to.
"""

from __future__ import annotations

import datetime
import html
import os
import random
import re
import subprocess
import sys
from typing import Any, Optional

from .occasions_table import DATA

_CODE = re.compile(r'^[A-Z]{2}$')


# ---------------------------------------------------------------------------
# Where the computer is set to
# ---------------------------------------------------------------------------
def _windows_region() -> str:
    import ctypes  # noqa: PLC0415

    buf = ctypes.create_unicode_buffer(16)
    try:
        if ctypes.windll.kernel32.GetUserDefaultGeoName(buf, 16):
            return buf.value
    except (AttributeError, OSError):
        pass
    return ''


def _mac_region() -> str:
    try:
        out = subprocess.run(['defaults', 'read', '-g', 'AppleLocale'], capture_output=True, text=True,
                             timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return ''
    found = re.search(r'_([A-Za-z]{2})\b', out or '')
    return found.group(1) if found else ''


def _posix_region() -> str:
    for name in ('LC_ALL', 'LC_TIME', 'LC_MESSAGES', 'LANG'):
        found = re.search(r'_([A-Za-z]{2})\b', os.environ.get(name, ''))
        if found:
            return found.group(1)
    return ''


def system_region() -> str:
    """The country the computer is set to ("KE"), or '' when it says none.

    Only a hint: the window weighs it against the time zone, since a region
    left at its default says nothing (see detectRegion in the window).
    """

    try:
        if sys.platform == 'win32':
            found = _windows_region()
        elif sys.platform == 'darwin':
            found = _mac_region()
        else:
            found = _posix_region()
    except Exception:
        found = ''
    found = (found or '').upper()
    return found if _CODE.match(found) else ''


def time_zone() -> str:
    """The computer's time zone by its tz name ("Africa/Nairobi"), or ''."""

    try:
        if sys.platform == 'win32':
            import winreg  # noqa: PLC0415

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r'SYSTEM\CurrentControlSet\Control\TimeZoneInformation') as key:
                name = winreg.QueryValueEx(key, 'TimeZoneKeyName')[0]
            return DATA.get('windows', {}).get(str(name).strip('\x00 '), '')
        if os.environ.get('TZ', '').count('/') >= 1:
            return os.environ['TZ'].lstrip(':')
        link = os.path.realpath('/etc/localtime')
        if 'zoneinfo/' in link:
            return link.split('zoneinfo/', 1)[1]
    except Exception:
        pass
    return ''


def detect_region(zone: str, system: str = '', languages: tuple[str, ...] = ()) -> str:
    """Where someone is: the same reckoning as detectRegion in the window.
    The time zone says where; the region set in the system, or the one in a
    language ("sw-TZ"), says which of the countries sharing that zone."""

    system = (system or '').upper()
    system = system if _CODE.match(system) else ''
    from_languages = []
    for lang in languages:
        parts = re.split(r'[-_]', str(lang or ''))
        if len(parts) > 1 and _CODE.match(parts[1].upper()):
            from_languages.append(parts[1].upper())
    sharing = DATA.get('zones', {}).get(zone or '') or []
    if sharing:
        if system in sharing:
            return system
        return next((r for r in from_languages if r in sharing), sharing[0])
    return system or (from_languages[0] if from_languages else '')


def guess_region() -> str:
    """The country the computer is in, before the window has said."""

    return detect_region(time_zone(), system_region())


# ---------------------------------------------------------------------------
# Which day it is
# ---------------------------------------------------------------------------
def _start(row: dict[str, Any], year: int) -> Optional[datetime.date]:
    if row.get('md'):
        month, day = (int(x) for x in row['md'].split('-'))
        try:
            return datetime.date(year, month, day)
        except ValueError:
            return None
    iso = (row.get('on') or {}).get(str(year))
    return datetime.date.fromisoformat(iso) if iso else None


def _kept_in(row: dict[str, Any], region: str) -> bool:
    if row.get('where') == '*':
        return region not in (row.get('unless') or [])
    return bool(region) and region in (row.get('where') or [])


def _rows(region: str) -> list[dict[str, Any]]:
    rows = [r for r in DATA['occasions'] if _kept_in(r, region)]
    for n in (DATA['national'].get(region) or []) if region else []:
        rows.append({**n, 'kind': 'national', 'country': region, 'look': 'shamrock' if region == 'IE' else 'flag',
                     'priority': 40, 'days': 1, 'day': 0})
    return rows


def occasions_on(now: Optional[datetime.date] = None, region: str = '') -> list[dict[str, Any]]:
    """The days kept on *now* in *region*, the most particular first."""

    day = now or datetime.date.today()
    found = []
    for row in _rows(region):
        for year in (day.year - 1, day.year):
            start = _start(row, year)
            if start is None:
                continue
            if start <= day < start + datetime.timedelta(days=int(row.get('days') or 1)):
                on = start + datetime.timedelta(days=int(row.get('day') or 0))
                found.append({**row, 'start': start, 'on': on})
    found.sort(key=lambda o: (o['on'] != day, -int(o.get('priority') or 0)))
    return found


def today(now: Optional[datetime.date] = None, region: str = '') -> Optional[dict[str, Any]]:
    """The day to dress for, or None."""

    days = occasions_on(now, region)
    return days[0] if days else None


def look_of(occasion: dict[str, Any]) -> dict[str, Any]:
    if occasion.get('look') == 'flag':
        flag = DATA['flags'].get(occasion.get('country', '')) or ['#1ed760', '#ffd166', '#ffffff']
        return {'shape': 'ribbon', 'motion': 'fall', 'palette': flag}
    return DATA['looks'].get(occasion.get('look', ''), DATA['looks']['confetti'])


# What the splash says before the window has ever told it the words in its
# own language: English. After that, the window's words (see clean_words).
_TITLES = {
    'newyear': 'Happy New Year', 'christmas': 'Merry Christmas', 'orthodox_christmas': 'Merry Christmas',
    'lunar_new_year': 'Happy Lunar New Year', 'valentines': 'Happy Valentine’s Day',
    'womens_day': 'Happy International Women’s Day', 'holi': 'Happy Holi', 'nowruz': 'Happy Nowruz',
    'ramadan': 'Ramadan Mubarak', 'eid_fitr': 'Eid Mubarak', 'eid_adha': 'Eid al-Adha Mubarak',
    'easter': 'Happy Easter', 'orthodox_easter': 'Happy Easter', 'vesak': 'Happy Vesak',
    'world_music_day': 'Happy World Music Day', 'mid_autumn': 'Happy Mid-Autumn Festival',
    'rosh_hashanah': 'Shana Tova', 'diwali': 'Happy Diwali', 'halloween': 'Happy Halloween',
    'day_of_dead': 'Día de Muertos', 'thanksgiving': 'Happy Thanksgiving', 'thanksgiving_ca': 'Happy Thanksgiving',
    'hanukkah': 'Happy Hanukkah', 'mothers_day': 'Happy Mother’s Day', 'fathers_day': 'Happy Father’s Day',
}


_STARTING = 'starting your music…'
_WORD_MAX = 80


def clean_words(words: Any) -> dict[str, Any]:
    """The splash's words in the window's language, as the window sent them.

    Kept to short plain texts under the names the splash knows, so a page
    that sent anything else changes nothing.
    """

    if not isinstance(words, dict):
        return {}

    def text(value: Any) -> str:
        return ' '.join(value.split())[:_WORD_MAX] if isinstance(value, str) else ''

    out: dict[str, Any] = {}
    lang = str(words.get('lang') or '').strip().lower()
    if 2 <= len(lang) <= 3 and lang.isascii() and lang.isalpha():
        out['lang'] = lang
    for key in ('starting', 'national'):
        if value := text(words.get(key)):
            out[key] = value
    titles = words.get('titles')
    if isinstance(titles, dict):
        kept = {k: v for k, v in ((k, text(v)) for k, v in titles.items()) if k in _TITLES and v}
        if kept:
            out['titles'] = kept
    return out


def title_of(occasion: dict[str, Any], lang: str = 'en', words: Optional[dict[str, Any]] = None) -> str:
    words = words or {}
    if occasion.get('kind') == 'national':
        names = occasion.get('names') or {}
        name = names.get(lang) or names.get('en') or ''
        return (words.get('national') or 'Happy {name}').replace('{name}', name).strip()
    oid = occasion.get('id', '')
    title = (words.get('titles') or {}).get(oid) or _TITLES.get(oid, '')
    on = occasion.get('on')
    return title.replace('{year}', str(on.year) if isinstance(on, datetime.date) else '').strip()


def starting_words(words: Optional[dict[str, Any]] = None) -> str:
    """"Starting your music…" in the window's language, ready for the page."""

    return html.escape((words or {}).get('starting') or _STARTING.capitalize())


# ---------------------------------------------------------------------------
# The splash
# ---------------------------------------------------------------------------
# A piece of each shape, drawn with CSS and a character or two: the splash is
# up for a second or two, before anything else is loaded.
_GLYPHS = {'heart': '♥', 'star': '✦', 'note': '♪', 'clover': '☘'}


def _piece(shape: str, colour: str, rng: random.Random) -> tuple[str, str]:
    """(style, text) for one piece."""

    if shape == 'dot':
        size = rng.uniform(3, 7)
        return f'width:{size:.1f}px;height:{size:.1f}px;border-radius:50%;background:{colour};', ''
    if shape == 'ribbon':
        return f'width:6px;height:10px;border-radius:1px;background:{colour};', ''
    if shape in ('leaf', 'petal'):
        size = rng.uniform(9, 15)
        radius = '0 100% 0 100%' if shape == 'leaf' else '50% 50% 50% 0'
        return f'width:{size:.0f}px;height:{size:.0f}px;border-radius:{radius};background:{colour};', ''
    if shape == 'lantern':
        return (f'width:12px;height:16px;border-radius:5px;background:{colour};'
                f'box-shadow:0 0 12px {colour};'), ''
    if shape in ('flame', 'spark'):
        size = rng.uniform(4, 7)
        return (f'width:{size:.1f}px;height:{size:.1f}px;border-radius:50%;background:{colour};'
                f'box-shadow:0 0 10px {colour};'), ''
    if shape == 'puff':
        size = rng.uniform(70, 140)
        return (f'width:{size:.0f}px;height:{size:.0f}px;border-radius:50%;opacity:.3;'
                f'background:radial-gradient(closest-side,{colour},transparent);'), ''
    size = rng.uniform(11, 18)
    return f'font-size:{size:.0f}px;line-height:1;color:{colour};', _GLYPHS.get(shape, '✦')


_MOTIONS = {
    # name: (keyframes, starts at the top or the bottom, seconds)
    'fall': ('@keyframes go{to{transform:translateY(110vh) rotate(var(--r))}}', 'top:-16px;', (6, 11)),
    'rise': ('@keyframes go{0%{opacity:0}15%{opacity:1}85%{opacity:1}'
             '100%{transform:translateY(-110vh) rotate(var(--r));opacity:0}}', 'bottom:-24px;', (7, 12)),
    'twinkle': ('@keyframes go{0%,100%{transform:scale(.35);opacity:.2}50%{transform:scale(1);opacity:1}}',
                '', (2.2, 4.4)),
    'burst': ('@keyframes go{0%,100%{transform:scale(.2);opacity:0}30%{transform:scale(1.4);opacity:1}'
              '70%{transform:scale(1);opacity:.6}}', '', (1.8, 3.2)),
    'drift': ('@keyframes go{0%{transform:scale(.6);opacity:0}50%{opacity:.3}'
              '100%{transform:scale(1.25) translateY(-30px);opacity:0}}', '', (5, 9)),
}


def splash_extras(now: Optional[datetime.date] = None, seed: Optional[int] = None,
                  region: str = '', lang: str = '', light: bool = False,
                  words: Optional[dict[str, Any]] = None) -> tuple[str, str, str]:
    """(hint, css, markup) for the splash on a special day; three '' on any other.

    Drawn with CSS alone. For anyone who asked the system for less motion it
    is all there, holding still.
    """

    occasion = today(now, region)
    if occasion is None:
        return '', '', ''
    look = look_of(occasion)
    shape, motion, palette = look['shape'], look['motion'], look['palette'] or ['#ffffff']
    if light:
        # White on white is nothing at all.
        palette = ['#96b4d7' if c.lower() in ('#fff', '#ffffff') else c for c in palette]
    keyframes, anchor, (d0, d1) = _MOTIONS.get(motion, _MOTIONS['fall'])
    rng = random.Random(seed)
    pieces = []
    for i in range(26):
        colour = palette[i % len(palette)]
        style, text = _piece(shape, colour, rng)
        left = rng.uniform(0, 100)
        place = anchor or f'top:{rng.uniform(6, 88):.1f}%;'
        spin = rng.uniform(-40, 40) + (rng.uniform(300, 600) if shape in ('ribbon', 'leaf', 'petal') else 0)
        pieces.append(
            f"<i class='f' style='left:{left:.1f}%;{place}{style}--r:{spin:.0f}deg;"
            f"--y:{rng.uniform(4, 90):.1f}%;animation-delay:{-rng.uniform(0, 9):.1f}s;"
            f"animation-duration:{rng.uniform(d0, d1):.1f}s'>{text}</i>"
        )
    css = (
        '.fx{position:fixed;inset:0;pointer-events:none;overflow:hidden}'
        '.f{position:absolute;font-style:normal;opacity:.85;animation:go linear infinite}'
        + keyframes +
        # Less motion: everything where it would be, holding still.
        '@media (prefers-reduced-motion:reduce){.f{animation:none;top:var(--y)!important;bottom:auto!important}}'
    )
    words = clean_words(words)
    lang = lang or words.get('lang') or 'en'
    starting = words.get('starting') or _STARTING
    hint = html.escape(f'{title_of(occasion, lang, words)} · {starting}')
    return hint, css, "<div class='fx' aria-hidden='true'>" + ''.join(pieces) + '</div>'
