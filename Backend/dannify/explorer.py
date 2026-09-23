"""Online music explorer: Spotify-style discovery over YouTube Music.

Provides multi-type search (songs / artists / albums / playlists) plus rich
artist, album and playlist pages so the UI can browse and preview *before*
downloading. Everything funnels through ``ytmusicapi`` and is normalized into
the same song-dict shape the rest of Dannify uses.
"""

from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from loguru import logger

from .providers import _ytm, _result_to_song, _upgrade_thumbnail, _parse_duration


# --- tiny TTL cache so repeated explorer hits are instant ---
_TTL = 60 * 30
_cache: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
_lock = threading.Lock()

# Long-lived workers for the parallel facet requests. Sized for a couple of
# searches in flight at once (search-as-you-type fires one per keystroke
# burst). Every HTTP call underneath carries a timeout (see
# account.REQUEST_TIMEOUT), so a worker can never park forever.
_FACET_TIMEOUT = 20.0
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix='ytm-search')


# How old a cached answer may get before we quietly refresh it behind the
# user's back. Below this it is served as-is; above it, still served
# instantly, but a background refresh starts so the next visit is current.
# This is what stops the app feeling frozen in time after the first search.
_SOFT_TTL = 90.0
_refreshing: set[str] = set()


def _cache_get(key: str, refresh=None) -> Optional[Any]:
    """Cached value, revalidating in the background once it goes stale."""
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if not hit or now - hit[0] >= _TTL:
            return None
        _cache.move_to_end(key)
        stale = now - hit[0] >= _SOFT_TTL
        if stale and refresh is not None and key not in _refreshing:
            _refreshing.add(key)
        else:
            stale = False
        value = hit[1]

    if stale:
        def _revalidate() -> None:
            try:
                fresh = refresh()
                if fresh:
                    _cache_put(key, fresh)
            except Exception:
                logger.opt(exception=True).debug('revalidate {} failed', key)
            finally:
                with _lock:
                    _refreshing.discard(key)

        _POOL.submit(_revalidate)
    return value


def _cache_put(key: str, value: Any) -> None:
    with _lock:
        _cache[key] = (time.time(), value)
        _cache.move_to_end(key)
        while len(_cache) > 256:
            _cache.popitem(last=False)


def clear_cache() -> None:
    """Drop cached results (called when the signed-in account changes)."""

    with _lock:
        _cache.clear()


# The home feed is personal and changes through the day: cache it briefly
# so navigating back to Home is instant without going stale.
_HOME_TTL = 60 * 5


def home(limit: int = 6) -> list[dict[str, Any]]:
    from . import account

    key = f'home::{limit}::{account.is_signed_in()}'
    cached = _cache_get(key, refresh=lambda: account.home(limit=limit))
    if cached is not None:
        return cached
    sections = account.home(limit=limit)
    if sections:
        _cache_put(key, sections)
    return sections


def _thumb(item: dict[str, Any]) -> str:
    thumbs = item.get('thumbnails') or []
    if not thumbs:
        return ''
    return _upgrade_thumbnail(thumbs[-1].get('url', ''))


def _artists_list(item: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for a in item.get('artists') or []:
        if isinstance(a, dict) and a.get('name'):
            out.append({'name': a['name'], 'id': a.get('id') or ''})
    return out


def _artist_names(item: dict[str, Any]) -> list[str]:
    return [a['name'] for a in _artists_list(item)]


# ---------------------------------------------------------------------------
# Search (multi-type)
# ---------------------------------------------------------------------------


def _song_card(r: dict[str, Any]) -> Optional[dict[str, Any]]:
    song = _result_to_song(r)
    if song is None:
        return None
    # Preserve artist ids so the UI can deep-link into artist pages.
    song['artist_ids'] = _artists_list(r)
    return song


def _artist_card(r: dict[str, Any]) -> Optional[dict[str, Any]]:
    bid = r.get('browseId')
    name = r.get('artist') or r.get('title')
    if not bid or not name:
        return None
    return {
        'type': 'artist',
        'browse_id': bid,
        'name': name,
        'cover_url': _thumb(r),
        'subscribers': r.get('subscribers') or '',
    }


def _album_card(r: dict[str, Any]) -> Optional[dict[str, Any]]:
    bid = r.get('browseId')
    title = r.get('title')
    if not bid or not title:
        return None
    return {
        'type': 'album',
        'browse_id': bid,
        'name': title,
        'cover_url': _thumb(r),
        'artists': _artist_names(r),
        'artist_ids': _artists_list(r),
        'year': str(r.get('year') or ''),
        'album_type': r.get('type') or 'Album',
    }


def _playlist_card(r: dict[str, Any]) -> Optional[dict[str, Any]]:
    bid = r.get('browseId')
    title = r.get('title')
    if not bid or not title:
        return None
    return {
        'type': 'playlist',
        'browse_id': bid,
        'name': title,
        'cover_url': _thumb(r),
        'item_count': str(r.get('itemCount') or ''),
        'author': r.get('author') or '',
    }


def search(query: str, limit: int = 20) -> dict[str, Any]:
    """Return ``{songs, artists, albums, playlists}`` for *query*."""

    q = (query or '').strip()
    if not q:
        return {'songs': [], 'artists': [], 'albums': [], 'playlists': []}

    cache_key = f'search::{q.lower()}::{limit}'
    cached = _cache_get(cache_key, refresh=lambda: _search_uncached(q, limit))
    if cached is not None:
        return cached
    return _search_uncached(q, limit, cache_key)


def _search_uncached(
    q: str, limit: int, cache_key: Optional[str] = None
) -> dict[str, Any]:
    if cache_key is None:
        cache_key = f'search::{q.lower()}::{limit}'

    def _run(filt: str, fn) -> list[dict[str, Any]]:
        try:
            # One client per worker thread (ytmusicapi is not thread-safe).
            rows = _ytm().search(q, filter=filt, limit=limit)
        except Exception:
            logger.opt(exception=True).debug('explore search %s failed', filt)
            return []  # one failing facet must not fail the whole search
        out = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            card = fn(r)
            if card:
                out.append(card)
        return out

    # The four facets are independent requests: run them at once. Sequential
    # calls made a search feel like ~4× one round trip.
    facets = (
        ('songs', 'songs', _song_card),
        ('artists', 'artists', _artist_card),
        ('albums', 'albums', _album_card),
        ('playlists', 'community_playlists', _playlist_card),
    )
    # A shared pool, never a `with` block: ThreadPoolExecutor.__exit__ waits
    # for every worker, so one stalled facet would hold the whole request open
    # long past its own timeout. Workers are also reused across searches, so a
    # repeat query skips four thread creations.
    result: dict[str, Any] = {}
    futures = {key: _POOL.submit(_run, filt, fn) for key, filt, fn in facets}
    deadline = time.monotonic() + _FACET_TIMEOUT
    for key, future in futures.items():
        try:
            result[key] = future.result(timeout=max(0.1, deadline - time.monotonic()))
        except Exception:
            logger.opt(exception=True).debug('explore search {} gave up', key)
            result[key] = []
    # Don't cache a half-empty answer: the next search should try again.
    if any(result.values()):
        _cache_put(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Artist page
# ---------------------------------------------------------------------------


def _section_songs(section: Any) -> list[dict[str, Any]]:
    songs: list[dict[str, Any]] = []
    results = (section or {}).get('results') if isinstance(section, dict) else None
    for r in results or []:
        if not isinstance(r, dict):
            continue
        vid = r.get('videoId')
        if not vid:
            continue
        album = r.get('album') or {}
        songs.append({
            'song_id': vid,
            'name': r.get('title', ''),
            'artists': _artist_names(r) or [r.get('artist', '')],
            'artist_ids': _artists_list(r),
            'album_name': album.get('name', '') if isinstance(album, dict) else '',
            'album_id': album.get('id', '') if isinstance(album, dict) else '',
            'video_id': vid,
            'like_status': r.get('likeStatus') or '',
            'cover_url': _thumb(r),
            'duration': _parse_duration(r.get('duration')),
            'url': f'https://music.youtube.com/watch?v={vid}',
            'source': 'youtube',
        })
    return songs


def _section_albums(section: Any) -> list[dict[str, Any]]:
    albums: list[dict[str, Any]] = []
    results = (section or {}).get('results') if isinstance(section, dict) else None
    for r in results or []:
        if not isinstance(r, dict):
            continue
        card = _album_card(r)
        if card:
            albums.append(card)
    return albums


def _playlist_songs(browse_id: str, limit: int = 200) -> list[dict[str, Any]]:
    """Return all songs from a YT-Music playlist browseId (e.g. an artist's
    full songs list), normalized to song dicts."""

    pid = browse_id[2:] if browse_id.startswith('VL') else browse_id
    try:
        data = _ytm().get_playlist(pid, limit=limit)
    except Exception:
        logger.opt(exception=True).debug('artist songs playlist failed %s', pid)
        return []
    songs: list[dict[str, Any]] = []
    for t in data.get('tracks') or []:
        if not isinstance(t, dict):
            continue
        vid = t.get('videoId')
        if not vid:
            continue
        album_obj = t.get('album') or {}
        songs.append({
            'song_id': vid,
            'name': t.get('title', ''),
            'artists': _artist_names(t),
            'artist_ids': _artists_list(t),
            'album_name': album_obj.get('name', '')
            if isinstance(album_obj, dict)
            else '',
            'album_id': album_obj.get('id', '') if isinstance(album_obj, dict) else '',
            'video_id': vid,
            'like_status': t.get('likeStatus') or '',
            'cover_url': _thumb(t),
            'duration': t.get('duration_seconds')
            or _parse_duration(t.get('duration')),
            'url': f'https://music.youtube.com/watch?v={vid}',
            'source': 'youtube',
        })
    return songs


def _artist_full_albums(browse_id: str, section: Any, channel_id: str, kind: str) -> list[dict[str, Any]]:
    """Return the full album/single list. If the section has a ``params``
    token, fetch the complete paginated list; otherwise use the inline preview."""

    if not isinstance(section, dict):
        return []
    params = section.get('params')
    if params and channel_id:
        try:
            rows = _ytm().get_artist_albums(channel_id, params)
            out = []
            for r in rows or []:
                if isinstance(r, dict):
                    card = _album_card(r)
                    if card:
                        out.append(card)
            if out:
                return out
        except Exception as exc:
            logger.debug('get_artist_albums fallback: {}', exc.__class__.__name__)
    return _section_albums(section)


def artist(browse_id: str) -> dict[str, Any]:
    cache_key = f'artist::{browse_id}'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    data = _ytm().get_artist(browse_id)
    channel_id = data.get('channelId') or browse_id

    # The artist page needs three more things from YouTube: the full songs
    # playlist, the full album list and the full singles list. They only
    # depend on the response above, not on each other, so running them one
    # after another was spending three round trips of wall clock on work
    # that fits in one. Measured serially: 1.1 s + 1.9 s + two more.
    songs_section = data.get('songs') or {}
    songs_bid = (
        songs_section.get('browseId') if isinstance(songs_section, dict) else None
    )

    def _songs() -> list[dict[str, Any]]:
        # Prefer the artist's songs *playlist* (every track) over the
        # five-track inline preview.
        rows = _playlist_songs(songs_bid) if songs_bid else []
        return rows or _section_songs(songs_section)

    jobs = {
        'songs': _POOL.submit(_songs),
        'albums': _POOL.submit(
            _artist_full_albums, browse_id, data.get('albums'), channel_id, 'albums'
        ),
        'singles': _POOL.submit(
            _artist_full_albums, browse_id, data.get('singles'), channel_id, 'singles'
        ),
    }

    def _done(name: str, fallback):
        try:
            # Generous: this is the whole page, and a slow section is still
            # better than an empty one.
            return jobs[name].result(timeout=20)
        except Exception:
            logger.opt(exception=True).debug('artist {} section failed', name)
            return fallback

    out = {
        'type': 'artist',
        'browse_id': browse_id,
        'name': data.get('name', ''),
        'description': data.get('description') or '',
        'cover_url': _thumb(data),
        'subscribers': data.get('subscribers') or '',
        'monthly_listeners': data.get('monthlyListeners') or '',
        'songs': _done('songs', []),
        'albums': _done('albums', []),
        'singles': _done('singles', []),
    }
    _cache_put(cache_key, out)
    return out


# ---------------------------------------------------------------------------
# Album page
# ---------------------------------------------------------------------------


def album(browse_id: str) -> dict[str, Any]:
    cache_key = f'album::{browse_id}'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    data = _ytm().get_album(browse_id)
    cover = _thumb(data)
    artists = _artist_names(data)
    tracks: list[dict[str, Any]] = []
    for i, t in enumerate(data.get('tracks') or [], start=1):
        if not isinstance(t, dict):
            continue
        vid = t.get('videoId')
        if not vid:
            continue
        t_artists = _artist_names(t) or artists
        tracks.append({
            'song_id': vid,
            'name': t.get('title', ''),
            'artists': t_artists,
            'artist_ids': _artists_list(t),
            'album_name': data.get('title', ''),
            'album_id': browse_id,
            'video_id': vid,
            'like_status': t.get('likeStatus') or '',
            'cover_url': _thumb(t) or cover,
            'duration': t.get('duration_seconds')
            or _parse_duration(t.get('duration')),
            'track_number': i,
            'url': f'https://music.youtube.com/watch?v={vid}',
            'source': 'youtube',
        })
    out = {
        'type': 'album',
        'browse_id': browse_id,
        'name': data.get('title', ''),
        'cover_url': cover,
        'artists': artists,
        'artist_ids': _artists_list(data),
        'year': str(data.get('year') or ''),
        'track_count': data.get('trackCount') or len(tracks),
        'description': data.get('description') or '',
        'tracks': tracks,
    }
    _cache_put(cache_key, out)
    return out


# ---------------------------------------------------------------------------
# Playlist page
# ---------------------------------------------------------------------------


def _clean_playlist_id(browse_id: str) -> str:
    # ytmusicapi accepts the raw playlistId; search returns VL-prefixed ids.
    bid = browse_id.strip()
    if bid.startswith('VL'):
        bid = bid[2:]
    return bid


def playlist(browse_id: str, limit: int = 200) -> dict[str, Any]:
    pid = _clean_playlist_id(browse_id)
    cache_key = f'playlist::{pid}::{limit}'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    data = _ytm().get_playlist(pid, limit=limit)
    cover = _thumb(data)
    tracks: list[dict[str, Any]] = []
    for i, t in enumerate(data.get('tracks') or [], start=1):
        if not isinstance(t, dict):
            continue
        vid = t.get('videoId')
        if not vid:
            continue
        album_obj = t.get('album') or {}
        tracks.append({
            'song_id': vid,
            'name': t.get('title', ''),
            'artists': _artist_names(t),
            'artist_ids': _artists_list(t),
            'album_name': album_obj.get('name', '')
            if isinstance(album_obj, dict)
            else '',
            'album_id': album_obj.get('id', '') if isinstance(album_obj, dict) else '',
            'video_id': vid,
            'like_status': t.get('likeStatus') or '',
            'cover_url': _thumb(t) or cover,
            'duration': t.get('duration_seconds')
            or _parse_duration(t.get('duration')),
            'track_number': i,
            'url': f'https://music.youtube.com/watch?v={vid}',
            'source': 'youtube',
        })
    author = data.get('author') or {}
    out = {
        'type': 'playlist',
        'browse_id': pid,
        'name': data.get('title', ''),
        'cover_url': cover,
        'description': data.get('description') or '',
        'author': author.get('name', '') if isinstance(author, dict) else str(author or ''),
        'track_count': data.get('trackCount') or len(tracks),
        'tracks': tracks,
    }
    _cache_put(cache_key, out)
    return out
