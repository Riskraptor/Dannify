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
_CLIENT_ID = 'Dannify/3.1 (https://github.com/DANIELMWENDWA9451/Dannify)'

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


def _cache_key(song: dict[str, Any]) -> str:
    artists = song.get('artists') or []
    a = (artists[0] if artists else '').strip().lower()
    return f"{a}|{(song.get('name') or '').strip().lower()}"


def clear_cache(song: Optional[dict[str, Any]] = None) -> None:
    """Drop cached lyrics so the next lookup re-queries the source.

    With *song* clears just that track; otherwise clears everything. Used by
    the "refresh lyrics" button when the source may have updated.
    """

    with _lyrics_cache_lock:
        if song is not None:
            _lyrics_cache.pop(_cache_key(song), None)
            _versions_cache.pop(_cache_key(song), None)
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
    if key.strip('|'):
        with _lyrics_cache_lock:
            if key in _lyrics_cache:
                _lyrics_cache.move_to_end(key)
                return _lyrics_cache[key]

    import time as _time

    started = _time.monotonic()
    result = _fetch_uncached(song, providers)

    # "No lyrics" is only worth remembering when the source said so. One that
    # could not be reached (offline, a timeout, the service having a bad
    # minute) used to be written down as a miss, for good, across restarts.
    if result is None and _last_trouble >= started:
        return None

    if key.strip('|'):
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
        f_search = ex.submit(_fetch_lrclib_search, title, artist, duration)
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
) -> float:
    """Lower is better. ``inf`` means reject (wrong artist or title)."""

    rt = _norm(row.get('trackName'))
    ra = row.get('artistName') or ''
    if not rt:
        return float('inf')
    wt = _norm(want_title)
    # Title match: exact, containment, OR fuzzy (handles "to"/"too" typos,
    # "&"/"and", punctuation). Accept when token-overlap is strong.
    sim = _title_similarity(want_title, row.get('trackName') or '')
    title_ok = rt == wt or wt in rt or rt in wt or sim >= 0.7
    if not title_ok:
        return float('inf')
    # Artist must match: this is what stops "different song, same title".
    if not _artist_matches(want_artist, ra):
        return float('inf')

    score = 0.0
    if rt != wt:
        score += 5 * (1.0 - sim)  # smaller penalty the closer the titles are
    # Duration proximity (the strongest version discriminator).
    rd = row.get('duration') or 0
    if want_duration and rd:
        score += abs(float(rd) - float(want_duration))
    # Strongly prefer rows that actually have synced lyrics.
    if not (row.get('syncedLyrics') or '').strip():
        score += 1000
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
    title: str, artist: str, duration: int = 0
) -> Optional[Lyrics]:
    candidates = _gather_candidates(title, artist)
    if not candidates:
        return None

    scored = []
    for row in candidates:
        s = _score_row(row, title, artist, duration)
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

    candidates = _gather_candidates(title, artist)
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in candidates:
        if not (row.get('syncedLyrics') or '').strip():
            continue
        s = _score_row(row, title, artist, duration)
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
        versions.append(
            Lyrics(
                plain=(row.get('plainLyrics') or '').strip() or None,
                synced=synced,
            )
        )
        if len(versions) >= 6:  # cap. Nobody needs more than a handful
            break
    return versions


# ---------------------------------------------------------------------------
# Structured helpers used by the live lyrics API + the player UI.
# ---------------------------------------------------------------------------

_LRC_LINE = _re.compile(r'\[(\d+):(\d+(?:\.\d+)?)\]')


def parse_lrc(synced: Optional[str]) -> list[dict[str, Any]]:
    """Parse an LRC string into ``[{'time': float_seconds, 'text': str}, ...]``.

    Multiple timestamps on a single line are expanded. Metadata-only lines
    (``[ar:...]`` etc.) are skipped. Output is sorted by time.
    """

    if not synced:
        return []
    out: list[dict[str, Any]] = []
    for raw_line in synced.splitlines():
        stamps = list(_LRC_LINE.finditer(raw_line))
        if not stamps:
            continue
        text = _LRC_LINE.sub('', raw_line).strip()
        for m in stamps:
            minutes = int(m.group(1))
            seconds = float(m.group(2))
            out.append({'time': minutes * 60 + seconds, 'text': text})
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


def fetch_versions_structured(song: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all synced versions as ``[{synced:[...], plain, has}, ...]``.

    Cached in memory so the multi-query lrclib sweep is paid once per song.
    """

    key = _cache_key(song)
    with _lyrics_cache_lock:
        cached = _versions_cache.get(key) if key.strip('|') else None
    if cached is None:
        cached = fetch_all_versions(song)
        if key.strip('|'):
            with _lyrics_cache_lock:
                _versions_cache[key] = cached
                _versions_cache.move_to_end(key)
                while len(_versions_cache) > 512:
                    _versions_cache.popitem(last=False)

    out: list[dict[str, Any]] = []
    for ver in cached:
        lines = parse_lrc(ver.synced)
        if not lines:
            continue
        plain = ver.plain or (
            '\n'.join(l['text'] for l in lines if l['text']) or None
        )
        out.append({'synced': lines, 'plain': plain, 'has': True})
    return out
