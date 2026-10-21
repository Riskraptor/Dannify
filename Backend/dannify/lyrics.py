"""Lyrics providers used to enrich downloaded audio files and the live player.

Primary provider is ``lrclib`` (https://lrclib.net) with both its exact
``/get`` and fuzzy ``/search`` endpoints. The fetcher iterates over every
configured provider and, within lrclib, over multiple strategies: so a
single timeout or miss never sinks the whole lookup. A shared, pooled HTTP
session keeps concurrent lyric requests fast.
"""

from __future__ import annotations

import re as _re
from dataclasses import dataclass
from typing import Any, Callable, Optional

import requests
from loguru import logger
from requests.adapters import HTTPAdapter

LRCLIB_BASE = 'https://lrclib.net/api'
# lrclib asks clients to identify themselves; sending the Lrclib-Client header
# (and a matching User-Agent) improves reliability and rate-limit treatment.
_CLIENT_ID = 'Dannify/3.1 (https://github.com/Riskraptor/Dannify)'

SUPPORTED_PROVIDERS = {'lrclib'}

# Shared, connection-pooled session so many simultaneous lyric lookups reuse
# sockets instead of paying TLS setup each time.
_session = requests.Session()
_session.headers.update({
    'User-Agent': _CLIENT_ID,
    'Lrclib-Client': _CLIENT_ID,
})
_adapter = HTTPAdapter(pool_connections=20, pool_maxsize=40, max_retries=0)
_session.mount('https://', _adapter)
_session.mount('http://', _adapter)

# (connect, read) timeout. Queries run in parallel now, so we can afford a
# tighter read deadline: the fastest successful query wins, and results are
# cached (memory + disk) so the wait is paid at most once per song, ever.
_TIMEOUT = (4.0, 8.0)


@dataclass
class Lyrics:
    plain: Optional[str] = None
    synced: Optional[str] = None
    # What a version is, for the picker: its length, whether it is timed word
    # by word, how many lines. Only versions carry it; it is not persisted.
    about: Optional[dict] = None

    def has_any(self) -> bool:
        return bool(self.plain) or bool(self.synced)


# Small in-memory cache so repeated lookups for the same track are instant and
# we don't hammer lrclib (which is rate-limited and sometimes slow).
import json as _json
import threading as _threading
from collections import OrderedDict as _OrderedDict
from pathlib import Path as _Path

_lyrics_cache: "_OrderedDict[str, Optional[Lyrics]]" = _OrderedDict()
_lyrics_cache_lock = _threading.Lock()
# One write of the cache file at a time.
_persist_lock = _threading.Lock()
# When a lookup last failed to reach the source at all, as opposed to reaching
# it and hearing there are no lyrics. A time rather than a flag because the
# lookups run on a pool of their own threads.
_last_trouble = 0.0


def _mark_trouble() -> None:
    global _last_trouble
    import time as _time

    _last_trouble = _time.monotonic()
_LYRICS_CACHE_MAX = 4096
_cache_path: Optional[_Path] = None


def init_cache(database_dir) -> None:
    """Load the persistent lyrics cache so the lrclib cost is paid once *ever*
    (across restarts), not once per session. Misses are cached too."""

    global _cache_path
    _cache_path = _Path(database_dir) / 'lyrics_cache.json'
    try:
        if _cache_path.exists():
            raw = _json.loads(_cache_path.read_text(encoding='utf-8'))
            with _lyrics_cache_lock:
                for k, v in raw.items():
                    _lyrics_cache[k] = (
                        None
                        if v is None
                        else Lyrics(plain=v.get('plain'), synced=v.get('synced'))
                    )
            logger.info('Lyrics cache loaded ({} entries)', len(_lyrics_cache))
    except Exception:
        logger.opt(exception=True).debug('Could not load lyrics cache')


def _persist_cache() -> None:
    if _cache_path is None:
        return

    def _run() -> None:
        # One writer at a time, and the file replaced whole. Two saves at once
        # (a few downloads fetching lyrics together) used to write into the
        # same file side by side, leaving the tail of the longer one behind the
        # shorter: the next start read that as broken JSON and began with an
        # empty cache.
        try:
            with _persist_lock:
                with _lyrics_cache_lock:
                    snapshot = {
                        k: (None if v is None else {'plain': v.plain, 'synced': v.synced})
                        for k, v in _lyrics_cache.items()
                    }
                part = _cache_path.with_name(_cache_path.name + '.part')
                part.write_text(_json.dumps(snapshot), encoding='utf-8')
                import os as _os

                _os.replace(part, _cache_path)
        except Exception:
            logger.opt(exception=True).debug('Could not persist lyrics cache')

    # Write off the request path so persistence never adds latency.
    _threading.Thread(target=_run, daemon=True).start()


def _base_key(song: dict[str, Any]) -> str:
    artists = song.get('artists') or []
    a = (artists[0] if artists else '').strip().lower()
    return f"{a}|{(song.get('name') or '').strip().lower()}"


def _cache_key(song: dict[str, Any]) -> str:
    """Artist, title and, when known, length: two cuts of a song with one
    name (a radio edit, the album take) were kept as one, so the lyrics and
    versions found for the first were shown, and ranked, for the second."""

    base = _base_key(song)
    try:
        seconds = int(float(song.get('duration') or 0))
    except (TypeError, ValueError):
        seconds = 0
    return f'{base}|{seconds}' if seconds > 0 else base


def _same_song(key: str, base: str) -> bool:
    return key == base or key.startswith(base + '|')


def clear_cache(song: Optional[dict[str, Any]] = None) -> None:
    """Drop cached lyrics so the next lookup re-queries the source.

    With *song* clears just that track; otherwise clears everything. Used by
    the "refresh lyrics" button when the source may have updated.
    """

    with _lyrics_cache_lock:
        if song is not None:
            # Every length of it: a song published is asked for by name.
            base = _base_key(song)
            for cache in (_lyrics_cache, _versions_cache):
                for key in [k for k in cache if _same_song(k, base)]:
                    cache.pop(key, None)
        else:
            _lyrics_cache.clear()
            _versions_cache.clear()
    _persist_cache()


def fetch(song: dict[str, Any], providers: list[str]) -> Optional[Lyrics]:
    """Try each configured provider in order; return the first hit.

    Providers are isolated: an exception or timeout in one is logged compactly
    and the next provider is attempted, so the lookup degrades gracefully.
    Results (including misses) are cached so the cost is paid at most once.
    """

    key = _cache_key(song)
    base = _base_key(song)
    if base.strip('|'):
        with _lyrics_cache_lock:
            # What was kept before lengths were part of the key still counts,
            # so nothing found earlier is looked up again, or lost offline.
            for k in (key, base):
                if k in _lyrics_cache:
                    _lyrics_cache.move_to_end(k)
                    return _lyrics_cache[k]

    import time as _time

    started = _time.monotonic()
    result = _fetch_uncached(song, providers)

    # "No lyrics" is only worth remembering when the source said so. One that
    # could not be reached (offline, a timeout, the service having a bad
    # minute) used to be written down as a miss, for good, across restarts.
    if result is None and _last_trouble >= started:
        return None

    if base.strip('|'):
        with _lyrics_cache_lock:
            _lyrics_cache[key] = result
            _lyrics_cache.move_to_end(key)
            while len(_lyrics_cache) > _LYRICS_CACHE_MAX:
                _lyrics_cache.popitem(last=False)
        _persist_cache()  # async, off the request path
    return result


def _fetch_uncached(
    song: dict[str, Any], providers: list[str]
) -> Optional[Lyrics]:
    tried = 0
    for name in providers or []:
        fn = _PROVIDER_FNS.get(name)
        if fn is None:
            continue
        tried += 1
        try:
            result = fn(song)
        except Exception as exc:
            logger.warning(
                'lyrics provider {!r} error: {}', name, exc.__class__.__name__
            )
            _mark_trouble()
            continue
        if result and result.has_any():
            return result
    # Safety net: if nothing was configured/usable, still try lrclib once.
    if tried == 0 and 'lrclib' in SUPPORTED_PROVIDERS:
        try:
            return _fetch_lrclib(song)
        except Exception:
            return None
    return None


def _get_json(url: str, params: dict[str, Any]) -> Optional[Any]:
    """Single pooled GET returning parsed JSON, or ``None`` on any failure."""

    try:
        resp = _session.get(url, params=params, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        logger.debug('lyrics GET {} failed: {}', url, exc.__class__.__name__)
        _mark_trouble()
        return None
    if resp.status_code != 200:
        if resp.status_code == 429 or resp.status_code >= 500:
            _mark_trouble()
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def _lyrics_from_row(row: dict[str, Any]) -> Optional[Lyrics]:
    plain = (row.get('plainLyrics') or '').strip() or None
    synced = (row.get('syncedLyrics') or '').strip() or None
    if not plain and not synced:
        return None
    return Lyrics(plain=plain, synced=synced)


def _fetch_lrclib(song: dict[str, Any]) -> Optional[Lyrics]:
    """lrclib lookup: exact ``/get`` and scored fuzzy ``/search`` run **in
    parallel**, then the best result is chosen: halving worst-case latency."""

    import concurrent.futures as _cf

    artists = song.get('artists') or []
    title = (song.get('name') or '').strip()
    if not title or not artists:
        return None
    artist = artists[0]
    duration = int(song.get('duration') or 0)
    album = (song.get('album_name') or '').strip()

    get_params: dict[str, Any] = {'track_name': title, 'artist_name': artist}
    if album:
        get_params['album_name'] = album
    if duration:
        get_params['duration'] = duration

    # Fire /get and the multi-query /search concurrently.
    with _cf.ThreadPoolExecutor(max_workers=2) as ex:
        f_get = ex.submit(_get_json, f'{LRCLIB_BASE}/get', get_params)
        f_search = ex.submit(_fetch_lrclib_search, title, artist, duration, album)
        data = f_get.result()
        scored = f_search.result()

    # Prefer a synced /get hit (most authoritative), else the scored search.
    if isinstance(data, dict) and (data.get('syncedLyrics') or '').strip():
        hit = _lyrics_from_row(data)
        if hit:
            return hit
    if scored is not None and scored.synced:
        return scored
    # Fall back to any plain lyrics.
    if isinstance(data, dict):
        hit = _lyrics_from_row(data)
        if hit:
            return hit
    return scored


def _norm(text: str) -> str:
    # Letters in any script. The a-to-z version reduced a Japanese or Russian
    # title to nothing, so no search result could ever match one.
    from .library import fold  # noqa: PLC0415

    return fold(text)


# Canonicalize common spelling/typo variants so titles like "Never To Late"
# and "Never Too Late" compare equal.
_TITLE_SYNONYMS = {
    'too': 'to',
    'and': 'n',
    '&': 'n',
    'ur': 'your',
    'u': 'you',
    'cant': 'cant',
    'wont': 'wont',
}


def _canon_title(text: str) -> str:
    words = _norm(text).split()
    out = [_TITLE_SYNONYMS.get(w, w) for w in words]
    return ' '.join(out)


def _title_similarity(a: str, b: str) -> float:
    """Token-overlap ratio (0..1) of two canonicalized titles."""

    ta = set(_canon_title(a).split())
    tb = set(_canon_title(b).split())
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / max(len(ta), len(tb))


def _alt_title(title: str) -> str:
    """A common-typo-corrected variant to widen the lrclib search.

    Most usefully fixes the frequent "to" → "too" miswrite (e.g. a downloaded
    file titled "Never To Late" should also search for "Never Too Late").
    """

    words = title.split()
    out = []
    for w in words:
        lw = w.lower().strip('.,!?')
        if lw == 'to':
            out.append('Too')
        elif lw == 'u':
            out.append('You')
        elif lw == 'ur':
            out.append('Your')
        else:
            out.append(w)
    return ' '.join(out)


# What a title says about *which* recording it is. A remix, a live take or a
# sped-up upload has the same words at other times, so one is only a good
# match for the same kind of recording.
_VERSION_TAGS = {
    'remix': ('remix', 'rmx', 'mix'),
    'live': ('live', 'concert', 'session', 'sessions'),
    'acoustic': ('acoustic', 'unplugged', 'stripped'),
    'instrumental': ('instrumental', 'karaoke', 'backing track'),
    'fast': ('sped up', 'speed up', 'nightcore', 'fast'),
    'slow': ('slowed', 'reverb', 'chopped'),
    'extended': ('extended', 'long version'),
    'cover': ('cover', 'tribute'),
    'demo': ('demo',),
}
# Asides that name nobody new and change nothing about the words.
_ASIDE = _re.compile(
    r'\s*[\(\[](?:feat\.?|ft\.?|featuring|with|prod\.?|from|official|audio|lyrics?|lyric video|'
    r'video|visuali[sz]er|remaster(?:ed)?(?: \d{4})?|\d{4} remaster(?:ed)?|explicit|clean|'
    r'radio edit|single version|album version|original mix|mono|stereo)[^\)\]]*[\)\]]',
    _re.I,
)
_TRAILING_FEAT = _re.compile(r'\s+(?:feat\.?|ft\.?|featuring)\s+.*$', _re.I)
_DASH_ASIDE = _re.compile(
    r'\s+-\s+(?:remaster(?:ed)?(?: \d{4})?|\d{4} remaster(?:ed)?|radio edit|single version|'
    r'album version|original mix|mono|stereo|explicit|clean)\s*$',
    _re.I,
)


def _base_title(text: str) -> str:
    """The title without who it features or how it was mastered."""

    t = str(text or '')
    for _ in range(3):
        t2 = _DASH_ASIDE.sub('', _ASIDE.sub('', _TRAILING_FEAT.sub('', t)))
        if t2 == t:
            break
        t = t2
    return t.strip() or str(text or '').strip()


def _tags(text: str) -> set[str]:
    folded = ' ' + _norm(text) + ' '
    found = set()
    for tag, words in _VERSION_TAGS.items():
        if any(f' {w} ' in folded for w in words):
            found.add(tag)
    return found


_STAMP = _re.compile(r'\[(\d+):(\d+(?:\.\d+)?)\]')


def _synced_shape(synced: str) -> tuple[int, float, bool, int]:
    """(lines, last time, timed word by word, times that go backwards)."""

    times = [int(m.group(1)) * 60 + float(m.group(2)) for m in _STAMP.finditer(synced or '')]
    back = sum(1 for a, b in zip(times, times[1:]) if b + 0.05 < a)
    return len(times), (max(times) if times else 0.0), '<' in (synced or '') and bool(
        _re.search(r'<\d+:\d+(?:\.\d+)?>', synced or '')
    ), back


def _artist_matches(query_artist: str, row_artist: str) -> bool:
    """True if the queried artist appears in the row's artist field.

    Handles collaborations like "Marioo/Bien" or "Bien & Marioo" by checking
    token containment in both directions.
    """

    qa = _norm(query_artist)
    ra = _norm(row_artist)
    if not qa or not ra:
        return False
    if qa == ra:
        return True
    # token sets: every word of the (shorter) primary artist should appear.
    q_tokens = set(qa.split())
    r_tokens = set(ra.split())
    if q_tokens and q_tokens.issubset(r_tokens):
        return True
    if r_tokens and r_tokens.issubset(q_tokens):
        return True
    return False


def _score_row(
    row: dict[str, Any],
    want_title: str,
    want_artist: str,
    want_duration: int,
    want_album: str = '',
) -> float:
    """Lower is better. ``inf`` means reject (wrong artist or title).

    What counts, most first: lyrics timed at all; the same kind of recording
    (a remix or a live take has the words at other times); the same length;
    timing that fits inside the song; the same title once who it features
    is set aside; word-by-word timing; the same album.
    """

    row_title = row.get('trackName') or ''
    rt = _norm(row_title)
    ra = row.get('artistName') or ''
    if not rt:
        return float('inf')
    wt = _norm(want_title)
    # Title match: exact, containment, OR fuzzy (handles "to"/"too" typos,
    # "&"/"and", punctuation). Accept when token-overlap is strong. Compared
    # without "(feat. ...)" too: "Girl Next Door (feat. Tiwa Savage)" is
    # "Girl Next Door".
    wb, rb = _norm(_base_title(want_title)), _norm(_base_title(row_title))
    sim = max(_title_similarity(want_title, row_title), _title_similarity(wb, rb))
    title_ok = rt == wt or wb == rb or wt in rt or rt in wt or sim >= 0.7
    if not title_ok:
        return float('inf')
    # Artist must match: this is what stops "different song, same title".
    if not _artist_matches(want_artist, ra):
        return float('inf')

    score = 0.0
    if rt != wt and wb != rb:
        score += 5 * (1.0 - sim)  # smaller penalty the closer the titles are
    # A different kind of recording: a remix found for the original is
    # worse than one for which the song is the remix.
    want_tags, row_tags = _tags(want_title), _tags(row_title)
    score += 30 * len(row_tags - want_tags) + 15 * len(want_tags - row_tags)
    # Duration proximity (the strongest version discriminator), and more so
    # past ten seconds, where it is another cut of the song.
    rd = row.get('duration') or 0
    if want_duration and rd:
        diff = abs(float(rd) - float(want_duration))
        score += diff + (20 if diff > 10 else 0)
    synced = (row.get('syncedLyrics') or '').strip()
    if not synced:
        # Strongly prefer rows that actually have synced lyrics.
        score += 1000
    else:
        lines, last, words, back = _synced_shape(synced)
        if want_duration and last > float(want_duration) + 8:
            score += 60  # its words go on after the song has ended
        if lines < 3:
            score += 15
        score += 2 * back
        if words:
            score -= 2
    if want_album and _norm(row.get('albumName')) == _norm(want_album):
        score -= 1.5
    return score


def _gather_candidates(title: str, artist: str) -> list[dict[str, Any]]:
    """Collect lrclib search candidates from several query variants: run in
    **parallel** so the total latency is one round-trip, not the sum of all."""

    import concurrent.futures as _cf

    primary = artist.split(',')[0].split('&')[0].split('/')[0].strip()
    # Build a typo-tolerant title variant ("never to late" -> "never too late").
    alt_title = _alt_title(title)
    queries: list[dict[str, Any]] = [
        {'track_name': title, 'artist_name': artist},
        {'q': f'{title} {primary or artist}'},
        # Search by artist alone: returns their whole catalogue, surfacing the
        # correctly-spelled / synced upload even when our title has a typo.
        {'artist_name': primary or artist},
        {'q': title},
    ]
    if alt_title and alt_title != title:
        queries.insert(1, {'track_name': alt_title, 'artist_name': artist})
    if primary and primary.casefold() != artist.casefold():
        queries.insert(1, {'track_name': title, 'artist_name': primary})

    candidates: list[dict[str, Any]] = []
    seen_ids: set[Any] = set()
    with _cf.ThreadPoolExecutor(max_workers=len(queries)) as ex:
        results = list(
            ex.map(
                lambda p: _get_json(f'{LRCLIB_BASE}/search', p), queries
            )
        )
    for rows in results:
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            rid = row.get('id') or (
                row.get('trackName'),
                row.get('artistName'),
                row.get('duration'),
            )
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            candidates.append(row)
    return candidates


def _fetch_lrclib_search(
    title: str, artist: str, duration: int = 0, album: str = ''
) -> Optional[Lyrics]:
    candidates = _gather_candidates(title, artist)
    if not candidates:
        return None

    scored = []
    for row in candidates:
        s = _score_row(row, title, artist, duration, album)
        if s != float('inf'):
            scored.append((s, row))
    if not scored:
        logger.debug(
            'lrclib: no acceptable match for {!r} by {!r} among {} candidates',
            title,
            artist,
            len(candidates),
        )
        return None
    scored.sort(key=lambda x: x[0])
    best = scored[0][1]
    logger.debug(
        'lrclib match: {!r} by {!r} (dur {}, {}) for query {!r}/{!r} dur {}',
        best.get('trackName'),
        best.get('artistName'),
        best.get('duration'),
        'synced' if (best.get('syncedLyrics') or '').strip() else 'plain',
        title,
        artist,
        duration,
    )
    return _lyrics_from_row(best)


_PROVIDER_FNS: dict[str, Callable[[dict[str, Any]], Optional[Lyrics]]] = {
    'lrclib': _fetch_lrclib,
}


def fetch_all_versions(song: dict[str, Any]) -> list[Lyrics]:
    """Return every distinct **synced** lyric version for *song*, best first.

    lrclib often has several synced uploads of the same track with slightly
    different line timings. We return them all (de-duplicated by content) so
    the UI can let the user cycle to whichever syncs best.
    """

    artists = song.get('artists') or []
    title = (song.get('name') or '').strip()
    if not title or not artists:
        return []
    artist = artists[0]
    duration = int(song.get('duration') or 0)
    album = (song.get('album_name') or '').strip()

    candidates = _gather_candidates(title, artist)
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in candidates:
        if not (row.get('syncedLyrics') or '').strip():
            continue
        s = _score_row(row, title, artist, duration, album)
        if s != float('inf'):
            scored.append((s, row))
    scored.sort(key=lambda x: x[0])

    versions: list[Lyrics] = []
    seen_text: set[str] = set()
    for _s, row in scored:
        synced = (row.get('syncedLyrics') or '').strip()
        # De-dupe only EXACT duplicates (same timestamps + text). Versions that
        # share words but differ in timing are kept: that's the whole point of
        # the version switcher (small per-line second differences).
        sig = synced
        if sig in seen_text:
            continue
        seen_text.add(sig)
        lines, _last, words, _back = _synced_shape(synced)
        length = row.get('duration') or 0
        versions.append(
            Lyrics(
                plain=(row.get('plainLyrics') or '').strip() or None,
                synced=synced,
                about={
                    'words': words,
                    'lines': lines,
                    'length': round(float(length)) if length else None,
                    'diff': round(float(length) - duration) if length and duration else None,
                },
            )
        )
        if len(versions) >= 6:  # cap. Nobody needs more than a handful
            break
    return versions


# ---------------------------------------------------------------------------
# Structured helpers used by the live lyrics API + the player UI.
# ---------------------------------------------------------------------------

_LRC_LINE = _re.compile(r'\[(\d+):(\d+(?:\.\d+)?)\]')
# Word times from "enhanced" LRC (<00:12.34>), the time each word is sung.
_LRC_WORD = _re.compile(r'<(\d+):(\d+(?:\.\d+)?)>')


def _seconds(m) -> float:
    return int(m.group(1)) * 60 + float(m.group(2))


def _words(body: str, start: float) -> tuple[str, list[dict[str, Any]], Optional[float]]:
    """The words of an enhanced line, each with when it is sung.

    Returns the plain text, the words (``[{'time', 'text'}]``, the text keeping
    its spaces so they join back into the line) and when the last one ends,
    or ``None`` when the file does not say. A line without word times gives
    no words.
    """

    stamps = list(_LRC_WORD.finditer(body))
    text = ' '.join(_LRC_WORD.sub('', body).split())
    if not stamps:
        return text, [], None
    words: list[dict[str, Any]] = []
    lead = body[: stamps[0].start()]
    if lead.strip():
        words.append({'time': start, 'text': lead})
    end: Optional[float] = None
    for i, m in enumerate(stamps):
        stop = stamps[i + 1].start() if i + 1 < len(stamps) else len(body)
        piece = body[m.end():stop]
        if piece.strip():
            words.append({'time': _seconds(m), 'text': piece})
        elif i + 1 == len(stamps):
            # A closing stamp with nothing after it: when the line ends.
            end = _seconds(m)
        elif words:
            words[-1]['text'] += piece
    # Spaces as the line shows them: one between words, none at either end.
    for w in words:
        w['text'] = _re.sub(r'\s+', ' ', w['text'])
    if words:
        words[0]['text'] = words[0]['text'].lstrip()
        words[-1]['text'] = words[-1]['text'].rstrip()
    times = [w['time'] for w in words]
    if any(b < a for a, b in zip(times, times[1:])):
        return text, [], None  # out of order: the file is not to be trusted
    return text, words, end


def parse_lrc(synced: Optional[str]) -> list[dict[str, Any]]:
    """Parse an LRC string into ``[{'time': float_seconds, 'text': str}, ...]``.

    Multiple timestamps on a single line are expanded. Metadata-only lines
    (``[ar:...]`` etc.) are skipped. Output is sorted by time.

    A line with word times (enhanced LRC) also carries ``words``, each with
    the time it is sung, and ``end`` when the file says when the line ends.
    """

    if not synced:
        return []
    out: list[dict[str, Any]] = []
    for raw_line in synced.splitlines():
        stamps = list(_LRC_LINE.finditer(raw_line))
        if not stamps:
            continue
        body = _LRC_LINE.sub('', raw_line).strip()
        first = _seconds(stamps[0])
        text, words, end = _words(body, first)
        for m in stamps:
            time = _seconds(m)
            row: dict[str, Any] = {'time': time, 'text': text}
            if words:
                # Word times are written for the first time the line is
                # sung; a chorus stamped again is sung the same way later.
                shift = time - first
                row['words'] = [
                    {'time': round(w['time'] + shift, 3), 'text': w['text']} for w in words
                ]
                if end is not None:
                    row['end'] = round(end + shift, 3)
            out.append(row)
    out.sort(key=lambda r: r['time'])
    return out


def fetch_structured(
    song: dict[str, Any], providers: Optional[list[str]] = None
) -> dict[str, Any]:
    """Return ``{'synced': [...], 'plain': str|None, 'has': bool}`` for a song.

    Live lookup against lrclib (the only implemented provider). Used by the
    streaming player so lyrics work even when nothing is downloaded.
    """

    result = fetch(song, providers or ['lrclib'])
    if result is None:
        return {'synced': [], 'plain': None, 'has': False}
    synced_lines = parse_lrc(result.synced)
    plain = result.plain
    if not plain and result.synced:
        plain = '\n'.join(
            line['text'] for line in synced_lines if line['text']
        ) or None
    return {
        'synced': synced_lines,
        'plain': plain,
        'has': bool(synced_lines or plain),
    }


_versions_cache: "_OrderedDict[str, list[Lyrics]]" = _OrderedDict()


def _versions_of(song: dict[str, Any]) -> list[Lyrics]:
    """Every synced version of *song*, best first; one lookup per song."""

    key = _cache_key(song)
    named = bool(_base_key(song).strip('|'))
    with _lyrics_cache_lock:
        cached = _versions_cache.get(key) if named else None
    if cached is None:
        cached = fetch_all_versions(song)
        if named:
            with _lyrics_cache_lock:
                _versions_cache[key] = cached
                _versions_cache.move_to_end(key)
                while len(_versions_cache) > 512:
                    _versions_cache.popitem(last=False)
    return cached


def version_text(song: dict[str, Any], index: int) -> Optional[str]:
    """Version *index*'s own LRC text, to keep beside a saved song."""

    versions = [v for v in _versions_of(song) if parse_lrc(v.synced)]
    if 0 <= index < len(versions):
        return versions[index].synced
    return None


def same_words(a: Optional[str], b: Optional[str]) -> bool:
    """Whether two LRC texts are the same lyrics, timed the same way."""

    def norm(text: Optional[str]) -> list[tuple[float, str]]:
        return [(round(l['time'], 1), _norm(l['text'])) for l in parse_lrc(text)]

    na, nb = norm(a), norm(b)
    return bool(na) and na == nb


def fingerprint(lines: Any) -> str:
    """A short mark of one version's words and timing, so a choice can be
    found again wherever that version lands in the list next time (the list
    is re-ranked, and lrclib gains uploads). Takes parsed lines or LRC text."""

    import hashlib  # noqa: PLC0415

    if isinstance(lines, str) or lines is None:
        lines = parse_lrc(lines)
    body = '\n'.join(f"{round(float(l['time']), 1)}|{_norm(l['text'])}" for l in lines)
    if not body:
        return ''
    return hashlib.sha1(body.encode('utf-8')).hexdigest()[:16]


def fetch_versions_structured(song: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all synced versions as ``[{synced:[...], plain, has}, ...]``.

    Cached in memory so the multi-query lrclib sweep is paid once per song.
    """

    cached = _versions_of(song)
    out: list[dict[str, Any]] = []
    for ver in cached:
        lines = parse_lrc(ver.synced)
        if not lines:
            continue
        plain = ver.plain or (
            '\n'.join(l['text'] for l in lines if l['text']) or None
        )
        out.append({
            'synced': lines, 'plain': plain, 'has': True, 'about': ver.about or {},
            'pick': fingerprint(lines),
        })
    return out
