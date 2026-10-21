"""What has been listened to: a line for every listen, behind History and Stats.

A listen is a song heard for long enough to count (see ``counts``), not one
skipped past. Each is kept with when it started and for how long, so the app
can say what was played lately, what is played most, and how much.

Everything is one file in the app's data folder, ``listens.jsonl``, and it is
only ever added to: a line for a song the first time it is heard (and again
when more is known about it), a line for each listen. Playlists are written
whole on every change, which is fine for a file that changes when somebody
edits one. This changes with every song played, for years, so a listen costs
one short line on the end instead of the whole history written again. A line
cut short by a crash or a power cut is skipped when the file is read; every
line before it is as it was.

A song is kept the way a playlist keeps one (see playlists.clean_track), so
the window shows and plays it the same way: from the library when it is
saved, from YouTube by its id when it is not.
"""

from __future__ import annotations

import bisect
import json
import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from . import playlists

_lock = threading.RLock()
_path: Optional[Path] = None
_loaded = False
# The file's last line was cut short: the next one starts on a line of its
# own, or the two would run together and both be lost.
_torn = False
_songs: dict[str, dict[str, Any]] = {}
# (started, seconds, key), oldest first.
_plays: list[tuple[int, int, str]] = []
_seen: set[tuple[int, str]] = set()

# Half a minute is a listen. It is the mark scrobblers have used for twenty
# years, and it is about where "that was not what I wanted" ends.
MIN_SECONDS = 30
# One listen is never longer than this, whatever the window says: a count
# left running by a clock change must not become a month of listening.
MAX_SECONDS = 12 * 3600
# Nothing was listened to before the app existed. A time before this is a
# clock that was wrong, and is put right rather than believed.
_EARLIEST = 1577836800  # 2020-01-01
# Beyond this many days the chart is drawn by month: a bar for each of a
# thousand days is not a chart.
_DAILY_UP_TO = 92
# What "you have not played this in a while" means, for Rediscover.
_FORGOTTEN_AFTER_DAYS = 30
_REDISCOVER_MIN_PLAYS = 3
_REDISCOVER = 12


def init(data_dir: Path) -> None:
    """Where the file is. It is read the first time something asks."""

    global _path, _loaded, _torn
    with _lock:
        _path = Path(data_dir) / 'listens.jsonl'
        _loaded = False
        _torn = False
        _songs.clear()
        _plays.clear()
        _seen.clear()


def counts(seconds: float, duration: float = 0) -> bool:
    """Whether *seconds* of a song was a listen, and not a skip.

    Half a minute, or half the song when the song is too short for that: an
    intro of forty seconds heard to the end was listened to.
    """

    if seconds >= MIN_SECONDS:
        return True
    return duration > 0 and seconds >= 5 and seconds >= duration / 2


def song_key(song: dict[str, Any]) -> str:
    """What makes two listens the same song.

    Its YouTube id when it has one, so a song streamed and the same song
    played from its saved file are one song with one count. Only a saved
    file that never had an id goes by its path.
    """

    video = str(song.get('video_id') or '')
    if video:
        return 'v:' + video[:64]
    return 'f:' + str(song.get('file') or '')


def _load() -> None:
    """Read the file, once. Called with the lock held."""

    global _loaded, _torn
    if _loaded:
        return
    _loaded = True
    if _path is None:
        return
    try:
        text = _path.read_text(encoding='utf-8', errors='replace')
    except FileNotFoundError:
        return
    except OSError:
        logger.opt(exception=True).warning('listening history could not be read')
        return
    _torn = bool(text) and not text.endswith('\n')
    plays: list[tuple[int, int, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue  # cut short, or damaged: this line only
        if isinstance(row, dict):
            key = row.get('k')
            song = playlists.clean_track(row)
            if isinstance(key, str) and key and song is not None:
                _songs[key] = song
        elif isinstance(row, list) and len(row) == 3:
            at, seconds, key = row
            if (
                isinstance(at, (int, float))
                and isinstance(seconds, (int, float))
                and isinstance(key, str)
            ):
                plays.append((int(at), int(seconds), key))
    # A song's line comes before its listens, so a listen with no song is one
    # whose song line was the damaged one. It cannot be shown; it is let go.
    for play in sorted(plays):
        if play[2] in _songs and (play[0], play[2]) not in _seen:
            _plays.append(play)
            _seen.add((play[0], play[2]))


def _append(lines: list[str]) -> bool:
    global _torn
    if _path is None:
        return False
    try:
        _path.parent.mkdir(parents=True, exist_ok=True)
        with _path.open('a', encoding='utf-8', newline='\n') as f:
            f.write(('\n' if _torn else '') + ''.join(line + '\n' for line in lines))
        _torn = False
        return True
    except OSError:
        logger.opt(exception=True).warning('could not add to the listening history')
        return False


def _rewrite() -> None:
    """Write the file again from what is in memory, after something was taken
    out. Whole and atomically, as playlists are: the old file stays until the
    new one is complete."""

    global _torn
    if _path is None:
        return
    used = {key for _, _, key in _plays}
    for key in [k for k in _songs if k not in used]:
        del _songs[key]
    lines = [json.dumps({'k': key, **_songs[key]}, ensure_ascii=False) for key in sorted(_songs)]
    lines += [json.dumps([at, seconds, key], ensure_ascii=False) for at, seconds, key in _plays]
    part = _path.with_name(_path.name + '.part')
    try:
        if not lines:
            _path.unlink(missing_ok=True)
        else:
            part.write_text(''.join(line + '\n' for line in lines), encoding='utf-8', newline='\n')
            os.replace(part, _path)
        _torn = False
    except OSError:
        logger.opt(exception=True).warning('could not save the listening history')


def _merged(known: Optional[dict[str, Any]], song: dict[str, Any]) -> dict[str, Any]:
    """What is known about a song, with what this listen adds.

    The same song arrives streamed (a picture from the web, no file) and from
    its saved file (a file, no picture). Each fills in what the other lacks;
    neither wipes it out.
    """

    if known is None:
        return song
    out = dict(known)
    for name, value in song.items():
        if value not in ('', [], 0, None):
            out[name] = value
    return out


def checked(
    track: Any,
    seconds: Any,
    started: Any = None,
    now: Optional[float] = None,
) -> Optional[tuple[dict[str, Any], int, int]]:
    """``(song, started, seconds)`` for a listen that counts, put right where
    the window's clock was wrong; None for a skip or something unreadable."""

    song = playlists.clean_track(track)
    if song is None:
        return None
    try:
        heard = int(float(seconds))
    except (TypeError, ValueError):
        return None
    if not counts(heard, song.get('duration') or 0):
        return None
    heard = min(heard, MAX_SECONDS)
    now = time.time() if now is None else now
    try:
        at = int(float(started))
    except (TypeError, ValueError):
        at = 0
    if at < _EARLIEST or at > now + 300:
        at = int(now - heard)
    return song, at, heard


def record(
    track: Any,
    seconds: Any,
    started: Any = None,
    now: Optional[float] = None,
) -> bool:
    """Keep one listen. False when it was a skip, or it is already kept."""

    found = checked(track, seconds, started, now)
    return keep(found) if found is not None else False


def keep(found: tuple[dict[str, Any], int, int]) -> bool:
    """Keep a listen checked() has passed. False when it is already kept."""

    song, at, heard = found
    key = song_key(song)
    with _lock:
        _load()
        # The window keeps a listen it could not hand over and offers it
        # again on its next start, so the same one can arrive twice.
        if (at, key) in _seen:
            return False
        lines = []
        merged = _merged(_songs.get(key), song)
        if merged != _songs.get(key):
            lines.append(json.dumps({'k': key, **merged}, ensure_ascii=False))
        lines.append(json.dumps([at, heard, key], ensure_ascii=False))
        if not _append(lines):
            return False
        _songs[key] = merged
        bisect.insort(_plays, (at, heard, key))
        _seen.add((at, key))
    return True


def forget(at: Any, key: str) -> bool:
    """Take one listen out of the history."""

    try:
        when = int(float(at))
    except (TypeError, ValueError):
        return False
    with _lock:
        _load()
        if (when, key) not in _seen:
            return False
        _plays[:] = [p for p in _plays if not (p[0] == when and p[2] == key)]
        _seen.discard((when, key))
        _rewrite()
    return True


def played_between(key: str, start: int, end: int) -> bool:
    """Whether the song *key* was listened to from *start* up to *end*."""

    with _lock:
        _load()
        i = bisect.bisect_left(_plays, (int(start), -1, ''))
        while i < len(_plays) and _plays[i][0] < end:
            if _plays[i][2] == key:
                return True
            i += 1
    return False


def clear() -> None:
    """Forget everything that was listened to."""

    with _lock:
        _load()
        _songs.clear()
        _plays.clear()
        _seen.clear()
        _rewrite()


def _entry(songs: dict[str, dict[str, Any]], key: str, **extra: Any) -> dict[str, Any]:
    """A song as the window is given it: what a playlist would keep of it,
    its key, and whatever is being said about it (when, how often)."""

    return {**songs[key], 'key': key, **extra}


def history(limit: int = 100, before: int = 0) -> dict[str, Any]:
    """The latest listens, newest first: ``{items, more, total}``.

    *before* is the time of the oldest one already shown, to carry on from.
    """

    limit = max(1, min(int(limit), 500))
    with _lock:
        _load()
        end = len(_plays)
        if before:
            end = bisect.bisect_left(_plays, (int(before), -1, ''))
        start = max(0, end - limit)
        items = [
            _entry(_songs, key, at=at, seconds=seconds)
            for at, seconds, key in reversed(_plays[start:end])
        ]
        return {'items': items, 'more': start > 0, 'total': len(_plays)}


def _day_start(day: date) -> int:
    """Midnight at the start of *day*, here: days are the listener's own."""

    return int(time.mktime((day.year, day.month, day.day, 0, 0, 0, 0, 0, -1)))


def _cover(song: dict[str, Any]) -> str:
    # The way a playlist names its pictures (see playlists._summary).
    return song.get('cover_url') or (('file:' + song['file']) if song.get('file') else '')


def _streaks(days: set[date], today: date) -> tuple[int, int]:
    """How many days in a row have had a listen: up to now, and at most."""

    current = 0
    # Today may not have had its listen yet. The run is not over until a
    # whole day has gone by without one.
    day = today if today in days else today - timedelta(days=1)
    while day in days:
        current += 1
        day -= timedelta(days=1)
    longest = run = 0
    last: Optional[date] = None
    for day in sorted(days):
        run = run + 1 if last is not None and day - last == timedelta(days=1) else 1
        longest = max(longest, run)
        last = day
    return current, longest


def _tally(chosen: list[tuple[int, int, str]], songs: dict[str, dict[str, Any]]) -> tuple:
    """Listens summed by song, artist, album and hour of the day.

    ``(by_song, by_artist, by_album, by_hour, total_seconds)``: by_song maps a
    song's key to [plays, seconds, last played].
    """

    by_song: dict[str, list[int]] = {}
    by_artist: dict[str, dict[str, Any]] = {}
    by_album: dict[tuple[str, str], dict[str, Any]] = {}
    by_hour = [0] * 24
    total_seconds = 0
    for at, seconds, key in chosen:
        song = songs[key]
        total_seconds += seconds
        tally = by_song.setdefault(key, [0, 0, 0])
        tally[0] += 1
        tally[1] += seconds
        tally[2] = max(tally[2], at)

        ids = {str(a.get('name', '')).casefold(): a.get('id', '') for a in song.get('artist_ids') or []}
        for name in song.get('artists') or []:
            folded = name.casefold().strip()
            if not folded:
                continue
            who = by_artist.setdefault(
                folded, {'name': name, 'id': '', 'plays': 0, 'seconds': 0, 'keys': {}}
            )
            who['plays'] += 1
            who['seconds'] += seconds
            who['id'] = who['id'] or ids.get(folded, '')
            who['keys'][key] = who['keys'].get(key, 0) + 1

        album = str(song.get('album') or '').strip()
        if album:
            first = (song.get('artists') or [''])[0]
            entry = by_album.setdefault(
                (album.casefold(), first.casefold()),
                {'name': album, 'artist': first, 'album_id': '', 'plays': 0, 'seconds': 0, 'keys': {}},
            )
            entry['plays'] += 1
            entry['seconds'] += seconds
            entry['album_id'] = entry['album_id'] or song.get('album_id', '')
            entry['keys'][key] = entry['keys'].get(key, 0) + 1

        by_hour[time.localtime(at).tm_hour] += seconds
    return by_song, by_artist, by_album, by_hour, total_seconds


def _ranked(songs, by_song, by_artist, by_album, top: int) -> tuple[list, list, list]:
    """The songs, artists and albums of a tally, the most listened first."""

    def most_played(keys: dict[str, int]) -> dict[str, Any]:
        return songs[max(keys, key=lambda k: (keys[k], by_song[k][1]))]

    top_songs = [
        _entry(songs, key, plays=n, seconds=s, last=last)
        for key, (n, s, last) in sorted(
            by_song.items(), key=lambda item: (-item[1][0], -item[1][1], item[0])
        )[:top]
    ]
    top_artists = [
        {
            'name': who['name'],
            'id': who['id'],
            'plays': who['plays'],
            'seconds': who['seconds'],
            'songs': len(who['keys']),
            'cover': _cover(most_played(who['keys'])),
        }
        for who in sorted(
            by_artist.values(), key=lambda w: (-w['seconds'], -w['plays'], w['name'])
        )[:top]
    ]
    top_albums = [
        {
            'name': entry['name'],
            'artist': entry['artist'],
            'album_id': entry['album_id'],
            'plays': entry['plays'],
            'seconds': entry['seconds'],
            'songs': len(entry['keys']),
            'cover': _cover(most_played(entry['keys'])),
        }
        for entry in sorted(
            by_album.values(), key=lambda e: (-e['seconds'], -e['plays'], e['name'])
        )[:top]
    ]
    return top_songs, top_artists, top_albums


def stats(days: int = 0, top: int = 50, now: Optional[float] = None) -> dict[str, Any]:
    """What was listened to in the last *days* days (0: ever), summed up.

    The totals, the songs, artists and albums played most, how the listening
    was spread over the days (or the months, for a long stretch) and over the
    hours of the day, and the same totals for the stretch before, to compare.
    """

    now = time.time() if now is None else now
    top = max(1, min(int(top), 200))
    days = max(0, int(days))
    today = date.fromtimestamp(now)
    with _lock:
        _load()
        plays = list(_plays)
        songs = dict(_songs)

    since = previous_since = 0
    if days:
        first_day = today - timedelta(days=days - 1)
        since = _day_start(first_day)
        previous_since = _day_start(first_day - timedelta(days=days))
    chosen = plays[bisect.bisect_left(plays, (since, -1, '')):] if since else plays

    by_song, by_artist, by_album, by_hour, total_seconds = _tally(chosen, songs)
    by_bucket: dict[str, list[int]] = {}
    monthly = not days or days > _DAILY_UP_TO

    for at, seconds, _key in chosen:
        local = time.localtime(at)
        label = (
            f'{local.tm_year:04d}-{local.tm_mon:02d}'
            if monthly
            else f'{local.tm_year:04d}-{local.tm_mon:02d}-{local.tm_mday:02d}'
        )
        bucket = by_bucket.setdefault(label, [0, 0])
        bucket[0] += seconds
        bucket[1] += 1

    top_songs, top_artists, top_albums = _ranked(songs, by_song, by_artist, by_album, top)

    # Every day (or month) of the stretch, the empty ones too: a chart with
    # the quiet days left out says the listening never stopped.
    labels: list[str] = []
    if chosen or days:
        if monthly:
            start = date.fromtimestamp(since) if since else date.fromtimestamp(chosen[0][0])
            year, month = start.year, start.month
            while (year, month) <= (today.year, today.month):
                labels.append(f'{year:04d}-{month:02d}')
                year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        else:
            day = today - timedelta(days=days - 1)
            while day <= today:
                labels.append(day.isoformat())
                day += timedelta(days=1)
    buckets = [
        {'label': label, 'seconds': by_bucket.get(label, [0, 0])[0], 'plays': by_bucket.get(label, [0, 0])[1]}
        for label in labels
    ]

    previous = None
    if days:
        lo = bisect.bisect_left(plays, (previous_since, -1, ''))
        hi = bisect.bisect_left(plays, (since, -1, ''))
        previous = {
            'seconds': sum(p[1] for p in plays[lo:hi]),
            'plays': hi - lo,
        }

    current, longest = _streaks({date.fromtimestamp(p[0]) for p in plays}, today)

    # Played a good deal, and then not for a while.
    cutoff = now - _FORGOTTEN_AFTER_DAYS * 86400
    ever: dict[str, list[int]] = {}
    for at, seconds, key in plays:
        tally = ever.setdefault(key, [0, 0, 0])
        tally[0] += 1
        tally[1] += seconds
        tally[2] = max(tally[2], at)
    rediscover = [
        _entry(songs, key, plays=n, seconds=s, last=last)
        for key, (n, s, last) in sorted(
            ever.items(), key=lambda item: (-item[1][0], -item[1][1], item[0])
        )
        if n >= _REDISCOVER_MIN_PLAYS and last < cutoff
    ][:_REDISCOVER]

    return {
        'days': days,
        'seconds': total_seconds,
        'plays': len(chosen),
        'songs': len(by_song),
        'artists': len(by_artist),
        'albums': len(by_album),
        'previous': previous,
        'first': plays[0][0] if plays else 0,
        'streak': current,
        'longest_streak': longest,
        'bucket': 'month' if monthly else 'day',
        'buckets': buckets,
        'by_hour': by_hour,
        'top_songs': top_songs,
        'top_artists': top_artists,
        'top_albums': top_albums,
        'rediscover': rediscover,
    }


# ---------------------------------------------------------------------------
# Made from what is listened to
# ---------------------------------------------------------------------------
# A mix is a list of songs, played and saved like any playlist, kept up to
# date by the listening itself. Fewer songs than this and it is not shown.
_MIX_SIZE = 40
_MIX_MIN = 4
_ON_REPEAT_DAYS = 21


def mixes(now: Optional[float] = None) -> dict[str, Any]:
    """``{mixes: [{id, songs}]}``: On repeat, Forgotten favourites and Top
    this month, each left out while it has too few songs to be a mix."""

    now = time.time() if now is None else now
    with _lock:
        _load()
        plays = list(_plays)
        songs = dict(_songs)

    def since(moment: float) -> list[tuple[int, int, str]]:
        return plays[bisect.bisect_left(plays, (int(moment), -1, '')):]

    def tally(chosen: list[tuple[int, int, str]]) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        for at, seconds, key in chosen:
            row = out.setdefault(key, [0, 0, 0])
            row[0] += 1
            row[1] += seconds
            row[2] = max(row[2], at)
        return out

    def listed(rows: list[tuple[str, list[int]]]) -> list[dict[str, Any]]:
        return [
            _entry(songs, key, plays=n, seconds=s, last=last) for key, (n, s, last) in rows[:_MIX_SIZE]
        ]

    found: list[dict[str, Any]] = []

    # What has been played more than once lately, the most played first.
    recent = tally(since(now - _ON_REPEAT_DAYS * 86400))
    on_repeat = sorted(
        ((k, v) for k, v in recent.items() if v[0] >= 2), key=lambda kv: (-kv[1][0], -kv[1][2], kv[0])
    )
    # Played a good deal, and then not for a month.
    cutoff = now - _FORGOTTEN_AFTER_DAYS * 86400
    ever = tally(plays)
    forgotten = sorted(
        ((k, v) for k, v in ever.items() if v[0] >= _REDISCOVER_MIN_PLAYS and v[2] < cutoff),
        key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]),
    )
    # This calendar month, by time listened.
    first_of_month = _day_start(date.fromtimestamp(now).replace(day=1))
    month = sorted(tally(since(first_of_month)).items(), key=lambda kv: (-kv[1][1], -kv[1][0], kv[0]))

    for mix_id, rows in (('on_repeat', on_repeat), ('forgotten', forgotten), ('top_month', month)):
        if len(rows) >= _MIX_MIN:
            found.append({'id': mix_id, 'songs': listed(rows)})
    return {'mixes': found}


def recap(year: int, now: Optional[float] = None) -> dict[str, Any]:
    """A year of listening, for "Your year in music"."""

    now = time.time() if now is None else now
    with _lock:
        _load()
        plays = list(_plays)
        songs = dict(_songs)

    years = sorted({date.fromtimestamp(p[0]).year for p in plays}, reverse=True)
    start = _day_start(date(year, 1, 1))
    end = _day_start(date(year + 1, 1, 1))
    lo = bisect.bisect_left(plays, (start, -1, ''))
    hi = bisect.bisect_left(plays, (end, -1, ''))
    chosen = plays[lo:hi]

    by_song, by_artist, by_album, by_hour, total = _tally(chosen, songs)
    # Twenty-five songs: five are shown, all of them make "Your top songs of
    # the year" when it is saved as a playlist.
    top_songs, top_artists, top_albums = _ranked(songs, by_song, by_artist, by_album, 25)
    top_artists, top_albums = top_artists[:5], top_albums[:5]

    by_day: dict[date, int] = {}
    months = [0] * 12
    weekdays = [0] * 7  # Monday first
    # Each month's own favourite artist, and the most a song was played in a day.
    month_artists: list[dict[str, list]] = [{} for _ in range(12)]
    song_days: dict[tuple[str, date], int] = {}
    first_heard: dict[str, int] = {}
    for at, seconds, key in chosen:
        day = date.fromtimestamp(at)
        by_day[day] = by_day.get(day, 0) + seconds
        months[day.month - 1] += seconds
        weekdays[day.weekday()] += seconds
        song_days[(key, day)] = song_days.get((key, day), 0) + 1
        first_heard.setdefault(key, at)
        for name in songs[key].get('artists') or []:
            folded = name.casefold().strip()
            if folded:
                who = month_artists[day.month - 1].setdefault(folded, [name, 0, {}])
                who[1] += seconds
                who[2][key] = who[2].get(key, 0) + 1
    busiest = max(by_day.items(), key=lambda kv: (kv[1], kv[0])) if by_day else None
    _current, longest = _streaks(set(by_day), date.fromtimestamp(min(now, end - 1)))

    # Artists first heard this year: not in anything played before it.
    before: set[str] = set()
    for _at, _seconds, key in plays[:lo]:
        for name in songs[key].get('artists') or []:
            before.add(name.casefold().strip())
    new_artists = sum(1 for folded in by_artist if folded not in before)

    def month_top(tally: dict[str, list]) -> Optional[dict[str, Any]]:
        if not tally:
            return None
        name, seconds, keys = max(tally.values(), key=lambda w: (w[1], w[0]))
        favourite = max(keys, key=lambda k: keys[k])
        return {'name': name, 'seconds': seconds, 'cover': _cover(songs[favourite])}

    # The song played most in a single day: the year's "on repeat" moment.
    repeat = None
    if song_days:
        (key, day), n = max(song_days.items(), key=lambda kv: (kv[1], kv[0][1]))
        if n > 1:
            repeat = _entry(songs, key, plays=n, date=day.isoformat())
    top_song_more = None
    if top_songs:
        key = top_songs[0]['key']
        top_song_more = {
            'first': date.fromtimestamp(first_heard[key]).isoformat(),
            'most_in_a_day': max((n for (k, _d), n in song_days.items() if k == key), default=0),
        }

    # The year before, to say how this one compares.
    before_lo = bisect.bisect_left(plays, (_day_start(date(year - 1, 1, 1)), -1, ''))
    last_year = plays[before_lo:lo]

    return {
        'year': year,
        'years': years,
        'seconds': total,
        'hours': by_hour,
        'weekdays': weekdays,
        'month_artists': [month_top(m) for m in month_artists],
        'repeat': repeat,
        'top_song_more': top_song_more,
        'last_year': {'seconds': sum(sec for _at, sec, _k in last_year), 'plays': len(last_year)},
        'plays': len(chosen),
        'songs': len(by_song),
        'artists': len(by_artist),
        'albums': len(by_album),
        'days': len(by_day),
        'longest_streak': longest,
        'busiest_day': {'date': busiest[0].isoformat(), 'seconds': busiest[1]} if busiest else None,
        'peak_hour': max(range(24), key=lambda h: by_hour[h]) if total else None,
        'months': months,
        'new_artists': new_artists,
        'top_songs': top_songs,
        'top_artists': top_artists,
        'top_albums': top_albums,
        'first': _entry(songs, chosen[0][2], at=chosen[0][0]) if chosen else None,
    }
