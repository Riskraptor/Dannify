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


def forget_artist(browse_id: str) -> None:
    """Drop an artist's cached page, so the next visit asks YouTube again."""

    with _lock:
        _cache.pop(f'artist::{browse_id}', None)
        _cache.pop(f'brief::{browse_id}', None)


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
        _suggest_cache.clear()


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
    # Either name YouTube Music uses for them (see account._thumbs_of).
    thumbs = item.get('thumbnails') or item.get('thumbnail') or []
    if isinstance(thumbs, dict):
        thumbs = thumbs.get('thumbnails') or []
    thumbs = [t for t in thumbs if isinstance(t, dict) and t.get('url')]
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


# ---------------------------------------------------------------------------
# Moods and genres: what Search shows before anything is typed
# ---------------------------------------------------------------------------

_MOODS_TTL = 60 * 60 * 12
_MOOD_PLAYLISTS = 40


def moods() -> list[dict[str, Any]]:
    """YouTube Music's moods and genres: ``[{title, items: [{title, params}]}]``."""

    key = 'moods'
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _MOODS_TTL:
        return hit[1]
    raw = _ytm().get_mood_categories() or {}
    sections = []
    for title, items in raw.items():
        cards = [
            {'title': str(i.get('title') or ''), 'params': str(i.get('params') or '')}
            for i in items or []
            if isinstance(i, dict) and i.get('params') and i.get('title')
        ]
        if cards:
            sections.append({'title': str(title), 'items': cards})
    if sections:
        _cache_put(key, sections)
    return sections


def _mood_page_rows(params: str) -> list[dict[str, Any]]:
    """The playlists on a mood or genre page, read one item at a time.

    ytmusicapi reads every two-row item on the page as a playlist. Genre
    pages now also carry shelves of songs and music videos in the same kind
    of item, and the first of those stopped the whole page with a KeyError:
    23 of the 36 categories would not open. Albums and episodes sit there
    too, and read as a playlist they became a card that opened nothing. Here
    only playlists are taken and the rest of the page is passed over.
    """

    from ytmusicapi.navigation import (  # noqa: PLC0415
        CAROUSEL_CONTENTS,
        GRID_ITEMS,
        NAVIGATION_BROWSE_ID,
        SECTION_LIST,
        SINGLE_COLUMN_TAB,
        TITLE,
        nav,
    )
    from ytmusicapi.parsers.browsing import parse_playlist  # noqa: PLC0415

    response = _ytm()._send_request(
        'browse', {'browseId': 'FEmusic_moods_and_genres_category', 'params': params},
    )
    rows: list[dict[str, Any]] = []
    for section in nav(response, SINGLE_COLUMN_TAB + SECTION_LIST, True) or []:
        if not isinstance(section, dict):
            continue
        if 'gridRenderer' in section:
            items = nav(section, GRID_ITEMS, True)
        elif 'musicCarouselShelfRenderer' in section:
            items = nav(section, CAROUSEL_CONTENTS, True)
        elif 'musicImmersiveCarouselShelfRenderer' in section:
            items = nav(section, ['musicImmersiveCarouselShelfRenderer', 'contents'], True)
        else:
            continue
        for item in items or []:
            data = item.get('musicTwoRowItemRenderer') if isinstance(item, dict) else None
            if not isinstance(data, dict):
                continue
            # A playlist's id is VL and the playlist's own; an album's is
            # MPRE, an episode's MPED, and a song or video has none.
            browse_id = nav(data, TITLE + NAVIGATION_BROWSE_ID, True)
            if not (isinstance(browse_id, str) and browse_id.startswith('VL')):
                continue
            try:
                rows.append(parse_playlist(data))
            except (KeyError, IndexError, TypeError):
                continue
    return rows


def mood_playlists(params: str) -> list[dict[str, Any]]:
    """The playlists for one mood or genre, as playlist cards."""

    key = f'mood::{params}'
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _MOODS_TTL:
        return hit[1]
    rows = _mood_page_rows(params)
    cards = []
    for r in rows[:_MOOD_PLAYLISTS]:
        pid = r.get('playlistId') if isinstance(r, dict) else None
        if not pid or not r.get('title'):
            continue
        cards.append({
            'type': 'playlist',
            'browse_id': pid,
            'name': r['title'],
            'cover_url': _thumb(r),
            'description': str(r.get('description') or ''),
        })
    if cards:
        _cache_put(key, cards)
    return cards


# ---------------------------------------------------------------------------
# Charts and new releases: what YouTube Music says is played now, where the
# listener is
# ---------------------------------------------------------------------------

_CHARTS_TTL = 60 * 60 * 6
_CHART_ARTISTS = 20
_NEW_RELEASES = 24


def charts(country: str = '') -> dict[str, Any]:
    """YouTube Music's charts for a country (two capital letters; ``ZZ`` or
    one it has no charts for: the world): ``{country, code, playlists,
    artists}``. The playlists are its chart lists (the trending songs, the
    top videos); the artists the most played now, ranked, with which way
    they are going."""

    code = country.strip().upper() if re.fullmatch(r'[A-Za-z]{2}', country.strip() or '') else 'ZZ'
    key = f'charts::{code}'
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _CHARTS_TTL:
        return hit[1]
    raw = _ytm().get_charts(code) or {}
    options = ((raw.get('countries') or {}).get('options')) or []
    if code != 'ZZ' and options and code not in options:
        return charts('ZZ')
    playlists = []
    for item in raw.get('videos') or []:
        pid = item.get('playlistId') if isinstance(item, dict) else None
        if pid and item.get('title'):
            playlists.append({
                'type': 'playlist',
                'browse_id': pid,
                'name': str(item['title']),
                'cover_url': _thumb(item),
            })
    artists = []
    for item in (raw.get('artists') or [])[:_CHART_ARTISTS]:
        if not isinstance(item, dict) or not item.get('browseId') or not item.get('title'):
            continue
        trend = str(item.get('trend') or '')
        artists.append({
            'type': 'artist',
            'browse_id': item['browseId'],
            'name': str(item['title']),
            'cover_url': _thumb(item),
            'rank': int(item['rank']) if str(item.get('rank') or '').isdigit() else len(artists) + 1,
            'trend': trend if trend in ('up', 'down', 'neutral') else 'neutral',
            'subscribers': str(item.get('subscribers') or ''),
        })
    selected = ((raw.get('countries') or {}).get('selected') or {}).get('text') or ''
    out = {'country': str(selected), 'code': code, 'playlists': playlists, 'artists': artists}
    if playlists or artists:
        _cache_put(key, out)
    return out


def new_releases() -> list[dict[str, Any]]:
    """New albums and singles, as YouTube Music's explore page shows them
    where the listener is."""

    key = 'new_releases'
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _CHARTS_TTL:
        return hit[1]
    raw = _ytm().get_explore() or {}
    cards = []
    for item in (raw.get('new_releases') or [])[:_NEW_RELEASES]:
        if not isinstance(item, dict) or not item.get('browseId') or not item.get('title'):
            continue
        artists = [
            a.get('name') if isinstance(a, dict) else str(a)
            for a in item.get('artists') or []
        ]
        cards.append({
            'type': 'album',
            'browse_id': item['browseId'],
            'name': str(item['title']),
            'artist': ', '.join(a for a in artists if a),
            'kind': str(item.get('type') or ''),
            'cover_url': _thumb(item),
            'explicit': bool(item.get('isExplicit')),
        })
    if cards:
        _cache_put(key, cards)
    return cards


# ---------------------------------------------------------------------------
# Suggestions: what the search box offers while something is being typed
# ---------------------------------------------------------------------------

_SUGGEST_TTL = 60 * 20
# A cache of its own. One is asked for on nearly every keystroke, and in the
# shared one a minute of typing would push out the artist and album pages
# that cost a real round trip to get back.
_suggest_cache: "OrderedDict[str, tuple[float, list[str]]]" = OrderedDict()


def suggest(query: str, limit: int = 8) -> list[str]:
    """What YouTube Music would finish *query* as, most likely first."""

    q = ' '.join((query or '').split())
    if not q:
        return []
    limit = max(1, min(int(limit), 20))
    key = q.casefold()
    with _lock:
        hit = _suggest_cache.get(key)
        if hit and time.time() - hit[0] < _SUGGEST_TTL:
            _suggest_cache.move_to_end(key)
            return hit[1][:limit]
    out: list[str] = []
    seen = {key}  # what was typed is not a suggestion
    for row in _ytm().get_search_suggestions(q) or []:
        text = ' '.join(row.split()) if isinstance(row, str) else ''
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)
    with _lock:
        _suggest_cache[key] = (time.time(), out)
        _suggest_cache.move_to_end(key)
        while len(_suggest_cache) > 400:
            _suggest_cache.popitem(last=False)
    return out[:limit]


class SearchUnavailable(ConnectionError):
    """No part of a search could reach YouTube Music."""


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


def search_artists(query: str, limit: int = 6) -> list[dict[str, Any]]:
    """Artist results only, one request, and a failure is raised, not hidden.

    For putting a name to an online artist (see artist_links): search() turns
    every failure into an empty list, which there reads as "no such artist",
    and an app started before the Wi-Fi was up would have written off every
    artist in the library for a week.
    """

    rows = _ytm().search(query, filter='artists', limit=limit)
    out = []
    for r in rows or []:
        if isinstance(r, dict):
            card = _artist_card(r)
            if card:
                out.append(card)
    return out


def _search_uncached(
    q: str, limit: int, cache_key: Optional[str] = None
) -> dict[str, Any]:
    if cache_key is None:
        cache_key = f'search::{q.lower()}::{limit}'

    def _run(filt: str, fn) -> Optional[list[dict[str, Any]]]:
        try:
            # One client per worker thread (ytmusicapi is not thread-safe).
            rows = _ytm().search(q, filter=filt, limit=limit)
        except Exception:
            logger.opt(exception=True).debug('explore search %s failed', filt)
            return None  # one failing facet must not fail the whole search
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
    failed = 0
    for key, future in futures.items():
        try:
            rows = future.result(timeout=max(0.1, deadline - time.monotonic()))
        except Exception:
            logger.opt(exception=True).debug('explore search {} gave up', key)
            rows = None
        failed += rows is None
        result[key] = rows or []
    if failed == len(facets):
        # Not one part of the search got an answer: that is no connection,
        # not "no results". Said as nothing found, the window told someone
        # offline that the artist they were looking for did not exist.
        raise SearchUnavailable('YouTube Music could not be reached')
    _label_namesakes(result.get('artists') or [])
    # Don't cache a half-empty answer: the next search should try again.
    if any(result.values()):
        _cache_put(cache_key, result)
    return result


def _label_namesakes(cards: list[dict[str, Any]]) -> None:
    """Tell apart artists who share a name.

    A search for "Mavokali" brings back two cards, same name, two channels:
    one has the songs, the other is a channel of videos. Shown as they came,
    they looked like the same artist twice. Each gets what tells them apart
    (their followers, and whether they have songs at all), and one with songs
    goes before one with none.
    """

    from .library import fold  # noqa: PLC0415

    groups: dict[str, list[dict[str, Any]]] = {}
    for card in cards:
        groups.setdefault(fold(card.get('name') or ''), []).append(card)
    twins = [c for group in groups.values() if len(group) > 1 for c in group][:6]
    if not twins:
        return
    jobs = {c['browse_id']: _POOL.submit(artist_brief, c['browse_id']) for c in twins}
    deadline = time.monotonic() + 5
    for card in twins:
        try:
            brief = jobs[card['browse_id']].result(timeout=max(0.1, deadline - time.monotonic()))
        except Exception:
            continue
        if brief.get('subscribers') and not card.get('subscribers'):
            card['subscribers'] = brief['subscribers']
        card['has_songs'] = bool(brief.get('has_songs'))
        card['namesake'] = True
    # Within each name, one with songs before one without; everyone else
    # stays where YouTube put them.
    ordered: list[dict[str, Any]] = []
    for card in cards:
        group = groups[fold(card.get('name') or '')]
        if len(group) == 1:
            ordered.append(card)
        elif card is group[0]:
            ordered.extend(sorted(group, key=lambda c: c.get('has_songs') is False))
    cards[:] = ordered


def artist_brief(browse_id: str) -> dict[str, Any]:
    """An artist's name, picture and followers: one request, remembered."""

    full = _cache_get(f'artist::{browse_id}')
    if full is not None:
        return {
            'name': full.get('name', ''),
            'cover_url': full.get('cover_url', ''),
            'subscribers': full.get('subscribers', ''),
            'has_songs': bool(full.get('has_songs', full.get('songs'))),
            'plain_channel': bool(full.get('plain_channel')),
        }
    key = f'brief::{browse_id}'
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        data = _ytm().get_artist(browse_id)
    except KeyError:
        # A plain channel (see _channel_page): it has a page, not songs.
        page = artist(browse_id)
        out = {'name': page['name'], 'cover_url': page['cover_url'],
               'subscribers': '', 'has_songs': False, 'plain_channel': True}
        _cache_put(key, out)
        return out
    songs = data.get('songs') if isinstance(data.get('songs'), dict) else {}
    out = {
        'name': data.get('name', ''),
        'cover_url': _thumb(data),
        'subscribers': data.get('subscribers') or '',
        'has_songs': bool(songs.get('results') or songs.get('browseId')),
    }
    _cache_put(key, out)
    return out


def artists_of_video(video_id: str) -> list[dict[str, str]]:
    """Who YouTube Music credits on a recording, with their ids.

    A failure to reach YouTube is raised, as search_artists does. A page this
    cannot read (some music videos come back in a shape the library does not
    know) is an empty answer: the next song of the artist may do better.
    """

    from .providers import watch_track  # noqa: PLC0415

    key = f'credits::{video_id}'
    cached = _cache_get(key)
    if cached is not None:
        return cached
    track = watch_track(video_id)
    if track is None:
        return []
    out = _artists_list(track)
    _cache_put(key, out)
    return out


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


# A channel page lists this many uploads at most: enough to play through,
# and one page load stays a few seconds.
_CHANNEL_UPLOADS = 200


def _channel_listing(channel_id: str) -> dict[str, Any]:
    """The channel's own uploads list, read the way yt-dlp reads it.

    A flat listing is one page load and gives every upload (up to the cap),
    where a video search for the channel's name found only the few uploads
    that happened to rank. Kept apart so tests can answer it.
    """

    import yt_dlp  # noqa: PLC0415  (heavy; only a channel page needs it)

    from .streaming import _YDL_LOGGER, _cookiefile  # noqa: PLC0415

    opts: dict[str, Any] = {
        'quiet': True,
        'no_warnings': True,
        'logger': _YDL_LOGGER,
        'extract_flat': 'in_playlist',
        'playlistend': _CHANNEL_UPLOADS,
        'skip_download': True,
        'socket_timeout': 10,
    }
    jar = _cookiefile()
    if jar is not None:
        opts['cookiefile'] = jar
    url = f'https://www.youtube.com/channel/{channel_id}/videos'
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False) or {}


def _channel_page(channel_id: str) -> dict[str, Any]:
    """The page of a channel YouTube Music has no artist page for.

    Its name, picture and uploads come from the channel itself. Raises if the
    channel cannot be found at all, so a wrong id is still an error.
    """

    try:
        info = _channel_listing(channel_id)
    except Exception as exc:
        raise LookupError(f'no channel {channel_id}') from exc
    name = (info.get('channel') or info.get('uploader') or '').strip()
    if not name:
        raise LookupError(f'no channel {channel_id}')
    # The listing's pictures mix wide banners with the square avatar; the
    # page wants the avatar.
    pics = [t for t in info.get('thumbnails') or [] if isinstance(t, dict) and t.get('url')]
    avatar = next((t['url'] for t in pics if t.get('id') == 'avatar_uncropped'), '') or next(
        (t['url'] for t in pics if t.get('width') and t.get('width') == t.get('height')), ''
    )

    songs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for e in info.get('entries') or []:
        vid = e.get('id') if isinstance(e, dict) else None
        # Shelves and shorts tabs can show up as entries too: only an
        # 11-character video id is an upload that plays.
        if not vid or vid in seen or len(vid) != 11:
            continue
        seen.add(vid)
        thumbs = [t for t in e.get('thumbnails') or [] if isinstance(t, dict) and t.get('url')]
        cover = max(thumbs, key=lambda t: t.get('width') or 0)['url'] if thumbs else ''
        songs.append({
            'song_id': vid,
            'name': e.get('title') or '',
            'artists': [name],
            'artist_ids': [{'name': name, 'id': channel_id}],
            'album_name': '',
            'album_id': '',
            'video_id': vid,
            'like_status': '',
            'cover_url': cover or f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg',
            'duration': int(e.get('duration') or 0),
            'url': f'https://music.youtube.com/watch?v={vid}',
            'source': 'youtube',
        })

    return {
        'type': 'artist',
        'browse_id': channel_id,
        'name': name,
        'description': (info.get('description') or '').strip(),
        'cover_url': avatar,
        'subscribers': '',
        'monthly_listeners': '',
        'channel_id': channel_id,
        'songs': songs,
        'albums': [],
        'singles': [],
        'has_songs': False,
        'plain_channel': True,
    }


def artist(browse_id: str) -> dict[str, Any]:
    cache_key = f'artist::{browse_id}'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        data = _ytm().get_artist(browse_id)
    except KeyError:
        # A plain YouTube channel (a user who uploads, not a Music artist)
        # has no artist header, and ytmusicapi fails on it. Its uploads still
        # play, so give it a page of its own instead of an error.
        out = _channel_page(browse_id)
        _cache_put(cache_key, out)
        return out
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

    videos_section = data.get('videos') or {}
    videos_bid = (
        videos_section.get('browseId') if isinstance(videos_section, dict) else None
    )

    def _songs() -> list[dict[str, Any]]:
        # Prefer the artist's songs *playlist* (every track) over the
        # five-track inline preview.
        rows = _playlist_songs(songs_bid) if songs_bid else []
        rows = rows or _section_songs(songs_section)
        if rows:
            return rows
        # Some artists YouTube Music lists have videos and no songs at all
        # (a channel of music videos). Their page used to come up with
        # nothing to play; the videos are what they have.
        rows = _playlist_songs(videos_bid, 100) if videos_bid else []
        return rows or _section_songs(videos_section)

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
        'channel_id': data.get('channelId') or (browse_id if str(browse_id).startswith('UC') else ''),
        'songs': _done('songs', []),
        'albums': _done('albums', []),
        'singles': _done('singles', []),
        # Songs of their own, as against the videos standing in for them
        # (see _songs): what tells two artists of one name apart in search.
        'has_songs': bool(
            songs_bid or (isinstance(songs_section, dict) and songs_section.get('results'))
        ),
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


# ----- podcasts -------------------------------------------------------------
_SPOKEN = re.compile(r'(\d+)\s*(hr|h|hour|hours|min|m|minute|minutes|sec|s|seconds?)\b', re.I)


def _spoken_seconds(value: Any) -> int:
    """An episode's length as YouTube Music says it: "2 hr 43 min", or 1:02:03."""

    found = _parse_duration(value)
    if found or not isinstance(value, str):
        return found
    total = 0
    for amount, unit in _SPOKEN.findall(value):
        unit = unit.lower()
        total += int(amount) * (3600 if unit.startswith('h') else 60 if unit.startswith('m') else 1)
    return total


def podcast(browse_id: str, limit: int = 100) -> dict[str, Any]:
    """A podcast as a playlist of its episodes, the shape ``playlist`` gives.

    *browse_id* is YouTube Music's (MPSP and the episodes' playlist id) or the
    playlist id alone, as a youtube.com link has it.
    """

    bid = browse_id.strip()
    if not bid.startswith('MPSP'):
        bid = 'MPSP' + _clean_playlist_id(bid)
    cache_key = f'podcast::{bid}::{limit}'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    data = _ytm().get_podcast(bid, limit=limit)
    cover = _thumb(data)
    title = data.get('title') or ''
    author = data.get('author') or {}
    host = author.get('name', '') if isinstance(author, dict) else str(author or '')
    tracks: list[dict[str, Any]] = []
    for i, e in enumerate(data.get('episodes') or [], start=1):
        vid = e.get('videoId') if isinstance(e, dict) else None
        if not vid:
            continue
        tracks.append({
            'song_id': vid,
            'name': e.get('title', ''),
            'artists': [title or host],
            'artist_ids': [],
            'album_name': title,
            'album_id': '',
            'video_id': vid,
            'like_status': '',
            'cover_url': _thumb(e) or cover,
            'duration': _spoken_seconds(e.get('duration')),
            'track_number': i,
            'url': f'https://music.youtube.com/watch?v={vid}',
            'source': 'youtube',
            'podcast': True,
        })
    out = {
        'type': 'playlist',
        'podcast': True,
        'browse_id': bid,
        'name': title,
        'cover_url': cover,
        'description': data.get('description') or '',
        'author': host,
        'track_count': len(tracks),
        'tracks': tracks,
    }
    _cache_put(cache_key, out)
    return out


def _folded(text: str) -> str:
    return re.sub(r'[^\w]+', ' ', (text or '').casefold()).strip()


def find_podcast(name: str) -> Optional[dict[str, Any]]:
    """The podcast called *name* on YouTube Music: ``{browse_id, name}``, or None."""

    want = _folded(name)
    if not want:
        return None
    rows = [
        r for r in _ytm().search(name, filter='podcasts', limit=10) or []
        if isinstance(r, dict) and r.get('browseId')
    ]
    # The same name first; else one name the start of the other ("The Daily"
    # and "The Daily (Podcast)"), never a word or two in common.
    for close in (False, True):
        for r in rows:
            got = _folded(r.get('title', ''))
            if got == want or (close and min(len(got), len(want)) >= 6 and (got.startswith(want) or want.startswith(got))):
                return {'browse_id': r['browseId'], 'name': r.get('title', '')}
    return None


def find_episode(show: str, title: str) -> Optional[dict[str, Any]]:
    """An episode of *show* called *title* on YouTube Music, as a song."""

    want_show, want_title = _folded(show), _folded(title)
    if not want_title:
        return None
    for r in _ytm().search(f'{show} {title}'.strip(), filter='episodes', limit=10) or []:
        if not isinstance(r, dict) or not r.get('videoId'):
            continue
        pod = r.get('podcast') or {}
        got_show = _folded(pod.get('name', '') if isinstance(pod, dict) else '')
        got_title = _folded(r.get('title', ''))
        same_show = not want_show or got_show == want_show or want_show in got_show or got_show in want_show
        same_title = want_title in got_title or got_title in want_title
        if same_show and same_title:
            vid = r['videoId']
            return {
                'song_id': vid,
                'video_id': vid,
                'name': r.get('title', ''),
                'artists': [pod.get('name', '') if isinstance(pod, dict) else show],
                'album_name': pod.get('name', '') if isinstance(pod, dict) else show,
                'cover_url': _thumb(r),
                'duration': _spoken_seconds(r.get('duration')),
                'url': f'https://music.youtube.com/watch?v={vid}',
                'source': 'youtube',
                'podcast': True,
            }
    return None


def playlist(browse_id: str, limit: int = 200) -> dict[str, Any]:
    pid = _clean_playlist_id(browse_id)
    if pid.startswith('MPSP'):
        return podcast(pid, limit=min(limit, 100))
    cache_key = f'playlist::{pid}::{limit}'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        data = _ytm().get_playlist(pid, limit=limit)
    except KeyError:
        # A podcast's episodes are a playlist YouTube Music will not open as
        # one (a youtube.com link to a show): opened as the podcast it is.
        if pid.startswith('PL'):
            return podcast(pid, limit=min(limit, 100))
        raise
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
