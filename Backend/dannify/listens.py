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
# One sitting: songs that follow each other with no more than this between
# the end of one and the start of the next.
_SESSION_GAP = 10 * 60
# A song played this many times in one day is "on repeat" that day.
_REPEAT_MIN = 3
# Songs first heard in the stretch, shown on the Stats page.
_DISCOVERIES = 20


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


def between(start: int, end: int, top: int = 20) -> dict[str, Any]:
    """What was played from *start* up to *end* (times in seconds): how much,
    and the songs and artists played most. A special day's music, a year on.
    """

    top = max(1, min(int(top), 100))
    with _lock:
        _load()
        low = bisect.bisect_left(_plays, (int(start), -1, ''))
        high = bisect.bisect_left(_plays, (int(end), -1, ''))
        chosen = list(_plays[low:high])
        songs = dict(_songs)
    by_song, by_artist, by_album, _by_hour, total_seconds = _tally(chosen, songs)
    top_songs, top_artists, _top_albums = _ranked(songs, by_song, by_artist, by_album, top)
    return {
        'plays': len(chosen),
        'seconds': total_seconds,
        'songs': top_songs,
        'artists': top_artists[:8],
    }


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


def _highlights(chosen: list, plays: list, songs: dict, since: float) -> tuple[list, dict, list]:
    """The week, the moments worth telling, and what was new, for a stretch.

    ``(by_weekday, highlights, discoveries)``: seconds for each day of the
    week (Monday first); the biggest day, the longest sitting, the song
    played most in one day, the average day and how much was new; and the
    songs first heard in the stretch, the most played first. Nothing is new
    in "ever".
    """

    by_weekday = [0] * 7
    by_day: dict[date, int] = {}
    day_song: dict[tuple[date, str], int] = {}
    for at, seconds, key in chosen:
        day = date.fromtimestamp(at)
        by_weekday[day.weekday()] += seconds
        by_day[day] = by_day.get(day, 0) + seconds
        day_song[(day, key)] = day_song.get((day, key), 0) + 1

    best_day = None
    if by_day:
        day, seconds = max(by_day.items(), key=lambda kv: (kv[1], kv[0]))
        best_day = {'date': day.isoformat(), 'seconds': seconds}

    # The longest sitting: plays one after another, each starting no more
    # than _SESSION_GAP after the one before ended.
    session = None
    start = end = heard = count = 0
    for at, seconds, _key in chosen:
        if count and at - end <= _SESSION_GAP:
            heard += seconds
            count += 1
            end = max(end, at + seconds)
        else:
            start, end, heard, count = at, at + seconds, seconds, 1
        if session is None or heard > session['seconds']:
            session = {'start': start, 'seconds': heard, 'plays': count}

    repeat = None
    if day_song:
        (day, key), n = max(day_song.items(), key=lambda kv: (kv[1], kv[0][0]))
        if n >= _REPEAT_MIN:
            repeat = {'date': day.isoformat(), 'plays': n, 'song': _entry(songs, key)}

    new_songs = new_artists = 0
    discoveries: list[dict[str, Any]] = []
    if since:
        first_song: dict[str, int] = {}
        first_artist: dict[str, int] = {}
        for at, _seconds, key in plays:
            first_song.setdefault(key, at)
            for name in songs.get(key, {}).get('artists') or []:
                first_artist.setdefault(name.casefold().strip(), at)
        fresh = {key for key, at in first_song.items() if at >= since}
        new_songs = len(fresh)
        new_artists = sum(1 for name, at in first_artist.items() if name and at >= since)
        tally: dict[str, list[int]] = {}
        for at, seconds, key in chosen:
            if key in fresh:
                t = tally.setdefault(key, [0, 0, 0])
                t[0] += 1
                t[1] += seconds
                t[2] = max(t[2], at)
        discoveries = [
            _entry(songs, key, plays=n, seconds=secs, last=last)
            for key, (n, secs, last) in sorted(tally.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
        ][:_DISCOVERIES]

    active_days = len(by_day)
    highlights = {
        'best_day': best_day,
        'session': session,
        'repeat': repeat,
        'active_days': active_days,
        'per_day': round(sum(by_day.values()) / active_days) if active_days else 0,
        'new_songs': new_songs,
        'new_artists': new_artists,
    }
    return by_weekday, highlights, discoveries


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
            'songs': len({p[2] for p in plays[lo:hi]}),
        }
    by_weekday, highlights, discoveries = _highlights(chosen, plays, songs, since)

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
        'by_weekday': by_weekday,
        'highlights': highlights,
        'discoveries': discoveries,
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
    """A year of listening: the year's story (see story)."""

    return story('year', year, now)


# ---------------------------------------------------------------------------
# Your Soundtrack: a story of any stretch of time
# ---------------------------------------------------------------------------

PERIODS = ('day', 'week', 'month', 'year')
# Lifetime marks worth a word when a stretch crosses them.
_HOUR_MARKS = (10, 25, 50, 100, 250, 500, 1000, 2500, 5000)
_PLAY_MARKS = (100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000)
# How many different songs make a stretch "a little of everything".
_VARIETY = {'day': 12, 'week': 30, 'month': 70, 'year': 250}


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _next_month(day: date) -> date:
    return date(day.year + 1, 1, 1) if day.month == 12 else date(day.year, day.month + 1, 1)


def _bounds(
    period: str, today: date, year: Optional[int] = None, ago: int = 0, week_start: int = 0
) -> tuple[date, date, date]:
    """Where a stretch starts and ends (end not included), and where the one
    before it starts: today; this week, from the day weeks start where the
    listener is (``week_start``, Monday 0 to Sunday 6); this month; a year.
    ``ago`` steps back that many stretches: yesterday, last week, last month."""

    ago = max(0, int(ago or 0))
    if period == 'day':
        day = today - timedelta(days=ago)
        return day, day + timedelta(days=1), day - timedelta(days=1)
    if period == 'week':
        start = today - timedelta(days=(today.weekday() - week_start) % 7) - timedelta(days=7 * ago)
        return start, start + timedelta(days=7), start - timedelta(days=7)
    if period == 'month':
        start = _month_start(today)
        for _ in range(ago):
            start = _month_start(start - timedelta(days=1))
        return start, _next_month(start), _month_start(start - timedelta(days=1))
    y = year or today.year
    return date(y, 1, 1), date(y + 1, 1, 1), date(y - 1, 1, 1)


def _part_of(period: str, day: date, at: int, start: date) -> int:
    """Which part of the stretch a listen fell in, for "each part's own
    favourite": a year's months, a month's weeks, a week's days, a day's
    night, morning, afternoon and evening."""

    if period == 'year':
        return day.month - 1
    if period == 'month':
        return min(4, (day.day - 1) // 7)
    if period == 'week':
        return (day - start).days
    return time.localtime(at).tm_hour // 6


_PARTS = {'year': 12, 'month': 5, 'week': 7, 'day': 4}


def _chart_of(period: str, day: date, at: int, start: date) -> int:
    """The finer bars: a year by month, a month by day, a week by day, a day by hour."""

    if period == 'year':
        return day.month - 1
    if period == 'month':
        return day.day - 1
    if period == 'week':
        return (day - start).days
    return time.localtime(at).tm_hour


def _chart_size(period: str, start: date, end: date) -> int:
    return {'year': 12, 'week': 7, 'day': 24}.get(period, (end - start).days)


def story(
    period: str = 'year',
    year: Optional[int] = None,
    now: Optional[float] = None,
    ago: int = 0,
    week_start: int = 0,
) -> dict[str, Any]:
    """A stretch of listening told as a story: today, this week, this month,
    or a year, or one before (``ago``: yesterday, last week, last month).
    What was played most, when, how it compares with the stretch before, and
    the moments worth saying (``insights``), the strongest first."""

    if period not in PERIODS:
        period = 'year'
    now = time.time() if now is None else now
    with _lock:
        _load()
        plays = list(_plays)
        songs = dict(_songs)
    return _story(plays, songs, period, year, now, ago, week_start)


def _story(
    plays, songs, period: str, year: Optional[int], now: float, ago: int = 0, week_start: int = 0
) -> dict[str, Any]:
    today = date.fromtimestamp(now)
    week_start = int(week_start or 0) % 7
    ago = 0 if period == 'year' else max(0, min(int(ago or 0), 60))
    start_day, end_day, prev_day = _bounds(period, today, year, ago, week_start)
    start, end, prev_start = _day_start(start_day), _day_start(end_day), _day_start(prev_day)
    years = sorted({date.fromtimestamp(p[0]).year for p in plays}, reverse=True)
    lo = bisect.bisect_left(plays, (start, -1, ''))
    hi = bisect.bisect_left(plays, (end, -1, ''))
    before_lo = bisect.bisect_left(plays, (prev_start, -1, ''))
    chosen = plays[lo:hi]
    previous = plays[before_lo:lo]

    by_song, by_artist, by_album, by_hour, total = _tally(chosen, songs)
    # Twenty-five songs: five are shown, all of them make the playlist when
    # the story is saved as one.
    top_songs, top_artists, top_albums = _ranked(songs, by_song, by_artist, by_album, 25)
    top_artists, top_albums = top_artists[:5], top_albums[:5]

    by_day: dict[date, int] = {}
    weekdays = [0] * 7  # Monday first
    chart = [0] * _chart_size(period, start_day, end_day)
    parts: list[dict[str, list]] = [{} for _ in range(_PARTS[period])]
    song_days: dict[tuple[str, date], int] = {}
    first_heard: dict[str, int] = {}
    for at, seconds, key in chosen:
        day = date.fromtimestamp(at)
        by_day[day] = by_day.get(day, 0) + seconds
        weekdays[day.weekday()] += seconds
        chart[_chart_of(period, day, at, start_day)] += seconds
        song_days[(key, day)] = song_days.get((key, day), 0) + 1
        first_heard.setdefault(key, at)
        part = parts[_part_of(period, day, at, start_day)]
        for name in songs[key].get('artists') or []:
            folded = name.casefold().strip()
            if folded:
                who = part.setdefault(folded, [name, 0, {}])
                who[1] += seconds
                who[2][key] = who[2].get(key, 0) + 1
    busiest = max(by_day.items(), key=lambda kv: (kv[1], kv[0])) if by_day else None
    _current, longest = _streaks(set(by_day), date.fromtimestamp(min(now, end - 1)))

    # Artists first heard in this stretch: not in anything played before it.
    history = _history(plays[:lo], songs)
    new_artist_keys = [folded for folded in by_artist if folded not in history['artists']]

    def part_top(tally: dict[str, list]) -> Optional[dict[str, Any]]:
        if not tally:
            return None
        name, seconds, keys = max(tally.values(), key=lambda w: (w[1], w[0]))
        favourite = max(keys, key=lambda k: keys[k])
        return {'name': name, 'seconds': seconds, 'cover': _cover(songs[favourite])}

    # The song played most in a single day: the stretch's "on repeat" moment.
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

    before = {'seconds': sum(sec for _at, sec, _k in previous), 'plays': len(previous)}
    out = {
        'period': period,
        'ago': ago,
        'week_start': week_start,
        'start': start_day.isoformat(),
        'end': end_day.isoformat(),
        'year': start_day.year,
        'years': years,
        'seconds': total,
        'hours': by_hour,
        'weekdays': weekdays,
        'chart': chart,
        'parts': [part_top(p) for p in parts],
        'repeat': repeat,
        'top_song_more': top_song_more,
        'before': before,
        'plays': len(chosen),
        'songs': len(by_song),
        'artists': len(by_artist),
        'albums': len(by_album),
        'days': len(by_day),
        'longest_streak': longest,
        'busiest_day': {'date': busiest[0].isoformat(), 'seconds': busiest[1]} if busiest else None,
        'peak_hour': max(range(24), key=lambda h: by_hour[h]) if total else None,
        'new_artists': len(new_artist_keys),
        'top_songs': top_songs,
        'top_artists': top_artists,
        'top_albums': top_albums,
        'first': _entry(songs, chosen[0][2], at=chosen[0][0]) if chosen else None,
    }
    out['insights'] = _insights(
        plays, songs, period, out, chosen, previous, history, by_artist, by_day, new_artist_keys, start_day, end_day, now
    )
    if period == 'year':
        # The names the year's story has always used.
        out['months'] = chart
        out['month_artists'] = out['parts']
        out['last_year'] = before
    return out


def _history(before: list[tuple[int, int, str]], songs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Everything played before a stretch, in one pass: the artists already
    known, each day's minutes, every song's last listen and count."""

    artists: set[str] = set()
    days: dict[date, int] = {}
    last: dict[str, int] = {}
    count: dict[str, int] = {}
    seconds = 0
    for at, sec, key in before:
        if key not in count:
            for name in songs[key].get('artists') or []:
                artists.add(name.casefold().strip())
        day = date.fromtimestamp(at)
        days[day] = days.get(day, 0) + sec
        last[key] = at
        count[key] = count.get(key, 0) + 1
        seconds += sec
    return {'artists': artists, 'days': days, 'last': last, 'count': count, 'seconds': seconds, 'plays': len(before)}


def _insights(plays, songs, period, d, chosen, previous, history, by_artist, by_day, new_artist_keys, start_day, end_day, now):
    """The moments of a stretch worth saying, each with how much it is worth
    saying, the strongest first: records, streaks, climbs, comebacks, firsts,
    milestones. Words are the window's; this says what and how much."""

    found: list[dict[str, Any]] = []
    total = d['seconds']
    if not chosen:
        return found
    today = date.fromtimestamp(now)
    ongoing = start_day <= today < end_day

    # More than the stretch before: only ever said when it is more.
    before = d['before']['seconds']
    if before >= 600 and total > before * 1.1:
        percent = round((total - before) / before * 100)
        found.append({'kind': 'more', 'percent': percent, 'score': 55 + min(30, percent // 5)})

    # A record: the biggest day ever, by a margin, with some history behind it.
    best_before = history['days']
    if d['busiest_day'] and len(best_before) >= 7:
        record = max(best_before.values())
        if d['busiest_day']['seconds'] > record * 1.05:
            found.append({
                'kind': 'record_day',
                'date': d['busiest_day']['date'],
                'minutes': round(d['busiest_day']['seconds'] / 60),
                'score': 92,
            })

    # A run of days, still going.
    if ongoing:
        all_days = {date.fromtimestamp(at) for at, _s, _k in plays}
        current, _longest = _streaks(all_days, today)
        if current >= 3:
            found.append({'kind': 'streak', 'days': current, 'score': 60 + min(30, current * 3)})

    # Every single day of it so far.
    elapsed = (min(today, end_day - timedelta(days=1)) - start_day).days + 1
    if period in ('week', 'month') and elapsed >= 4 and len(by_day) >= elapsed:
        found.append({'kind': 'every_day', 'days': elapsed, 'score': 74})

    # Lifetime marks crossed in this stretch: news while it is news, so today
    # and this week only. A month or a year has its own things to say.
    lifetime_before, lo = history['seconds'], history['plays']
    if period in ('day', 'week'):
        hours = [m for m in _HOUR_MARKS if lifetime_before < m * 3600 <= lifetime_before + total]
        if hours:
            found.append({'kind': 'milestone_hours', 'hours': hours[-1], 'score': 88})
        marks = [m for m in _PLAY_MARKS if lo < m <= lo + len(chosen)]
        if marks:
            found.append({'kind': 'milestone_plays', 'plays': marks[-1], 'score': 86})

    # An artist climbing: from far down, or from nowhere, into the top five.
    if previous and d['top_artists']:
        prev_artists = sorted(_tally(previous, songs)[1].values(), key=lambda w: (-w['seconds'], w['name']))
        prev_rank = {w['name'].casefold(): i for i, w in enumerate(prev_artists)}
        for i, a in enumerate(d['top_artists'][:5]):
            was = prev_rank.get(a['name'].casefold())
            if was is None and len(prev_artists) >= 3:
                found.append({'kind': 'new_in_top', 'artist': a['name'], 'id': a['id'], 'cover': a['cover'],
                              'rank': i + 1, 'score': 78 - i * 3})
                break
            if was is not None and was - i >= 3:
                found.append({'kind': 'climber', 'artist': a['name'], 'id': a['id'], 'cover': a['cover'],
                              'rank': i + 1, 'from': was + 1, 'score': 80 - i * 2})
                break

    # A comeback: a song back after a month or more away.
    last_before, count_before = history['last'], history['count']
    in_stretch: dict[str, list[int]] = {}
    for at, _sec, key in chosen:
        in_stretch.setdefault(key, []).append(at)
    back = [
        (len(ats), key, (min(ats) - last_before[key]) // 86400)
        for key, ats in in_stretch.items()
        if key in last_before and count_before.get(key, 0) >= 2 and min(ats) - last_before[key] >= 30 * 86400
    ]
    if back:
        n, key, days = max(back)
        found.append({'kind': 'comeback', 'song': _entry(songs, key, plays=n), 'days': int(days), 'score': 70})

    # New to you.
    if new_artist_keys and lo:
        best = max(new_artist_keys, key=lambda k: by_artist[k]['seconds'])
        found.append({'kind': 'new_artists', 'count': len(new_artist_keys), 'artist': by_artist[best]['name'],
                      'score': 58 + min(20, len(new_artist_keys) * 2)})

    # The song of the stretch.
    if d['top_songs'] and d['top_songs'][0].get('plays', 0) >= 2:
        found.append({'kind': 'top_song', 'song': d['top_songs'][0], 'plays': d['top_songs'][0]['plays'], 'score': 62})

    # On repeat in a single day.
    if d['repeat'] and d['repeat']['plays'] >= 3:
        found.append({'kind': 'repeat', 'song': d['repeat'], 'plays': d['repeat']['plays'], 'score': 66})

    # Faithful to one artist.
    if d['top_artists'] and d['artists'] >= 2:
        share = d['top_artists'][0]['seconds'] / total
        if share >= 0.3:
            a = d['top_artists'][0]
            found.append({'kind': 'loyal', 'artist': a['name'], 'id': a['id'], 'cover': a['cover'],
                          'percent': round(share * 100), 'score': 50 + round(share * 20)})

    # When it is played.
    night = sum(d['hours'][h] for h in (22, 23, 0, 1, 2, 3, 4)) / total
    morning = sum(d['hours'][h] for h in (5, 6, 7, 8, 9)) / total
    if night >= 0.4:
        found.append({'kind': 'night', 'percent': round(night * 100), 'score': 46})
    elif morning >= 0.35:
        found.append({'kind': 'morning', 'percent': round(morning * 100), 'score': 46})

    # A little of everything.
    if d['songs'] >= _VARIETY[period]:
        found.append({'kind': 'variety', 'songs': d['songs'], 'artists': d['artists'], 'score': 44})

    # Always something to say, however quiet the stretch.
    found.append({'kind': 'minutes', 'minutes': round(total / 60), 'score': 10})
    found.sort(key=lambda f: -f['score'])
    return found[:8]


def glance(now: Optional[float] = None, week_start: int = 0) -> dict[str, Any]:
    """Today, this week, this month and this year at a glance: for Home's
    "Your music lately", each with its minutes, its bars and its best moments."""

    now = time.time() if now is None else now
    with _lock:
        _load()
        plays = list(_plays)
        songs = dict(_songs)
    out: dict[str, Any] = {}
    # A run of days, a record, a comeback or a lifetime mark is the same news
    # whichever stretch tells it: the first to have it says it, the others
    # leave it and say something else.
    said: set[str] = set()
    once = {'streak', 'record_day', 'every_day', 'comeback', 'repeat', 'milestone_hours', 'milestone_plays'}
    for period in PERIODS:
        d = _story(plays, songs, period, None, now, 0, week_start)
        moments = [f for f in d['insights'] if f['kind'] not in said]
        said |= {f['kind'] for f in moments[:3] if f['kind'] in once}
        out[period] = {
            'seconds': d['seconds'],
            'plays': d['plays'],
            'chart': d['chart'],
            'top_song': d['top_songs'][0] if d['top_songs'] else None,
            'top_artist': d['top_artists'][0] if d['top_artists'] else None,
            'insights': moments[:3],
            'start': d['start'],
        }
    return out
