"""What was played on YouTube Music, brought into Dannify's own history.

Signed in with Google, someone's YouTube Music history (the phone, the web,
a speaker) joins History, Your stats and Your year in music. A copy of
Dannify installed today is not empty: it starts from all that was played
before it, and keeps up from there.

YouTube Music says when a song was played only roughly, under a heading:
"Today", "Yesterday", "This week", "Last week", a month. Each is taken as a
span of days and a day within it. A song is brought in when it was surely
played after the last time it was brought in (its span starts after that
day), so the same play is not counted again as it moves from "Today" to
"Yesterday" to "This week"; and not at all when Dannify already has a listen
of it in that span, since what Dannify plays is told to YouTube Music too
(account.add_history) and comes back in its history.

What is brought in stays on this computer: it is not sent to ListenBrainz,
which is told only of what Dannify played, as it was played.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from . import account, listens

_FILE = 'ytm_history.json'
_lock = threading.Lock()
_path: Optional[Path] = None
# A history of a few hundred songs is what YouTube Music gives; more than
# this at once is something odd.
MOST = 600

_MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september',
           'october', 'november', 'december']
_WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']


def init(data_dir: Path) -> None:
    global _path
    _path = Path(data_dir) / _FILE


def _read() -> dict[str, Any]:
    if _path is None:
        return {}
    try:
        data = json.loads(_path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: dict[str, Any]) -> None:
    if _path is None:
        return
    try:
        tmp = _path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        tmp.replace(_path)
    except OSError:
        logger.opt(exception=True).warning('could not keep the YouTube Music history state')


def span_of(heading: str, today: date) -> tuple[date, date, date]:
    """(first day, last day, the day to put it on) for a history heading."""

    words = re.sub(r'\s+', ' ', str(heading or '').strip().lower())
    if words == 'today':
        return today, today, today
    if words == 'yesterday':
        y = today - timedelta(days=1)
        return y, y, y
    if words in _WEEKDAYS:
        back = (today.weekday() - _WEEKDAYS.index(words)) % 7 or 7
        d = today - timedelta(days=back)
        return d, d, d
    if words == 'this week':
        return today - timedelta(days=6), today - timedelta(days=2), today - timedelta(days=3)
    if words == 'last week':
        return today - timedelta(days=13), today - timedelta(days=7), today - timedelta(days=9)
    if words == 'this month':
        first = today.replace(day=1)
        last = max(first, today - timedelta(days=7))
        return first, last, max(first, today - timedelta(days=14))
    if words == 'last month':
        last = today.replace(day=1) - timedelta(days=1)
        first = last.replace(day=1)
        return first, last, last.replace(day=min(15, last.day))
    found = re.match(r'^([a-z]+)(?: (\d{4}))?$', words)
    if found and found.group(1) in _MONTHS:
        month = _MONTHS.index(found.group(1)) + 1
        year = int(found.group(2)) if found.group(2) else today.year
        first = date(year, month, 1)
        if first > today:
            first = date(year - 1, month, 1)
        last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        last = min(last, today)
        return first, last, min(first.replace(day=15), last)
    # "Older", or a heading never seen before.
    return today - timedelta(days=365), today - timedelta(days=30), today - timedelta(days=45)


def _midday(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, 12).timestamp())


def _track(song: dict[str, Any]) -> dict[str, Any]:
    """A YouTube Music song as a listen keeps it (see playlists.clean_track)."""

    return {
        'video_id': song.get('video_id') or '',
        'title': song.get('name') or '',
        'album': song.get('album_name') or '',
        'album_id': song.get('album_id') or '',
        'cover_url': song.get('cover_url') or '',
        'artists': song.get('artists') or [],
        'artist_ids': song.get('artist_ids') or [],
        'duration': song.get('duration') or 0,
    }


def bring_in(items: list[dict[str, Any]], today: Optional[date] = None) -> dict[str, int]:
    """Keep what is new in *items* (YouTube Music's history, newest first)."""

    today = today or date.today()
    with _lock:
        state = _read()
        seen: dict[str, str] = dict(state.get('seen') or {})
        brought = checked = 0
        # Within one heading the newest is first: a few minutes apart, so the
        # order holds in History.
        rank: dict[str, int] = {}
        for item in items[:MOST]:
            song = account.song_from_item(item) if isinstance(item, dict) else None
            if not song or not song.get('video_id'):
                continue
            checked += 1
            video = song['video_id']
            first, last, on = span_of(item.get('played') or '', today)
            known = seen.get(video)
            if known and first.isoformat() <= known:
                continue
            seen[video] = on.isoformat()
            key = listens.song_key({'video_id': video})
            start = _midday(first) - 12 * 3600
            end = _midday(last) + 12 * 3600
            if listens.played_between(key, start, end):
                continue
            heading = item.get('played') or ''
            n = rank.get(heading, 0)
            rank[heading] = n + 1
            seconds = int(song.get('duration') or 0) or 180
            at = _midday(on) - n * 240
            now = int(time.time())
            # Played today, and it is not noon yet: just before now, not later.
            if at > now - 60:
                at = now - (n + 1) * 240
            found = listens.checked(_track(song), seconds, at)
            if found is not None and listens.keep(found):
                brought += 1
        total = int(state.get('total') or 0) + brought
        _write({'seen': seen, 'last': int(time.time()), 'total': total})
    if brought:
        logger.info('brought {} plays in from YouTube Music history', brought)
    return {'brought': brought, 'checked': checked, 'total': total}


def sync() -> dict[str, Any]:
    """Read YouTube Music's history and bring in what is new.

    Raises account.NotSignedIn when there is no Google session.
    """

    items = account.client(require_auth=True).get_history() or []
    return {**bring_in(items), 'last': int(time.time())}


def status() -> dict[str, Any]:
    state = _read()
    return {'last': int(state.get('last') or 0), 'total': int(state.get('total') or 0)}
