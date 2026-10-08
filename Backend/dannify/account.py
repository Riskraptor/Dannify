"""YouTube Music account: sign-in, personalized feeds, likes.

Signing in is a real Google login shown in a WebView2 window (see
``Backend/desktop.py``). We keep the resulting ``youtube.com`` cookies and
turn them into ytmusicapi's "browser" auth, which unlocks:

* a personalized home feed, liked songs and library playlists,
* liking / unliking tracks straight from the player,
* yt-dlp requests that carry the session, which is what keeps YouTube from
  answering "Sign in to confirm you're not a bot" on downloads.

The ``Authorization`` header is a SAPISIDHASH that ytmusicapi recomputes per
request from the cookie jar, so nothing here expires on its own: the cookies
are refreshed whenever the user opens the sign-in window again.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Optional

import requests
from loguru import logger
from ytmusicapi import YTMusic

ORIGIN = 'https://music.youtube.com'
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
)
# Everything Google's endpoints validate. The jar is sent verbatim.
_COOKIE_NAMES = (
    '__Secure-3PAPISID',
    '__Secure-1PAPISID',
    'SAPISID',
    'APISID',
    'SID',
    'HSID',
    'SSID',
    '__Secure-1PSID',
    '__Secure-3PSID',
    '__Secure-1PSIDTS',
    '__Secure-3PSIDTS',
    '__Secure-1PSIDCC',
    '__Secure-3PSIDCC',
    'SIDCC',
    'LOGIN_INFO',
    'PREF',
    'SOCS',
    'VISITOR_INFO1_LIVE',
    'YSC',
)


# ytmusicapi never passes a timeout to requests, so a stalled socket parks a
# worker thread for as long as the OS keeps the connection open. Every client
# gets a session that supplies one, which is what makes the per-facet
# timeouts in explorer.search actually mean something.
REQUEST_TIMEOUT = 12.0


class _TimeoutSession(requests.Session):
    def request(self, *args, **kwargs):  # noqa: ANN002, ANN003
        kwargs.setdefault('timeout', REQUEST_TIMEOUT)
        return super().request(*args, **kwargs)


class NotSignedIn(RuntimeError):
    """Raised when an account-only call is made while signed out."""


_lock = threading.Lock()
_local = threading.local()
_state: dict[str, Any] = {
    'cookies': {},
    'profile': {},
    'path': None,
    'gen': 0,  # bumped on sign in/out so thread-local clients rebuild
    'visitor_id': '',  # shared across clients: saves a round trip each
    'visitor_gen': -1,
}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
# The sign-in is kept encrypted to this Windows account on this PC, the same
# way saved music is. It is a live Google session: whoever has these cookies
# is signed in as this person, to YouTube and to everything else on the
# account. Earlier versions wrote them to account.json in plain text, where
# anything that could read a file in AppData could lift them.
_FILE = 'account.dat'
_LEGACY = 'account.json'


def init(data_dir: Path) -> None:
    """Load a previously saved session (called once at startup)."""

    from . import vault  # noqa: PLC0415

    path = Path(data_dir) / _FILE
    legacy = Path(data_dir) / _LEGACY
    _state['path'] = path
    data = None
    try:
        if path.is_file():
            data = json.loads(vault._unprotect(path.read_bytes()).decode('utf-8'))
        elif legacy.is_file():
            data = json.loads(legacy.read_text(encoding='utf-8'))
    except Exception:
        logger.opt(exception=True).debug('Could not read saved account')
        data = None
    if not isinstance(data, dict):
        return
    cookies = data.get('cookies') or {}
    if not (isinstance(cookies, dict) and cookies.get('__Secure-3PAPISID')):
        return
    _state['cookies'] = cookies
    _state['profile'] = data.get('profile') or {}
    _state['gen'] += 1
    logger.info(
        'YouTube Music account restored ({})',
        _state['profile'].get('name') or 'signed in',
    )
    # A session read from the old plain file is written encrypted, and the
    # plain one goes only once the encrypted copy reads back the same.
    if legacy.is_file() and _save() and _stored() == data.get('cookies'):
        try:
            legacy.unlink()
        except OSError:
            logger.opt(exception=True).debug('Could not remove the old account file')


def _stored() -> Optional[dict]:
    """The cookies as they are on disk now, or None."""

    from . import vault  # noqa: PLC0415

    path = _state.get('path')
    try:
        blob = vault._unprotect(Path(path).read_bytes())
        return (json.loads(blob.decode('utf-8')) or {}).get('cookies')
    except Exception:
        return None


def _save() -> bool:
    """Write the session, encrypted. Returns whether it was written."""

    from . import vault  # noqa: PLC0415

    path = _state.get('path')
    if not path:
        return False
    try:
        if _state['cookies']:
            raw = json.dumps(
                {'cookies': _state['cookies'], 'profile': _state['profile']}
            ).encode('utf-8')
            blob = vault._protect(raw)
            if vault._unprotect(blob) != raw:
                return False
            # Flushed to disk before the rename, as the song keys are: a power
            # cut straight after the rename could otherwise leave an empty
            # file, and an empty sign-in is a sign-out nobody asked for.
            vault._atomic_write(Path(path), blob)
        else:
            Path(path).unlink(missing_ok=True)
            # Signed out: an old plain copy must not outlive the session.
            Path(path).with_name(_LEGACY).unlink(missing_ok=True)
        return True
    except Exception:
        logger.opt(exception=True).debug('Could not persist account')
        return False


# ---------------------------------------------------------------------------
# Auth plumbing
# ---------------------------------------------------------------------------
def _sapisid_hash(sapisid: str) -> str:
    ts = str(int(time.time()))
    digest = hashlib.sha1(f'{ts} {sapisid} {ORIGIN}'.encode()).hexdigest()
    return f'SAPISIDHASH {ts}_{digest}'


def auth_headers() -> Optional[dict[str, str]]:
    cookies = _state['cookies']
    sapisid = cookies.get('__Secure-3PAPISID') or cookies.get('SAPISID')
    if not sapisid:
        return None
    jar = dict(cookies)
    jar.setdefault('__Secure-3PAPISID', sapisid)
    jar.setdefault('SOCS', 'CAI')
    return {
        'Cookie': '; '.join(f'{k}={v}' for k, v in jar.items()),
        # ytmusicapi re-signs this on every request; it only has to be present.
        'Authorization': _sapisid_hash(sapisid),
        'X-Goog-AuthUser': '0',
        'origin': ORIGIN,
        'x-origin': ORIGIN,
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'en-US,en;q=0.9',
        'User-Agent': USER_AGENT,
    }


def is_signed_in() -> bool:
    return bool(_state['cookies'].get('__Secure-3PAPISID'))


def profile() -> dict[str, Any]:
    return dict(_state['profile'])


def status() -> dict[str, Any]:
    return {'signed_in': is_signed_in(), 'profile': profile()}


def client(require_auth: bool = False) -> YTMusic:
    """A YTMusic client for the calling thread.

    ytmusicapi mutates its header dict per request, so every worker thread
    gets its own instance instead of sharing one. The visitor id (normally
    an extra HTTP round trip per instance) is fetched once and handed to
    every later client, which is what keeps parallel searches cheap.
    """

    gen = _state['gen']
    cached = getattr(_local, 'client', None)
    if cached is not None and getattr(_local, 'gen', -1) == gen:
        if not require_auth or getattr(_local, 'authed', False):
            return cached

    headers = auth_headers()
    visitor = _state.get('visitor_id') if _state.get('visitor_gen') == gen else None
    session = _TimeoutSession()
    if headers:
        if visitor:
            headers['X-Goog-Visitor-Id'] = visitor  # skips the lookup entirely
        instance = YTMusic(auth=headers, requests_session=session)
        _local.authed = True
    else:
        if require_auth:
            raise NotSignedIn('Sign in with Google to use this feature')
        instance = YTMusic(requests_session=session)
        _local.authed = False
        if visitor:
            try:
                from requests.structures import CaseInsensitiveDict
                from ytmusicapi.helpers import initialize_headers

                seeded = CaseInsensitiveDict(initialize_headers())
                seeded['X-Goog-Visitor-Id'] = visitor
                # Pre-fill the cached_property so no visitor-id request runs.
                instance.__dict__['base_headers'] = seeded
            except Exception:
                logger.opt(exception=True).debug('visitor id reuse failed')

    if not visitor:
        try:
            found = instance.base_headers.get('X-Goog-Visitor-Id')
            if found:
                _state['visitor_id'] = found
                _state['visitor_gen'] = gen
        except Exception:
            logger.opt(exception=True).debug('could not read visitor id')

    _local.client = instance
    _local.gen = gen
    return instance


def cookie_dict() -> dict[str, str]:
    return dict(_state['cookies'])


def ydl_cookiefile() -> Optional[io.StringIO]:
    """An in-memory Netscape cookie jar for yt-dlp (None when signed out).

    Passing the signed-in session to yt-dlp is what stops YouTube's
    "confirm you're not a bot" wall. A fresh stream is required per
    YoutubeDL instance because yt-dlp writes the jar back on close.
    """

    cookies = _state['cookies']
    if not cookies:
        return None
    expires = int(time.time()) + 365 * 24 * 3600
    lines = ['# Netscape HTTP Cookie File', '']
    for domain in ('.youtube.com', '.google.com'):
        for name, value in cookies.items():
            lines.append(f'{domain}\tTRUE\t/\tTRUE\t{expires}\t{name}\t{value}')
    return io.StringIO('\n'.join(lines) + '\n')


# ---------------------------------------------------------------------------
# Sign in / out
# ---------------------------------------------------------------------------
def sign_in(cookies: dict[str, str]) -> dict[str, Any]:
    """Validate a cookie jar from the login window and store it."""

    keep = {
        name: value
        for name, value in (cookies or {}).items()
        if name in _COOKIE_NAMES and value
    }
    if not (keep.get('__Secure-3PAPISID') or keep.get('SAPISID')):
        raise NotSignedIn('No Google session found: the sign-in was not completed')

    with _lock:
        previous = _state['cookies']
        _state['cookies'] = keep
        _state['gen'] += 1
    try:
        info = (
            YTMusic(auth=auth_headers(), requests_session=_TimeoutSession())
            .get_account_info()
            or {}
        )
    except Exception as exc:
        with _lock:
            _state['cookies'] = previous
            _state['gen'] += 1
        logger.opt(exception=True).info('Sign-in validation failed')
        raise NotSignedIn(f'Could not verify the Google session: {exc}') from exc

    _state['profile'] = {
        'name': info.get('accountName') or '',
        'handle': info.get('channelHandle') or '',
        'photo': info.get('accountPhotoUrl') or '',
    }
    _save()
    logger.log('SUCCESS', 'Signed in to YouTube Music as {}', _state['profile']['name'])
    return status()


def sign_out() -> dict[str, Any]:
    with _lock:
        _state['cookies'] = {}
        _state['profile'] = {}
        _state['gen'] += 1
    _save()
    # Whoever signs in next follows their own channels.
    _keep_channels([])
    logger.info('Signed out of YouTube Music')
    return status()


# ---------------------------------------------------------------------------
# Normalizers: every item the UI sees uses the same song/card shapes
# ---------------------------------------------------------------------------
def _thumb(item: dict[str, Any], size: int = 544) -> str:
    thumbs = item.get('thumbnails') or []
    if not thumbs:
        return ''
    url = thumbs[-1].get('url', '')
    return _resize_thumb(url, size)


def _resize_thumb(url: str, size: int = 544) -> str:
    """Ask Google's CDN for exactly the size we render (smaller + faster)."""

    if not url:
        return url
    import re

    if '=w' in url and '-h' in url:
        return re.sub(r'=w\d+-h\d+[^&]*$', f'=w{size}-h{size}-l90-rj', url)
    if '=s' in url:
        return re.sub(r'=s\d+[^&]*$', f'=s{size}', url)
    return url


def _artists(item: dict[str, Any]) -> list[dict[str, str]]:
    out = []
    for a in item.get('artists') or []:
        if isinstance(a, dict) and a.get('name'):
            out.append({'name': a['name'], 'id': a.get('id') or ''})
    return out


def song_from_item(item: dict[str, Any]) -> Optional[dict[str, Any]]:
    """YT Music track/quick-pick → Dannify song dict."""

    video_id = item.get('videoId')
    if not video_id:
        return None
    album = item.get('album') or {}
    artists = _artists(item)
    duration = item.get('duration_seconds') or 0
    if not duration and isinstance(item.get('duration'), str):
        parts = [p for p in item['duration'].split(':') if p.isdigit()]
        if len(parts) == 2:
            duration = int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            duration = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return {
        'song_id': video_id,
        'video_id': video_id,
        'name': item.get('title', ''),
        'artists': [a['name'] for a in artists],
        'artist_ids': artists,
        'album_name': album.get('name', '') if isinstance(album, dict) else '',
        'album_id': album.get('id', '') if isinstance(album, dict) else '',
        'cover_url': _thumb(item),
        'duration': duration,
        'url': f'https://music.youtube.com/watch?v={video_id}',
        'explicit': bool(item.get('isExplicit')),
        'like_status': item.get('likeStatus') or '',
        'source': 'youtube',
    }


def card_from_item(item: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Home-feed entry → song / album / playlist / artist card."""

    if item.get('videoId'):
        song = song_from_item(item)
        if song:
            song['type'] = 'song'
        return song
    if item.get('playlistId') and not item.get('browseId'):
        return {
            'type': 'playlist',
            'browse_id': item['playlistId'],
            'name': item.get('title', ''),
            'cover_url': _thumb(item, 400),
            'author': ', '.join(
                a.get('name', '') for a in (item.get('author') or []) if isinstance(a, dict)
            )
            or item.get('description', ''),
            'item_count': str(item.get('count') or ''),
        }
    browse_id = item.get('browseId') or ''
    if browse_id.startswith('UC') or item.get('subscribers'):
        return {
            'type': 'artist',
            'browse_id': browse_id,
            'name': item.get('title', ''),
            'cover_url': _thumb(item, 400),
            'subscribers': item.get('subscribers') or '',
        }
    if browse_id:
        return {
            'type': 'album',
            'browse_id': browse_id,
            'name': item.get('title', ''),
            'cover_url': _thumb(item, 400),
            'artists': [a['name'] for a in _artists(item)],
            'artist_ids': _artists(item),
            'year': str(item.get('year') or ''),
            'album_type': item.get('type') or '',
        }
    return None


# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------
def home(limit: int = 6) -> list[dict[str, Any]]:
    """The YouTube Music home feed: personalized once signed in."""

    rows = client().get_home(limit=limit)
    sections = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        items = []
        for entry in row.get('contents') or []:
            if not isinstance(entry, dict):
                continue
            card = card_from_item(entry)
            if card:
                items.append(card)
        if items:
            sections.append({'title': row.get('title', ''), 'items': items})
    return sections


def liked_songs(limit: int = 250) -> list[dict[str, Any]]:
    data = client(require_auth=True).get_liked_songs(limit=limit) or {}
    out = []
    for track in data.get('tracks') or []:
        song = song_from_item(track)
        if song:
            out.append(song)
    return out


def library_playlists(limit: int = 50) -> list[dict[str, Any]]:
    rows = client(require_auth=True).get_library_playlists(limit=limit) or []
    out = []
    for row in rows:
        if not isinstance(row, dict) or not row.get('playlistId'):
            continue
        out.append(
            {
                'type': 'playlist',
                'browse_id': row['playlistId'],
                'name': row.get('title', ''),
                'cover_url': _thumb(row, 400),
                'item_count': str(row.get('count') or ''),
                'author': ', '.join(
                    a.get('name', '') for a in (row.get('author') or []) if isinstance(a, dict)
                ),
            }
        )
    return out


_CHANNEL = re.compile(r'^UC[A-Za-z0-9_-]{22}$')
_VIDEO = re.compile(r'^[A-Za-z0-9_-]{11}$')


# Plain YouTube channels the account followed from Dannify. YouTube Music's
# library lists only Music artists, so a followed channel (a preacher, a
# podcaster) would vanish from the list on the next refresh and its page
# would offer "Follow" again. Remembered here, beside the session.
_CHANNELS_FILE = 'followed_channels.json'


def _channels_path() -> Optional[Path]:
    path = _state.get('path')
    return Path(path).parent / _CHANNELS_FILE if path else None


def _followed_channels() -> list[dict[str, Any]]:
    path = _channels_path()
    try:
        rows = json.loads(path.read_text(encoding='utf-8')) if path and path.is_file() else []
    except (OSError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict) and _CHANNEL.match(str(r.get('browse_id') or ''))]


def _keep_channels(rows: list[dict[str, Any]]) -> None:
    path = _channels_path()
    if not path:
        return
    try:
        if rows:
            path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        elif path.is_file():
            path.unlink()
    except OSError:
        logger.opt(exception=True).debug('could not keep the followed channels')


def _note_channel(channel_id: str, on: bool) -> None:
    """Remember (or forget) a followed channel that has no artist page."""

    rows = [r for r in _followed_channels() if r['browse_id'] != channel_id]
    if on:
        from . import explorer  # noqa: PLC0415

        try:
            brief = explorer.artist_brief(channel_id)
        except Exception:
            logger.opt(exception=True).debug('could not look up {}', channel_id)
            return
        if not brief.get('plain_channel'):
            return  # a Music artist: the library lists it already
        rows.insert(0, {
            'type': 'artist',
            'browse_id': channel_id,
            'name': brief.get('name') or '',
            'cover_url': brief.get('cover_url') or '',
            'subscribers': '',
        })
    _keep_channels(rows)


def subscriptions(limit: int = 100) -> list[dict[str, Any]]:
    """The artists (and plain channels) the account follows."""

    rows = client(require_auth=True).get_library_subscriptions(limit=limit) or []
    out = []
    for row in rows:
        if not isinstance(row, dict) or not row.get('browseId'):
            continue
        out.append(
            {
                'type': 'artist',
                'browse_id': row['browseId'],
                'name': row.get('artist') or row.get('title') or '',
                'cover_url': _thumb(row, 240),
                'subscribers': str(row.get('subscribers') or ''),
            }
        )
    listed = {a['browse_id'] for a in out}
    out.extend(c for c in _followed_channels() if c['browse_id'] not in listed)
    return out


def follow(channel_id: str, on: bool) -> dict[str, Any]:
    """Follow or stop following an artist (their channel) on YouTube Music."""

    if not _CHANNEL.match(str(channel_id or '')):
        raise ValueError('not an artist channel')
    yt = client(require_auth=True)
    if on:
        yt.subscribe_artists([channel_id])
    else:
        yt.unsubscribe_artists([channel_id])
    _note_channel(channel_id, bool(on))
    return {'channel_id': channel_id, 'following': bool(on)}


def history() -> list[dict[str, Any]]:
    """What the account played lately on YouTube Music, newest first."""

    out = []
    seen: set[str] = set()
    for track in client(require_auth=True).get_history() or []:
        song = song_from_item(track)
        if song and song['song_id'] not in seen:
            seen.add(song['song_id'])
            out.append(song)
    return out


def add_to_playlist(playlist_id: str, video_ids: list[str]) -> dict[str, Any]:
    """Add songs to one of the account's playlists on YouTube Music."""

    ids = [v for v in video_ids if _VIDEO.match(str(v or ''))][:200]
    if not ids:
        raise ValueError('no songs to add')
    pid = str(playlist_id or '')
    if pid.startswith('VL'):
        pid = pid[2:]
    if not pid or pid in ('LM', 'SE'):
        raise ValueError('not a playlist that can be added to')
    result = client(require_auth=True).add_playlist_items(pid, ids, duplicates=False)
    status = result.get('status') if isinstance(result, dict) else None
    if status and 'SUCCEEDED' not in str(status):
        raise RuntimeError(f'YouTube Music said {status}')
    return {'playlist_id': pid, 'added': len(ids)}


def add_history(video_id: str) -> bool:
    """Tell YouTube Music this song was listened to, as its own player does,
    so the account's history and recommendations include what is played in
    Dannify."""

    if not _VIDEO.match(str(video_id or '')):
        return False
    yt = client(require_auth=True)
    song = yt.get_song(video_id)
    if not isinstance(song, dict) or not song.get('playbackTracking'):
        return False
    response = yt.add_history_item(song)
    return getattr(response, 'status_code', 0) in (200, 204)


def rate(video_id: str, liked: bool) -> dict[str, Any]:
    """Like / unlike a song on the user's YouTube Music account."""

    if not video_id:
        raise ValueError('video_id required')
    rating = 'LIKE' if liked else 'INDIFFERENT'
    client(require_auth=True).rate_song(video_id, rating)
    return {'video_id': video_id, 'liked': bool(liked)}


def radio(video_id: str, limit: int = 30) -> list[dict[str, Any]]:
    """Endless mix for a track (used for autoplay when the queue runs dry)."""

    data = client().get_watch_playlist(videoId=video_id, radio=True, limit=limit) or {}
    out = []
    for track in data.get('tracks') or []:
        song = song_from_item(track)
        if song and song['song_id'] != video_id:
            out.append(song)
    return out
