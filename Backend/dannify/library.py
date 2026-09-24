"""Offline library indexing: artists, albums, tracks, and fuzzy search.

Reads embedded tags from the downloaded audio files (via mutagen) and
builds a cached, grouped view of the library. The cache is invalidated
whenever the download directory's listing changes (file count or latest
mtime), so newly downloaded tracks show up without a restart.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Optional

from loguru import logger
from mutagen import File as MutagenFile

# .dnf is a sealed container holding one of the others. Everything that walks
# the music folder has to count it as a track, or a sealed library looks empty.
_AUDIO_EXTS = {'.mp3', '.m4a', '.flac', '.ogg', '.wav', '.aac', '.opus', '.dnf'}

_lock = threading.Lock()
_cache: dict[str, Any] = {}
_cache_signature: Optional[tuple[int, float]] = None


def _signature(base: Path) -> tuple[int, float]:
    count = 0
    latest = 0.0
    for p in base.rglob('*'):
        if p.is_file() and p.suffix.lower() in _AUDIO_EXTS:
            count += 1
            try:
                latest = max(latest, p.stat().st_mtime)
            except OSError:
                pass
    return count, latest


def _first(tag: Any) -> str:
    if tag is None:
        return ''
    if isinstance(tag, (list, tuple)):
        return str(tag[0]) if tag else ''
    return str(tag)


def _split_artists(value: str) -> list[str]:
    """Split an ID3 multi-artist string into individual names.

    ID3v2.3 joins multiple artists with ``/``; we also handle ``;``, ``,``,
    and the common ``feat.`` / ``&`` separators so collaborators don't create
    bogus ``A/B`` artist folders.
    """

    if not value:
        return []
    import re as _re

    parts = _re.split(r'\s*(?:/|;|,|&|\bfeat\.?\b|\bft\.?\b|\bx\b)\s*', value, flags=_re.IGNORECASE)
    seen: list[str] = []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.append(p)
    return seen


def _read_tags(path: Path) -> dict[str, Any]:
    """Best-effort tag read; falls back to the ``Artist - Title`` filename."""

    # A sealed container keeps its own header. mutagen would see noise.
    if path.suffix.lower() == '.dnf':
        from . import vault

        head = vault.read_header(path) or {}
        name = path.stem
        title = str(head.get('title') or '')
        raw = str(head.get('artist') or '')
        if not title and ' - ' in name:
            raw, title = name.split(' - ', 1)

        # The same shape the plain branch returns, key for key. It used to
        # hand back album_artist and no artist_display, and to put the whole
        # credit in as one name, so "Bensoul, Vic West" became an artist of
        # that name with one song, sitting in the sidebar next to the real
        # Bensoul. A container written by a current version carries the list
        # it was sealed with; an older one gets split the same way a plain
        # file does.
        stored = head.get('artists')
        if isinstance(stored, list) and stored:
            # Sealed by a version that recorded both, so 'artist' here is
            # already the primary the plain reader worked out, album artist
            # and all: "Bob Marley & The Wailers" rather than its first name.
            artists = [str(a) for a in stored if a]
            primary = raw or artists[0]
        else:
            # Older container: all there is to go on is one string, which is
            # what the filename gave. Split it the way a plain file is split.
            artists = _split_artists(raw)
            primary = artists[0] if artists else raw
        display = artists or ([primary] if primary else [])
        return {
            'title': title or name,
            'artist': primary or 'Unknown Artist',
            'artists': display,
            'artist_display': ', '.join(display) or primary or 'Unknown Artist',
            'album': str(head.get('album') or ''),
            'genre': str(head.get('genre') or ''),
            'duration': int(head.get('duration') or 0),
            'track_number': int(head.get('track_number') or 0),
            'video_id': str(head.get('video_id') or ''),
        }

    title = ''
    artist = ''
    album_artist = ''
    all_artists: list[str] = []
    album = ''
    genre = ''
    duration = 0
    track_number = 0
    video_id = ''
    try:
        audio = MutagenFile(str(path), easy=True)
        if audio is not None:
            tags = audio.tags or {}
            title = _first(tags.get('title'))
            album_artist = _first(tags.get('albumartist'))
            artist_raw = _first(tags.get('artist'))
            all_artists = _split_artists(artist_raw)
            album = _first(tags.get('album'))
            genre = _first(tags.get('genre'))
            tn = _first(tags.get('tracknumber'))
            if tn:
                try:
                    track_number = int(str(tn).split('/')[0])
                except ValueError:
                    track_number = 0
            if audio.info is not None:
                duration = int(getattr(audio.info, 'length', 0) or 0)
        # Pull DANNIFY_VIDEO_ID using the raw (non-easy) reader so the
        # mutagen ``easy`` interface's whitelist doesn't drop it.
        video_id = _read_video_id_tag(path) or ''
    except Exception:
        logger.opt(exception=True).debug('Tag read failed for {}', path)

    # Primary artist for grouping: prefer the clean album-artist, else the
    # first split artist, else the filename's "Artist - Title" prefix.
    primary = album_artist or (all_artists[0] if all_artists else '')

    if not title or not primary:
        stem = path.stem
        dash = stem.find(' - ')
        if dash > 0:
            if not primary:
                fname_artists = _split_artists(stem[:dash].strip())
                primary = fname_artists[0] if fname_artists else stem[:dash].strip()
                if not all_artists:
                    all_artists = fname_artists
            title = title or stem[dash + 3 :].strip()
        else:
            title = title or stem

    display_artists = all_artists or ([primary] if primary else [])
    return {
        'title': title or path.stem,
        'artist': primary or 'Unknown Artist',
        'artists': display_artists,
        'artist_display': ', '.join(display_artists) or primary or 'Unknown Artist',
        'album': album,
        'genre': genre,
        'duration': duration,
        'track_number': track_number,
        'video_id': video_id,
    }


_VIDEO_ID_RE = __import__('re').compile(r'^[A-Za-z0-9_-]{11}$')


def _read_video_id_tag(path: Path) -> str:
    """Return the stored YouTube videoId for *path*, or ''.

    Looks at the format-specific frame written by
    :func:`dannify.downloader.embed_video_id`. Cheap on a cache miss
    (a single mutagen file read shared with :func:`_read_tags`'s call).
    """

    try:
        from mutagen import File as _MF

        audio = _MF(str(path))
        if audio is None or audio.tags is None:
            return ''
        suffix = path.suffix.lower().lstrip('.')
        candidate = ''
        if suffix == 'mp3':
            for frame in audio.tags.getall('TXXX'):
                if getattr(frame, 'desc', '') == 'DANNIFY_VIDEO_ID':
                    txt = frame.text
                    candidate = (txt[0] if isinstance(txt, list) else str(txt)).strip()
                    break
        elif suffix in {'m4a', 'mp4', 'aac'}:
            raw = audio.tags.get('----:com.dannify:VIDEO_ID')
            if raw:
                first = raw[0]
                candidate = (
                    first.decode('utf-8', 'ignore')
                    if isinstance(first, (bytes, bytearray))
                    else str(first)
                ).strip()
        else:  # flac, ogg, opus → vorbis comments behave like a dict
            raw = audio.tags.get('DANNIFY_VIDEO_ID') or audio.tags.get(
                'dannify_video_id'
            )
            if raw:
                candidate = (
                    raw[0] if isinstance(raw, (list, tuple)) else str(raw)
                ).strip()
        return candidate if _VIDEO_ID_RE.match(candidate) else ''
    except Exception:
        return ''


def _norm_name(name: str) -> str:
    import re as _re

    return _re.sub(r'[^a-z0-9 ]+', '', name.casefold()).strip()


def _similar_token(a: str, b: str) -> bool:
    """True if two single tokens are near-identical (1-char typo tolerance)."""

    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) < 4 or len(b) < 4:
        return False
    # Levenshtein distance <= 1 (cheap bounded check).
    if len(a) == len(b):
        diffs = sum(1 for x, y in zip(a, b) if x != y)
        return diffs <= 1
    # one insertion/deletion
    short, long = (a, b) if len(a) < len(b) else (b, a)
    i = j = 0
    skips = 0
    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i += 1
            j += 1
        else:
            skips += 1
            j += 1
            if skips > 1:
                return False
    return True


def _same_artist(a: str, b: str) -> bool:
    """Decide whether two artist labels are the same act.

    Collapses prefix/superset variants ("Stephen Kasolo" vs "Stephen Kasolo
    Kitole") and tolerates a single-character typo in the differing trailing
    token ("Kitelo" vs "Kitole").
    """

    ta = _norm_name(a).split()
    tb = _norm_name(b).split()
    if not ta or not tb:
        return False
    short, long = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    # Every token of the shorter name must match the aligned token of the
    # longer one (allowing a one-char typo on the last compared token).
    for i, tok in enumerate(short):
        other = long[i]
        if tok == other:
            continue
        if i == len(short) - 1 and _similar_token(tok, other):
            continue
        return False
    return True


def _canonicalize_artists(names: list[str]) -> dict[str, str]:
    """Map each raw artist name to a canonical (shortest-variant) name."""

    # Sort by length so shorter "base" names are chosen as canonical anchors.
    ordered = sorted(set(names), key=lambda n: (len(n), n.lower()))
    canon: dict[str, str] = {}
    anchors: list[str] = []
    for name in ordered:
        match = None
        for anchor in anchors:
            if _same_artist(name, anchor):
                match = anchor
                break
        if match is None:
            anchors.append(name)
            canon[name] = name
        else:
            canon[name] = match
    return canon


def _build(base: Path) -> dict[str, Any]:
    tracks: list[dict[str, Any]] = []
    if base.exists():
        for path in sorted(base.rglob('*')):
            if not path.is_file() or path.suffix.lower() not in _AUDIO_EXTS:
                continue
            rel = path.relative_to(base).as_posix()
            meta = _read_tags(path)
            meta['file'] = rel
            try:
                meta['added'] = path.stat().st_mtime
            except OSError:
                meta['added'] = 0
            tracks.append(meta)

    # Collapse near-identical artist spellings to one canonical name.
    canon = _canonicalize_artists(
        [tr['artist'] or 'Unknown Artist' for tr in tracks]
    )

    artists: dict[str, dict[str, Any]] = {}
    for tr in tracks:
        raw = tr['artist'] or 'Unknown Artist'
        name = canon.get(raw, raw)
        entry = artists.setdefault(
            name,
            {'name': name, 'count': 0, 'albums': {}, 'cover': tr['file']},
        )
        entry['count'] += 1
        album_name = tr['album'] or ''
        # A "single" often tags album == title; bucket those together so the
        # artist view isn't a wall of one-track albums.
        if not album_name or album_name.strip().lower() == tr['title'].strip().lower():
            album_name = 'Singles'
        album = entry['albums'].setdefault(
            album_name,
            {'name': album_name, 'tracks': [], 'cover': tr['file']},
        )
        album['tracks'].append(tr)

    artist_list = []
    for name, entry in sorted(artists.items(), key=lambda kv: kv[0].lower()):
        albums = []
        for aname, album in sorted(
            entry['albums'].items(), key=lambda kv: kv[0].lower()
        ):
            album['tracks'].sort(
                key=lambda t: (t['track_number'] or 999, t['title'].lower())
            )
            albums.append(album)
        artist_list.append({
            'name': name,
            'count': entry['count'],
            'cover': entry['cover'],
            'albums': albums,
        })

    return {
        'tracks': tracks,
        'artists': artist_list,
        'total': len(tracks),
        # O(1) lookup tables for the "is this song already downloaded?" check.
        'by_video_id': {
            tr['video_id']: tr['file'] for tr in tracks if tr.get('video_id')
        },
        # Normalized (artist|title) → file for the fuzzy fallback when a song
        # was downloaded before we started tagging video_id, or imported from
        # somewhere else (no tag).
        'by_key': {
            _locate_key(tr['artist'], tr['title']): tr['file']
            for tr in tracks
        },
    }


_LOCATE_KEY_RE = __import__('re').compile(r'[^a-z0-9]+')


def _locate_key(artist: str, title: str) -> str:
    a = _LOCATE_KEY_RE.sub(' ', (artist or '').casefold()).strip()
    t = _LOCATE_KEY_RE.sub(' ', (title or '').casefold()).strip()
    return f'{a}|{t}'


def locate(
    base: Path,
    video_id: str = '',
    artist: str = '',
    title: str = '',
) -> Optional[dict[str, Any]]:
    """Return ``{file, title, artist, video_id}`` if a downloaded copy exists.

    Tries video_id first (exact, set by recent downloads), then falls back
    to a normalized ``artist|title`` key match (handles legacy files that
    pre-date the video_id tag). Title-only is the LAST resort and only
    fires when the caller had NO artist hint at all: otherwise a
    different artist's track sharing the title would wrongly win.
    """

    data = _get(base)
    if video_id:
        f = data['by_video_id'].get(video_id)
        if f:
            return _track_for_file(data, f)
    if artist or title:
        k = _locate_key(artist, title)
        f = data['by_key'].get(k)
        if f:
            return _track_for_file(data, f)
        # Title-only fallback only when the caller didn't pass an artist.
        if not artist.strip():
            norm_title = k.split('|', 1)[1]
            if len(norm_title) >= 4:
                for key, fpath in data['by_key'].items():
                    if key.split('|', 1)[1] == norm_title:
                        return _track_for_file(data, fpath)
    return None


def _track_for_file(
    data: dict[str, Any], file: str
) -> Optional[dict[str, Any]]:
    for tr in data['tracks']:
        if tr['file'] == file:
            return {
                'file': file,
                'title': tr.get('title', ''),
                'artist': tr.get('artist', ''),
                'video_id': tr.get('video_id', ''),
                'duration': tr.get('duration', 0),
            }
    return {'file': file}


def _get(base: Path) -> dict[str, Any]:
    global _cache, _cache_signature
    sig = _signature(base)
    with _lock:
        if _cache_signature == sig and _cache:
            return _cache
    built = _build(base)
    with _lock:
        _cache = built
        _cache_signature = sig
    return built


def signature(base: Path) -> tuple[int, float]:
    """Public view of the folder fingerprint, for the disk watcher."""

    return _signature(base)


def invalidate_cache() -> None:
    """Force the next :func:`library` call to re-scan the disk.

    Called when the user changes the download folder so the new
    location's tracks show up immediately.
    """
    global _cache, _cache_signature
    with _lock:
        _cache = {}
        _cache_signature = None


def library(base: Path) -> dict[str, Any]:
    return _get(base)


def artists(base: Path) -> list[dict[str, Any]]:
    data = _get(base)
    # Strip nested album/track payloads for the lightweight list view.
    return [
        {'name': a['name'], 'count': a['count'], 'cover': a['cover']}
        for a in data['artists']
    ]


def artist_detail(base: Path, name: str) -> Optional[dict[str, Any]]:
    data = _get(base)
    target = name.casefold()
    for a in data['artists']:
        if a['name'].casefold() == target:
            return a
    return None


def search(base: Path, query: str, limit: int = 50) -> dict[str, Any]:
    """Fuzzy offline search across title / artist / album."""

    data = _get(base)
    q = query.casefold().strip()
    if not q:
        return {'tracks': [], 'artists': [], 'albums': []}
    terms = q.split()

    def matches(haystack: str) -> bool:
        h = haystack.casefold()
        return all(t in h for t in terms)

    track_hits = [
        tr
        for tr in data['tracks']
        if matches(f"{tr['title']} {tr['artist']} {tr['album']}")
    ][:limit]

    artist_hits = [
        {'name': a['name'], 'count': a['count'], 'cover': a['cover']}
        for a in data['artists']
        if matches(a['name'])
    ][:limit]

    album_hits = []
    seen = set()
    for a in data['artists']:
        for album in a['albums']:
            key = f"{a['name']}|{album['name']}"
            if key in seen:
                continue
            if matches(f"{album['name']} {a['name']}"):
                seen.add(key)
                album_hits.append({
                    'name': album['name'],
                    'artist': a['name'],
                    'cover': album['cover'],
                    'count': len(album['tracks']),
                })
    album_hits = album_hits[:limit]

    return {
        'tracks': track_hits,
        'artists': artist_hits,
        'albums': album_hits,
    }
