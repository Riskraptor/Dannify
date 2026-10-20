"""Signing in to Spotify, and what that lets Dannify show: the person's
playlists, Liked Songs, saved albums, followed artists, top songs and artists,
and what they played lately. Every song plays through YouTube Music, matched
as it plays, the same way a pasted Spotify link does.

Signing in is Spotify's own way for an app on someone's computer: the
authorization code flow with PKCE, which needs no secret in the app. The
browser opens Spotify's page; Spotify sends the person back to a one-time
page that a tiny server here listens on (127.0.0.1, a port of its own, for ten
minutes at most, and for that one answer only). What comes back is checked
against a value made for this sign-in alone, so no other page can sign
someone in. The refresh token is kept sealed the way the Google sign-in is
(vault._protect); the access token lives in memory for its hour.

Spotify's rules for an app like this (2026): its owner needs Premium, and it
can sign in five people the owner names in the Spotify dashboard. Anyone
else can paste the Client ID of a Spotify app of their own (Settings,
Accounts), which this keeps alongside the sign-in.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlencode, urlsplit

import requests
from loguru import logger

# Dannify's own app on Spotify's developer dashboard. Not a secret: a PKCE
# client has none, and every copy carries this.
DEFAULT_CLIENT_ID = ''



def _base(env: str, default: str) -> str:
    # A stand-in Spotify for trying the app out, on this computer only: an
    # address anywhere else is ignored.
    value = os.environ.get(env, '').strip().rstrip('/')
    return value if value.startswith('http://127.0.0.1:') else default


_ACCOUNTS = _base('DANNIFY_SPOTIFY_ACCOUNTS', 'https://accounts.spotify.com')
AUTHORIZE_URL = _ACCOUNTS + '/authorize'
TOKEN_URL = _ACCOUNTS + '/api/token'
API = _base('DANNIFY_SPOTIFY_API', 'https://api.spotify.com') + '/v1'
# Registered in the dashboard as http://127.0.0.1/callback: Spotify lets the
# port of a loopback address change from one sign-in to the next.
CALLBACK_PATH = '/callback'
SCOPES = ' '.join((
    'user-read-private',
    'user-library-read',
    'playlist-read-private',
    'playlist-read-collaborative',
    'user-follow-read',
    'user-top-read',
    'user-read-recently-played',
))

_FILE = 'spotify.dat'
_TIMEOUT = 15
# How long the sign-in page waits for the person.
LOGIN_WINDOW = 10 * 60
# What is read from Spotify is kept this long, so going back and forth
# between its pages costs nothing.
CACHE_SECONDS = 5 * 60
# The most songs read from one list (Liked Songs can run to tens of
# thousands; the first few thousand are what anyone scrolls).
MOST_SONGS = 2000
MOST_PLAYLISTS = 500

# Why Spotify is not usable, for Settings to say: '' when it is.
NOT_CONFIGURED = 'not_configured'  # no Client ID anywhere
NOT_ALLOWED = 'not_allowed'  # this account is not on the app's list
EXPIRED = 'expired'  # the sign-in was revoked or ran out
DENIED = 'denied'  # the person said no on Spotify's page
FAILED = 'failed'  # anything else that went wrong signing in


class SpotifyError(RuntimeError):
    def __init__(self, reason: str, message: str = '') -> None:
        super().__init__(message or reason)
        self.reason = reason


_lock = threading.RLock()
_state: dict[str, Any] = {
    'dir': None,
    'client_id': '',  # one of the person's own, when they gave one
    'refresh': '',
    'access': '',
    'expires': 0.0,
    'scope': '',
    'user': {},
    'error': '',
    'login': None,  # the sign-in waiting for its answer
}
_cache: dict[str, tuple[float, Any]] = {}
# Replaceable in tests: how Spotify is asked.
_post: Callable[..., requests.Response] = requests.post
_get: Callable[..., requests.Response] = requests.get


# ---------------------------------------------------------------------------
# Kept between runs
# ---------------------------------------------------------------------------
def init(data_dir: Path) -> None:
    """Load the sign-in, if there is one. Nothing is asked of Spotify."""

    from . import vault  # noqa: PLC0415

    folder = Path(data_dir)
    with _lock:
        _state.update(dir=folder, client_id='', refresh='', access='', expires=0.0,
                      scope='', user={}, error='')
        _cache.clear()
        try:
            data = json.loads(vault._unprotect((folder / _FILE).read_bytes()).decode('utf-8'))
        except FileNotFoundError:
            return
        except Exception:
            logger.opt(exception=True).warning('could not read the Spotify sign-in')
            return
        if isinstance(data, dict):
            _state['client_id'] = str(data.get('client_id') or '')[:64]
            _state['refresh'] = str(data.get('refresh') or '')
            _state['scope'] = str(data.get('scope') or '')
            user = data.get('user')
            _state['user'] = user if isinstance(user, dict) else {}


def _save() -> bool:
    from . import vault  # noqa: PLC0415

    folder = _state['dir']
    if folder is None:
        return False
    path = folder / _FILE
    try:
        if not (_state['refresh'] or _state['client_id']):
            path.unlink(missing_ok=True)
            return True
        raw = json.dumps({
            'client_id': _state['client_id'],
            'refresh': _state['refresh'],
            'scope': _state['scope'],
            'user': _state['user'],
        }).encode('utf-8')
        blob = vault._protect(raw)
        if vault._unprotect(blob) != raw:
            return False
        folder.mkdir(parents=True, exist_ok=True)
        vault._atomic_write(path, blob)
        return True
    except Exception:
        logger.opt(exception=True).warning('could not keep the Spotify sign-in')
        return False


def client_id() -> str:
    return _state['client_id'] or DEFAULT_CLIENT_ID


def status() -> dict[str, Any]:
    with _lock:
        login = _state['login']
        return {
            'configured': bool(client_id()),
            'own_app': bool(_state['client_id']),
            'connected': bool(_state['refresh']),
            'signing_in': bool(login and not login.get('done')),
            'user': dict(_state['user']),
            'error': _state['error'],
        }


def set_client_id(value: str) -> dict[str, Any]:
    """Use the person's own Spotify app ('' goes back to Dannify's).

    A different app cannot use the other one's sign-in, so it ends it.
    """

    value = str(value or '').strip()
    if value and (len(value) != 32 or not all(c in '0123456789abcdef' for c in value.lower())):
        raise ValueError('a Spotify Client ID is 32 letters and digits')
    with _lock:
        if value.lower() != _state['client_id']:
            _forget_sign_in()
        _state['client_id'] = value.lower()
        _state['error'] = ''
        _save()
    return status()


def _forget_sign_in() -> None:
    _state.update(refresh='', access='', expires=0.0, scope='', user={})
    _cache.clear()


def disconnect() -> dict[str, Any]:
    with _lock:
        _stop_login()
        _forget_sign_in()
        _state['error'] = ''
        _save()
    return status()


# ---------------------------------------------------------------------------
# Signing in
# ---------------------------------------------------------------------------
def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


def begin() -> str:
    """Start signing in: the address of Spotify's page to open in the browser.

    The page sends the person back here, to a server listening for that one
    answer for ten minutes.
    """

    cid = client_id()
    if not cid:
        raise SpotifyError(NOT_CONFIGURED)
    with _lock:
        _stop_login()
        verifier = secrets.token_urlsafe(72)[:96]
        state = secrets.token_urlsafe(24)
        server = ThreadingHTTPServer(('127.0.0.1', 0), _CallbackHandler)
        server.daemon_threads = True
        redirect = f'http://127.0.0.1:{server.server_address[1]}{CALLBACK_PATH}'
        login = {
            'verifier': verifier,
            'state': state,
            'redirect': redirect,
            'client_id': cid,
            'server': server,
            'started': time.monotonic(),
            'done': False,
        }
        server.dannify_login = login  # type: ignore[attr-defined]
        _state['login'] = login
        _state['error'] = ''
    threading.Thread(target=server.serve_forever, name='spotify-sign-in', daemon=True).start()
    timer = threading.Timer(LOGIN_WINDOW, lambda: _expire(login))
    timer.daemon = True
    timer.start()
    return AUTHORIZE_URL + '?' + urlencode({
        'client_id': cid,
        'response_type': 'code',
        'redirect_uri': redirect,
        'code_challenge_method': 'S256',
        'code_challenge': _challenge(verifier),
        'state': state,
        'scope': SCOPES,
    })


def _expire(login: dict[str, Any]) -> None:
    with _lock:
        if _state['login'] is login and not login['done']:
            _stop_login()


def _stop_login() -> None:
    login = _state['login']
    _state['login'] = None
    if login and login.get('server'):
        server = login['server']
        login['server'] = None
        # Not from the server's own thread: shutdown waits for it. Then the
        # listening socket itself is closed, not left for the collector.
        def stop() -> None:
            server.shutdown()
            server.server_close()

        threading.Thread(target=stop, daemon=True).start()


def finish(login: dict[str, Any], query: dict[str, str]) -> tuple[bool, str]:
    """Spotify's answer on the callback page: (signed in, why not)."""

    given = query.get('state', '')
    if not hmac.compare_digest(given.encode(), login['state'].encode()):
        return False, 'mismatch'
    with _lock:
        if login['done'] or _state['login'] is not login:
            return False, 'mismatch'
        login['done'] = True
    if query.get('error'):
        reason = DENIED if query['error'] == 'access_denied' else FAILED
        with _lock:
            _state['error'] = reason
        return False, reason
    code = query.get('code', '')
    if not code:
        return False, FAILED
    try:
        res = _post(TOKEN_URL, data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': login['redirect'],
            'client_id': login['client_id'],
            'code_verifier': login['verifier'],
        }, timeout=_TIMEOUT)
        if res.status_code != 200:
            logger.warning('Spotify would not finish the sign-in: {} {}', res.status_code, res.text[:200])
            with _lock:
                _state['error'] = FAILED
            return False, FAILED
        _take_tokens(res.json())
        user = _api('/me')
    except SpotifyError as exc:
        with _lock:
            _forget_sign_in()
            _state['error'] = exc.reason
            _save()
        return False, exc.reason
    except Exception:
        logger.opt(exception=True).warning('Spotify sign-in failed')
        with _lock:
            _forget_sign_in()
            _state['error'] = FAILED
        return False, FAILED
    images = user.get('images') or []
    with _lock:
        _state['user'] = {
            'id': str(user.get('id') or ''),
            'name': str(user.get('display_name') or user.get('id') or ''),
            'image': str((images[0] or {}).get('url') or '') if images else '',
        }
        _state['error'] = ''
        _save()
    logger.info('Signed in to Spotify')
    return True, ''


def _take_tokens(data: dict[str, Any]) -> None:
    with _lock:
        _state['access'] = str(data.get('access_token') or '')
        _state['expires'] = time.time() + float(data.get('expires_in') or 3600) - 60
        if data.get('refresh_token'):
            _state['refresh'] = str(data['refresh_token'])
        if data.get('scope'):
            _state['scope'] = str(data['scope'])
    if not _state['access']:
        raise SpotifyError(FAILED, 'no access token')


def _access_token() -> str:
    with _lock:
        if _state['access'] and time.time() < _state['expires']:
            return _state['access']
        refresh = _state['refresh']
    if not refresh:
        raise SpotifyError(EXPIRED)
    res = _post(TOKEN_URL, data={
        'grant_type': 'refresh_token',
        'refresh_token': refresh,
        'client_id': client_id(),
    }, timeout=_TIMEOUT)
    if res.status_code in (400, 401):
        # Revoked on Spotify's side, or from another app: sign in again.
        with _lock:
            _forget_sign_in()
            _state['error'] = EXPIRED
            _save()
        raise SpotifyError(EXPIRED)
    res.raise_for_status()
    _take_tokens(res.json())
    with _lock:
        _save()
        return _state['access']


def _api(path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """GET from Spotify's API, signed in, with the token kept fresh."""

    url = path if path.startswith('http') else API + path
    for attempt in range(3):
        token = _access_token()
        res = _get(url, params=params, headers={'Authorization': f'Bearer {token}'}, timeout=_TIMEOUT)
        if res.status_code == 401 and attempt == 0:
            with _lock:
                _state['access'] = ''
            continue
        if res.status_code == 429 and attempt < 2:
            wait = min(5.0, float(res.headers.get('Retry-After') or 1))
            time.sleep(wait)
            continue
        if res.status_code == 403:
            text = res.text[:300].lower()
            if 'registered' in text or 'developer.spotify.com' in text:
                with _lock:
                    _state['error'] = NOT_ALLOWED
                raise SpotifyError(NOT_ALLOWED)
            raise SpotifyError('forbidden', res.text[:200])
        if res.status_code == 404:
            raise SpotifyError('not_found')
        res.raise_for_status()
        return res.json() if res.content else {}
    raise SpotifyError(FAILED, 'Spotify kept saying no')


# ---------------------------------------------------------------------------
# The one-time page Spotify sends the person back to
# ---------------------------------------------------------------------------
_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dannify</title><style>
:root{color-scheme:dark}body{margin:0;min-height:100vh;display:grid;place-items:center;
background:radial-gradient(80% 60% at 50% 0%,#1db95433,transparent),#0c0c0e;color:#fff;
font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{text-align:center;padding:40px 28px;max-width:420px}
.mark{width:64px;height:64px;border-radius:18px;margin:0 auto 18px;display:grid;place-items:center;
font-size:30px;background:{tone};color:#000}h1{font-size:24px;margin:0 0 8px}p{margin:0;color:#ffffffb3}
</style></head><body><main><div class="mark">{mark}</div><h1>{title}</h1><p>{text}</p></main>
<script>setTimeout(function(){window.close()},2500)</script></body></html>"""

_PAGES = {
    '': ('#1ed760', '&#10003;', 'Connected to Spotify', 'You can close this tab and go back to Dannify.'),
    DENIED: ('#f3f3f3', '&#8635;', 'Spotify was not connected',
             'Nothing was shared. You can try again from Dannify whenever you like.'),
    NOT_ALLOWED: ('#ffb020', '!', 'This Spotify account is not on the list',
                  'Spotify only lets a small app sign in the people its owner adds. '
                  'Dannify explains what to do next.'),
    'mismatch': ('#ffb020', '!', 'This sign-in has expired',
                 'Start again from Dannify, in Settings, Accounts.'),
    FAILED: ('#ff6b6b', '!', 'Spotify could not be connected', 'Go back to Dannify and try again.'),
}


class _CallbackHandler(BaseHTTPRequestHandler):
    server_version = 'Dannify'
    sys_version = ''

    def do_GET(self) -> None:  # noqa: N802
        parts = urlsplit(self.path)
        if parts.path != CALLBACK_PATH:
            self.send_error(404)
            return
        query = {k: v[0] for k, v in parse_qs(parts.query).items() if v}
        login = getattr(self.server, 'dannify_login', None)
        if not login:
            ok, why = False, 'mismatch'
        else:
            ok, why = finish(login, query)
        tone, mark, title, text = _PAGES.get('' if ok else why, _PAGES[FAILED])
        body = _PAGE
        for key, value in (('{tone}', tone), ('{mark}', mark), ('{title}', html.escape(title)),
                           ('{text}', html.escape(text))):
            body = body.replace(key, value)
        data = body.encode('utf-8')
        self.send_response(200 if ok else 400)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.end_headers()
        self.wfile.write(data)
        if login and login.get('done'):
            with _lock:
                if _state['login'] is login:
                    _stop_login()

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        # The address carries the one-time code: never into the log.
        return


# ---------------------------------------------------------------------------
# What Spotify has, as Dannify shows it
# ---------------------------------------------------------------------------
def _image(images: Any) -> str:
    if isinstance(images, list) and images:
        best = max((i for i in images if isinstance(i, dict) and i.get('url')),
                   key=lambda i: i.get('width') or 0, default=None)
        return str(best['url']) if best else ''
    return ''


def song_from_track(track: Any, added: str = '') -> Optional[dict[str, Any]]:
    """A Spotify track as a song the player knows (the shape spotify.py
    gives a pasted link): it plays by its Spotify address."""

    if not isinstance(track, dict) or track.get('type', 'track') != 'track' or track.get('is_local'):
        return None
    tid = str(track.get('id') or '')
    if not tid:
        return None
    album = track.get('album') if isinstance(track.get('album'), dict) else {}
    names = [str(a.get('name')) for a in track.get('artists') or [] if isinstance(a, dict) and a.get('name')]
    release = str(album.get('release_date') or '')
    song = {
        'song_id': tid,
        'name': str(track.get('name') or ''),
        'artists': names,
        'artist': ', '.join(names),
        'album_name': str(album.get('name') or ''),
        'cover_url': _image(album.get('images')),
        'duration': int((track.get('duration_ms') or 0) / 1000),
        'url': f'https://open.spotify.com/track/{tid}',
        'explicit': bool(track.get('explicit')),
        'release_date': release,
        'year': release[:4] if release[:4].isdigit() else '',
        'source': 'spotify',
    }
    isrc = (track.get('external_ids') or {}).get('isrc') if isinstance(track.get('external_ids'), dict) else ''
    if isrc:
        song['isrc'] = str(isrc)
    if added:
        song['added_at'] = added
    return song


def _cached(key: str, make: Callable[[], Any]) -> Any:
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
    value = make()
    with _lock:
        _cache[key] = (time.time(), value)
    return value


def _pages(path: str, params: dict[str, Any], most: int) -> list[Any]:
    """Every item of a paged list, up to *most*."""

    items: list[Any] = []
    data = _api(path, params)
    while True:
        box = data.get('items') if 'items' in data else (data.get('artists') or {}).get('items')
        items.extend(box or [])
        nxt = data.get('next') if 'items' in data else (data.get('artists') or {}).get('next')
        if not nxt or len(items) >= most:
            return items[:most]
        data = _api(nxt)


def _require() -> None:
    if not _state['refresh']:
        raise SpotifyError(EXPIRED)


def _count(box: Any) -> int:
    # Spotify renamed a playlist's `tracks` to `items` in February 2026.
    if isinstance(box, dict):
        return int(box.get('total') or 0)
    return 0


def playlists() -> list[dict[str, Any]]:
    _require()

    def make() -> list[dict[str, Any]]:
        me = _state['user'].get('id', '')
        out = []
        for p in _pages('/me/playlists', {'limit': 50}, MOST_PLAYLISTS):
            if not isinstance(p, dict) or not p.get('id'):
                continue
            owner = p.get('owner') if isinstance(p.get('owner'), dict) else {}
            out.append({
                'id': str(p['id']),
                'name': str(p.get('name') or ''),
                'owner': str(owner.get('display_name') or owner.get('id') or ''),
                'mine': bool(owner.get('id') and owner.get('id') == me),
                'collaborative': bool(p.get('collaborative')),
                'image': _image(p.get('images')),
                'count': _count(p.get('items') or p.get('tracks')),
                'url': f'https://open.spotify.com/playlist/{p["id"]}',
            })
        return out

    return _cached('playlists', make)


def playlist(pid: str) -> dict[str, Any]:
    """A playlist and its songs. Spotify gives the songs of a playlist the
    person owns or shares; another's public playlist is read the way a
    pasted link is."""

    _require()

    def make() -> dict[str, Any]:
        info = next((p for p in playlists() if p['id'] == pid), None)
        try:
            rows = _pages(f'/playlists/{pid}/items', {'limit': 50}, MOST_SONGS)
            songs = [s for s in (song_from_track(r.get('item') or r.get('track'), r.get('added_at') or '')
                                 for r in rows if isinstance(r, dict)) if s]
        except SpotifyError as exc:
            if exc.reason in (NOT_ALLOWED, EXPIRED):
                raise
            from . import spotify  # noqa: PLC0415

            name, songs = spotify.playlist_info_and_tracks(pid)
            info = info or {'id': pid, 'name': name, 'owner': '', 'mine': False, 'image': '', 'count': len(songs),
                            'url': f'https://open.spotify.com/playlist/{pid}'}
        return {**(info or {'id': pid, 'name': '', 'url': f'https://open.spotify.com/playlist/{pid}'}),
                'songs': songs}

    return _cached(f'playlist:{pid}', make)


def liked() -> list[dict[str, Any]]:
    _require()
    return _cached('liked', lambda: [
        s for s in (song_from_track(r.get('track'), r.get('added_at') or '')
                    for r in _pages('/me/tracks', {'limit': 50}, MOST_SONGS) if isinstance(r, dict)) if s
    ])


def albums() -> list[dict[str, Any]]:
    _require()

    def make() -> list[dict[str, Any]]:
        out = []
        for r in _pages('/me/albums', {'limit': 50}, MOST_PLAYLISTS):
            a = r.get('album') if isinstance(r, dict) else None
            if not isinstance(a, dict) or not a.get('id'):
                continue
            artists = [x.get('name') for x in a.get('artists') or [] if isinstance(x, dict) and x.get('name')]
            out.append({
                'id': str(a['id']),
                'name': str(a.get('name') or ''),
                'artist': ', '.join(artists),
                'image': _image(a.get('images')),
                'count': int(a.get('total_tracks') or 0),
                'year': str(a.get('release_date') or '')[:4],
                'url': f'https://open.spotify.com/album/{a["id"]}',
            })
        return out

    return _cached('albums', make)


def album(aid: str) -> dict[str, Any]:
    _require()

    def make() -> dict[str, Any]:
        a = _api(f'/albums/{aid}')
        artists = [x.get('name') for x in a.get('artists') or [] if isinstance(x, dict) and x.get('name')]
        frame = {k: a.get(k) for k in ('name', 'images', 'release_date')}
        songs = []
        for tr in (a.get('tracks') or {}).get('items') or []:
            if isinstance(tr, dict):
                s = song_from_track({**tr, 'album': frame})
                if s:
                    songs.append(s)
        return {
            'id': aid,
            'name': str(a.get('name') or ''),
            'artist': ', '.join(artists),
            'image': _image(a.get('images')),
            'year': str(a.get('release_date') or '')[:4],
            'url': f'https://open.spotify.com/album/{aid}',
            'songs': songs,
        }

    return _cached(f'album:{aid}', make)


def artists() -> list[dict[str, Any]]:
    _require()

    def make() -> list[dict[str, Any]]:
        rows = _pages('/me/following', {'type': 'artist', 'limit': 50}, MOST_PLAYLISTS)
        return [_artist(a) for a in rows if isinstance(a, dict) and a.get('id')]

    return _cached('artists', make)


def _artist(a: dict[str, Any]) -> dict[str, Any]:
    return {
        'id': str(a['id']),
        'name': str(a.get('name') or ''),
        'image': _image(a.get('images')),
        'genres': [str(g) for g in (a.get('genres') or [])[:3]],
        'url': f'https://open.spotify.com/artist/{a["id"]}',
    }


RANGES = ('short_term', 'medium_term', 'long_term')


def top(kind: str, span: str) -> list[dict[str, Any]]:
    _require()
    if kind not in ('tracks', 'artists') or span not in RANGES:
        raise ValueError('top tracks or artists, over a known span')

    def make() -> list[Any]:
        rows = _api(f'/me/top/{kind}', {'limit': 50, 'time_range': span}).get('items') or []
        if kind == 'artists':
            return [_artist(a) for a in rows if isinstance(a, dict) and a.get('id')]
        return [s for s in (song_from_track(r) for r in rows) if s]

    return _cached(f'top:{kind}:{span}', make)


def recent() -> list[dict[str, Any]]:
    _require()

    def make() -> list[dict[str, Any]]:
        rows = _api('/me/player/recently-played', {'limit': 50}).get('items') or []
        out = []
        for r in rows:
            if isinstance(r, dict):
                s = song_from_track(r.get('track'))
                if s:
                    s['played_at'] = str(r.get('played_at') or '')
                    out.append(s)
        return out

    # Recently played moves on as the person listens: kept a minute only.
    with _lock:
        hit = _cache.get('recent')
        if hit and time.time() - hit[0] < 60:
            return hit[1]
    value = make()
    with _lock:
        _cache['recent'] = (time.time(), value)
    return value


# ---------------------------------------------------------------------------
# Copying a Spotify list into Dannify
# ---------------------------------------------------------------------------
_imports: dict[str, dict[str, Any]] = {}
MOST_IMPORTED = 1000


def songs_of(kind: str, ident: str = '') -> tuple[str, list[dict[str, Any]]]:
    """(name, songs) of one of the person's Spotify lists."""

    if kind == 'playlist':
        p = playlist(ident)
        return p.get('name') or 'Spotify', p.get('songs') or []
    if kind == 'album':
        a = album(ident)
        return a.get('name') or 'Spotify', a.get('songs') or []
    if kind == 'liked':
        return 'Liked Songs', liked()
    if kind == 'top':
        return 'Top songs', top('tracks', ident if ident in RANGES else 'medium_term')
    if kind == 'recent':
        return 'Recently played', recent()
    raise ValueError('unknown list')


def start_import(kind: str, ident: str = '', name: str = '') -> str:
    """Copy a Spotify list into a new Dannify playlist, in the background:
    each song is matched on YouTube Music. Returns the job's id."""

    title, songs = songs_of(kind, ident)
    songs = songs[:MOST_IMPORTED]
    job = uuid.uuid4().hex[:12]
    with _lock:
        _imports[job] = {'total': len(songs), 'done': 0, 'matched': 0, 'playlist': '', 'error': '',
                         'name': (name or title)[:120], 'finished': False}
    threading.Thread(target=_run_import, args=(job, songs), name='spotify-import', daemon=True).start()
    return job


def import_status(job: str) -> dict[str, Any]:
    with _lock:
        found = _imports.get(job)
        return dict(found) if found else {}


def _match(song: dict[str, Any]) -> Optional[dict[str, Any]]:
    from . import providers  # noqa: PLC0415  (imports ytmusicapi)

    try:
        video_id, hit = providers.find_match(song)
    except Exception:
        logger.opt(exception=True).debug('no YouTube match for {}', song.get('name'))
        return None
    if not video_id:
        return None
    # Spotify's own cover, or YouTube Music's for the recording it matched.
    thumbs = [x for x in (hit or {}).get('thumbnails') or [] if isinstance(x, dict) and x.get('url')]
    return {
        'video_id': video_id,
        'title': song.get('name') or '',
        'artists': song.get('artists') or [],
        'album': song.get('album_name') or '',
        'duration': song.get('duration') or 0,
        'cover_url': song.get('cover_url') or (thumbs[-1]['url'] if thumbs else ''),
    }


def _run_import(job: str, songs: list[dict[str, Any]]) -> None:
    from . import playlists as dannify_playlists  # noqa: PLC0415

    entries: list[Optional[dict[str, Any]]] = [None] * len(songs)

    def one(i: int) -> None:
        entries[i] = _match(songs[i])
        with _lock:
            _imports[job]['done'] += 1
            if entries[i]:
                _imports[job]['matched'] += 1

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(one, range(len(songs))))
        kept = [e for e in entries if e]
        made = dannify_playlists.create(_imports[job]['name'], kept) if kept else None
        with _lock:
            _imports[job]['playlist'] = made['id'] if made else ''
            _imports[job]['error'] = '' if made else 'nothing_matched'
    except Exception:
        logger.opt(exception=True).warning('Copying a Spotify list failed')
        with _lock:
            _imports[job]['error'] = FAILED
    finally:
        with _lock:
            _imports[job]['finished'] = True
