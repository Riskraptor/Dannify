"""Offline library indexing: artists, albums, tracks, and fuzzy search.

Reads embedded tags from the downloaded audio files (via dannify.tags) and
builds a cached, grouped view of the library. The cache is invalidated
whenever the download directory's listing changes (file count or latest
mtime), so newly downloaded tracks show up without a restart.
"""

from __future__ import annotations

import stat as _stat
import threading
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from . import tags as _tags

# .dnf is a sealed container holding one of the others. Everything that walks
# the music folder has to count it as a track, or a sealed library looks empty.
_AUDIO_EXTS = {'.mp3', '.m4a', '.flac', '.ogg', '.wav', '.aac', '.opus', '.dnf'}

_lock = threading.Lock()
# One scan at a time. The window asks for the songs and the artists together,
# and both used to read every tag in the folder side by side, each doing the
# whole job; on a big library that doubled the wait for both.
_build_lock = threading.Lock()
_cache: dict[str, Any] = {}
_cache_signature: Optional[tuple] = None


def _signature(base: Path) -> tuple[int, float, int]:
    """File count, newest change, and a digest of every name, size and time.

    Count and newest time alone missed a rename in Explorer: same number of
    files, nothing newer. The list went on offering the old name, and playing
    it said the file had been moved or deleted.
    """

    count = 0
    latest = 0.0
    digest = 0
    for p in base.rglob('*'):
        if p.suffix.lower() not in _AUDIO_EXTS:
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        if not _stat.S_ISREG(st.st_mode):
            continue
        count += 1
        latest = max(latest, st.st_mtime)
        digest ^= hash((str(p), st.st_size, st.st_mtime_ns))
    return count, latest, digest


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

    # The word separators only count between two names, with a space on
    # each side: "X Ambassadors" and "Malcolm X" are one artist each, where
    # the old pattern cut the X off and kept "Ambassadors". "x" is tried
    # last, inside what the other separators left, so the X that ends
    # "Lil Nas X ft. Billy Ray Cyrus" stays with its name.
    parts = _re.split(
        r'\s*(?:/|;|,|&)\s*|\s+(?:feat\.?|ft\.?|featuring)\s+', value, flags=_re.IGNORECASE
    )
    seen: list[str] = []
    for part in parts:
        pieces = [q.strip() for q in _re.split(r'\s+x\s+', part.strip(), flags=_re.IGNORECASE)]
        if len(pieces) > 1 and not all(len(q) >= 2 for q in pieces):
            pieces = [part.strip()]
        for p in pieces:
            if p and p not in seen:
                seen.append(p)
    return seen


_FEAT_RE = __import__('re').compile(r'(?i)\s+(?:feat\.?|ft\.?|featuring)\s+')


def _split_feat(names: list[str]) -> list[str]:
    """Each name, with a guest credited inside it ("A Ft B") made its own.

    Only the words that always mean a guest: "&" and "," are left alone here,
    because a list YouTube Music gave already has them right ("Bob Marley &
    The Wailers" is one act). A song whose credit came as "Mbosso Ft Diamond
    Platnumz" put an artist of that name in the sidebar beside Mbosso.
    """

    out: list[str] = []
    for name in names:
        for piece in _FEAT_RE.split(name):
            piece = piece.strip()
            if piece and piece not in out:
                out.append(piece)
    return out


def _clean_ids(raw: Any) -> list[dict[str, str]]:
    """The artists a song credits, with their YouTube Music ids."""

    out: list[dict[str, str]] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and item.get('id') and item.get('name'):
            out.append({'name': str(item['name']), 'id': str(item['id'])})
    return out


def _read_tags(path: Path) -> dict[str, Any]:
    """Best-effort tag read; falls back to the ``Artist - Title`` filename."""

    # A sealed container keeps its own header. A tag reader would see noise.
    if path.suffix.lower() == '.dnf':
        from . import vault

        # Read once, and with it whether the track will play at all. A track
        # that will not used to come back looking like any other with its
        # details missing, and the first anybody heard of it was a play button
        # that did nothing. Saying so here is what lets the window mark it and
        # offer to repair it.
        head, problem = vault.inspect(path)
        head = head or {}
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
            artists = _split_feat([str(a) for a in stored if a])
            primary = _split_feat([raw])[0] if raw.strip() else artists[0]
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
            # Who the song credits, by their YouTube Music id: what tells two
            # artists with one name apart, and finds the right one online.
            'artist_ids': _clean_ids(head.get('artist_ids')),
            # The album on YouTube Music, for songs saved since it was kept.
            'album_id': str(head.get('album_id') or '')[:64],
            'problem': problem,
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
        found = _tags.details(path)
        if found:
            title = found['title']
            album_artist = found['albumartist']
            all_artists = _split_artists(found['artist'])
            album = found['album']
            genre = found['genre']
            track_number = int(found['track'] or 0)
            duration = int(found['duration'] or 0)
            video_id = found['video_id']
    except Exception:
        logger.opt(exception=True).debug('Tag read failed for {}', path)

    # Primary artist for grouping: prefer the clean album-artist, else the
    # first split artist, else the filename's "Artist - Title" prefix.
    primary = album_artist or (all_artists[0] if all_artists else '')
    if primary:
        primary = _split_feat([primary])[0]

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
        'artist_ids': [],
        'album_id': '',
        'problem': '',
    }


_VIDEO_ID_RE = __import__('re').compile(r'^[A-Za-z0-9_-]{11}$')


def _read_video_id_tag(path: Path) -> str:
    """Return the stored YouTube videoId for *path*, or ''.

    Looks at the format-specific frame written by
    :func:`dannify.downloader.embed_video_id` (and by earlier versions, for
    MP3, FLAC and Ogg files saved before songs were sealed).
    """

    try:
        return _tags.video_id(path)
    except Exception:
        return ''


def _norm_name(name: str) -> str:
    return fold(name)


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
    # A one-word name is not a shortened form of a longer one. Treating it as
    # one filed Drake Bell under Drake, Future Islands under Future and Travis
    # Scott under Travis. A longer prefix still is ("Stephen Kasolo" and
    # "Stephen Kasolo Kitole"), and a one-letter slip in one word still is.
    if len(short) == 1 and len(long) > 1:
        return False
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
    # Between spellings of one length, one not in capitals, then the one most
    # songs use, then a fixed order. It was whichever a set happened to give
    # first, so an artist was "Alex Kasau Katombi" on one start and
    # "ALEX KASAU KATOMBI" on the next.
    from collections import Counter

    used = Counter(names)
    ordered = sorted(used, key=lambda n: (len(n), n.isupper(), -used[n], n.lower(), n))
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


def _pick_cover(holder: dict[str, Any], tr: dict[str, Any]) -> None:
    # The picture of an artist or an album comes from one of its tracks.
    # It used to be the first one found, broken or not, so an artist whose
    # first song would not play showed a grey square however many good
    # ones they had. A track that plays wins; 'cover_v' changes whenever
    # that file does, so a repaired song's picture is fetched afresh
    # instead of the failure being remembered.
    if holder.get('_cover_ok') or ('cover' in holder and tr.get('problem')):
        return
    holder['cover'] = tr['file']
    holder['cover_v'] = int(tr.get('added') or 0)
    holder['_cover_ok'] = not tr.get('problem')


def _identity(name: str, members: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Who this artist is online, as far as their songs say.

    The ids the songs credit under this name, the most credited first, and a
    few of the songs' video ids for when none of them recorded an id (saved by
    an earlier version): YouTube says who is on a recording. A name alone is
    not enough: two "Mavokali" channels came back from a search, and the first
    was a video channel with no songs, not the one that released them.
    """

    from collections import Counter

    want = fold(name)
    ids: Counter = Counter()
    videos: list[str] = []
    for tr in members:
        for a in tr.get('artist_ids') or []:
            if fold(a['name']) == want or _same_artist(a['name'], name):
                ids[a['id']] += 1
        lead = (tr.get('artists') or [tr.get('artist') or ''])[0]
        if (
            tr.get('video_id')
            and not tr.get('problem')
            and len(videos) < 4
            and (fold(lead) == want or _same_artist(lead, name))
        ):
            videos.append(tr['video_id'])
    return [i for i, _ in ids.most_common()], videos


def _artist_entry(name: str, members: list[dict[str, Any]]) -> dict[str, Any]:
    """One artist's page: their tracks in albums, and a picture."""

    entry: dict[str, Any] = {'name': name, 'count': 0, 'albums': {}}
    for tr in members:
        _pick_cover(entry, tr)
        entry['count'] += 1
        album_name = tr['album'] or ''
        # A "single" often tags album == title; bucket those together so the
        # artist view isn't a wall of one-track albums.
        if not album_name or album_name.strip().lower() == tr['title'].strip().lower():
            album_name = 'Singles'
        album = entry['albums'].setdefault(album_name, {'name': album_name, 'tracks': []})
        _pick_cover(album, tr)
        album['tracks'].append(tr)

    albums = []
    for _, album in sorted(entry['albums'].items(), key=lambda kv: kv[0].lower()):
        album['tracks'].sort(
            key=lambda t: (t['track_number'] or 999, t['title'].lower())
        )
        album.pop('_cover_ok', None)
        albums.append(album)
    ids, videos = _identity(name, members)
    return {
        'name': name,
        'count': entry['count'],
        'cover': entry.get('cover', ''),
        'cover_v': entry.get('cover_v', 0),
        'albums': albums,
        'ids': ids,
        'videos': videos,
    }


def _image_size(data: bytes) -> Optional[tuple[int, int]]:
    """Width and height of a JPEG, PNG or WebP, read from its first bytes."""

    if data[:8] == b'\x89PNG\r\n\x1a\n' and len(data) >= 24:
        return int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP' and len(data) >= 30:
        kind = data[12:16]
        if kind == b'VP8X':
            return 1 + int.from_bytes(data[24:27], 'little'), 1 + int.from_bytes(data[27:30], 'little')
        if kind == b'VP8 ':
            return int.from_bytes(data[26:28], 'little') & 0x3FFF, int.from_bytes(data[28:30], 'little') & 0x3FFF
        if kind == b'VP8L':
            bits = int.from_bytes(data[21:25], 'little')
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        return None
    if data[:2] != b'\xff\xd8':
        return None
    at = 2
    while at + 9 < len(data):
        if data[at] != 0xFF:
            return None
        marker = data[at + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            at += 2
            continue
        length = int.from_bytes(data[at + 2:at + 4], 'big')
        # Start of frame (any kind but DHT, JPG and DAC): the size is in it.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return int.from_bytes(data[at + 7:at + 9], 'big'), int.from_bytes(data[at + 5:at + 7], 'big')
        at += 2 + length
    return None


# Whether a saved song's artwork is square, by file and when it was saved.
_square: dict[tuple[str, float], bool] = {}


def _square_art(base: Path, tr: dict[str, Any]) -> bool:
    """Whether a song's artwork is an album cover rather than a video frame.

    A song saved from its music video carries a 16:9 frame of the video. As an
    album's picture, cut to a square, it was a strip out of the middle of
    somebody's face with half a title across it.
    """

    stamp = (tr['file'], float(tr.get('added') or 0))
    if stamp in _square:
        return _square[stamp]
    from . import vault  # noqa: PLC0415  (circular at import)

    path = base / tr['file']
    try:
        found = vault.cover(path) if path.suffix.lower() == vault.SUFFIX else _tags.cover(path)
        size = _image_size(found[0]) if found else None
    except Exception:
        size = None
    square = bool(size) and size[1] > 0 and abs(size[0] - size[1]) <= 0.06 * max(size)
    if len(_square) > 20000:
        _square.clear()
    _square[stamp] = square
    return square


def _album_list(tracks: list[dict[str, Any]], base: Optional[Path] = None) -> list[dict[str, Any]]:
    """Every album there are songs from, with those songs in album order.

    An album is the songs that share an album name and an artist page (the
    track's ``group``): "Greatest Hits" by two people is two albums, and an
    album whose songs are tagged "Sauti Sol" and "SAUTI SOL" is one. Its id
    on YouTube Music is whichever of its songs knows it.

    One song whose album is named after it is a single, not an album: the
    artist page files those under Singles, and a page of one-song "albums"
    each called after its only song would be the library again, with bigger
    pictures. A single from an EP of the same name is kept once the EP has a
    second song saved.
    """

    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for tr in tracks:
        name = (tr.get('album') or '').strip()
        if not name:
            continue
        who = tr.get('group') or tr.get('artist') or 'Unknown Artist'
        entry = groups.setdefault(
            (fold(name) or name.casefold(), who),
            {'name': name, 'artist': who, 'album_id': '', 'tracks': []},
        )
        entry['tracks'].append(tr)
        entry['album_id'] = entry['album_id'] or tr.get('album_id') or ''

    albums = []
    for entry in groups.values():
        members = entry['tracks']
        if len(members) == 1 and fold(members[0].get('title') or '') == fold(entry['name']):
            continue
        members.sort(key=lambda t: (t.get('track_number') or 999, (t.get('title') or '').casefold()))
        holder: dict[str, Any] = {}
        for tr in members:
            _pick_cover(holder, tr)
        # The album's own cover when one of its first few songs has it: an
        # album saved after one of its songs was saved from the video.
        if base is not None:
            playable = [tr for tr in members if not tr.get('problem')]
            for tr in playable[:4]:
                if _square_art(base, tr):
                    holder['cover'], holder['cover_v'] = tr['file'], int(tr.get('added') or 0)
                    break
        albums.append({
            'name': entry['name'],
            'artist': entry['artist'],
            'album_id': entry['album_id'],
            'count': len(members),
            'duration': sum(int(tr.get('duration') or 0) for tr in members),
            # When its newest song was saved: "recently added" for albums.
            'added': max(float(tr.get('added') or 0) for tr in members),
            'cover': holder.get('cover', ''),
            'cover_v': holder.get('cover_v', 0),
            'tracks': members,
        })
    albums.sort(key=lambda a: (a['name'].casefold(), a['artist'].casefold()))
    return albums


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

    groups: dict[str, list[dict[str, Any]]] = {}
    for tr in tracks:
        raw = tr['artist'] or 'Unknown Artist'
        name = canon.get(raw, raw)
        # Which artist page the track is on. The window needs it: playing an
        # artist from their card used to pick tracks by the exact tag, so a
        # song tagged "BENSOUL" sat on Bensoul's page and was left out when
        # Bensoul was played.
        tr['group'] = name
        groups.setdefault(name, []).append(tr)

    artist_list = [
        _artist_entry(name, members)
        for name, members in sorted(groups.items(), key=lambda kv: kv[0].lower())
    ]

    # A track that will not play is not a downloaded copy of anything. Left
    # in these, every play of that song from search or home was sent to the
    # broken file instead of streaming it, and failed.
    playable = [tr for tr in tracks if not tr.get('problem')]

    return {
        'tracks': tracks,
        'artists': artist_list,
        'albums': _album_list(tracks, base),
        'total': len(tracks),
        # O(1) lookup tables for the "is this song already downloaded?" check.
        'by_video_id': {
            tr['video_id']: tr['file'] for tr in playable if tr.get('video_id')
        },
        # Normalized (artist|title) → file for the fuzzy fallback when a song
        # was downloaded before we started tagging video_id, or imported from
        # somewhere else (no tag).
        'by_key': {
            _locate_key(tr['artist'], tr['title']): tr['file']
            for tr in playable
        },
    }


_FOLD_RE = __import__('re').compile(r'[\W_]+')


def fold(text: str) -> str:
    """Lower case, accents off, anything but a letter or digit a space.

    Letters in any script. This used to keep a to z and 0 to 9 only, which
    turned every Japanese, Korean, Cyrillic or Arabic title into nothing at
    all: two such songs had the same empty key, so asking for one could play
    the other, and every one of them showed as already downloaded.
    """

    import unicodedata

    decomposed = unicodedata.normalize('NFKD', (text or '').casefold())
    bare = ''.join(c for c in decomposed if not unicodedata.combining(c))
    return _FOLD_RE.sub(' ', bare).strip()


def _locate_key(artist: str, title: str) -> str:
    return f'{fold(artist)}|{fold(title)}'


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
        if not k.split('|', 1)[1]:
            return None  # no title to go on: anything would match
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
    # The folder is part of the key: two empty folders look identical.
    sig = (str(base), _signature(base))
    with _lock:
        if _cache_signature == sig and _cache:
            return _cache
    with _build_lock:
        # Whoever held the lock may have just built exactly this.
        with _lock:
            if _cache_signature == sig and _cache:
                return _cache
        # Keyed by what the folder looked like BEFORE the scan. A file that
        # changes during it moves the fingerprint, so the next call scans
        # again instead of keeping a half-finished picture.
        built = _build(base)
        with _lock:
            _cache = built
            _cache_signature = sig
    return built


def served_signature(base: Path) -> Optional[tuple]:
    """The fingerprint of the folder as it was last read for the window."""

    with _lock:
        if _cache_signature and _cache and _cache_signature[0] == str(base):
            return _cache_signature[1]
    return None


def signature(base: Path) -> tuple[int, float, int]:
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
        {'name': a['name'], 'count': a['count'], 'cover': a['cover'], 'cover_v': a.get('cover_v', 0)}
        for a in data['artists']
    ]


def albums(base: Path) -> list[dict[str, Any]]:
    """Every album in the library, without its songs (see _album_list)."""

    return [{k: v for k, v in a.items() if k != 'tracks'} for a in _get(base).get('albums', [])]


def album_detail(base: Path, artist: str, name: str) -> Optional[dict[str, Any]]:
    """One album, songs and all, by its artist page and its name.

    The way they are written does not have to match exactly: a link made
    from a song's own tags ("BENSOUL", "midnight train") still finds it.
    """

    found = _get(base).get('albums', [])
    for a in found:
        if a['artist'].casefold() == artist.casefold() and a['name'].casefold() == name.casefold():
            return a
    want_artist, want_name = fold(artist), fold(name)
    if not want_name:
        return None
    for a in found:
        if fold(a['name']) == want_name and (
            fold(a['artist']) == want_artist or _same_artist(a['artist'], artist)
        ):
            return a
    return None


def artist_hints(base: Path, names: list[str]) -> dict[str, dict[str, list[str]]]:
    """For each artist, what their songs say about who they are online."""

    data = _get(base)
    by_name = {a['name']: a for a in data['artists']}
    out: dict[str, dict[str, list[str]]] = {}
    for name in names:
        a = by_name.get(name)
        if a is None:
            a = artist_detail(base, name)
        if a and (a.get('ids') or a.get('videos')):
            out[name] = {'ids': list(a.get('ids') or []), 'videos': list(a.get('videos') or [])}
    return out


def artist_detail(base: Path, name: str) -> Optional[dict[str, Any]]:
    data = _get(base)
    target = name.casefold()
    for a in data['artists']:
        if a['name'].casefold() == target:
            return a
    # Every artist name on a song is a link, not only the ones with a page of
    # their own, and the others used to say "Artist not found": a spelling
    # the list folded into another name ("Stephen Kasolo Kitole" is on
    # Stephen Kasolo's page), or somebody who is only ever featured.
    folded = fold(name)
    if not folded:
        return None
    for tr in data['tracks']:
        if fold(tr.get('artist') or '') == folded and tr.get('group'):
            for a in data['artists']:
                if a['name'] == tr['group']:
                    return a
    credited = [
        tr for tr in data['tracks']
        if any(fold(x) == folded for x in (tr.get('artists') or []))
    ]
    if credited:
        shown = next(
            (x for tr in credited for x in tr['artists'] if fold(x) == folded), name,
        )
        return _artist_entry(shown, credited)
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
        {'name': a['name'], 'count': a['count'], 'cover': a['cover'], 'cover_v': a.get('cover_v', 0)}
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
                    'cover_v': album.get('cover_v', 0),
                    'count': len(album['tracks']),
                })
    album_hits = album_hits[:limit]

    return {
        'tracks': track_hits,
        'artists': artist_hits,
        'albums': album_hits,
    }
