"""Spotify: signing in the way Spotify asks an app on someone's computer to
(PKCE, a one-time page on 127.0.0.1), keeping the sign-in sealed, and
reading the person's Spotify. Spotify itself is played by a fake that
answers the way accounts.spotify.com and api.spotify.com do."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from dannify import spotify_account as sp

CLIENT = '0123456789abcdef0123456789abcdef'


def track(n, **extra):
    return {
        'type': 'track', 'id': f'trk{n:019d}', 'name': f'Song {n}', 'duration_ms': 200000 + n,
        'explicit': n % 2 == 0, 'artists': [{'name': 'Sauti Sol'}, {'name': 'Nviiri'}],
        'album': {'name': 'Midnight Train', 'release_date': '2020-06-05',
                  'images': [{'url': 'https://i.scdn.co/small', 'width': 64},
                             {'url': 'https://i.scdn.co/big', 'width': 640}]},
        'external_ids': {'isrc': f'KE{n:010d}'},
        **extra,
    }


class FakeSpotify:
    """Answers token and API requests, and remembers what it was sent."""

    def __init__(self) -> None:
        self.token_posts: list[dict] = []
        self.gets: list[tuple[str, dict]] = []
        self.registered = True
        self.refresh_ok = True
        self.access = 'access-1'
        self.expires_in = 3600

    @staticmethod
    def respond(status, body=None, headers=None):
        res = requests.Response()
        res.status_code = status
        res._content = json.dumps(body).encode() if body is not None else b''
        res.headers.update(headers or {})
        return res

    def post(self, url, data=None, timeout=None):
        assert url == sp.TOKEN_URL
        self.token_posts.append(dict(data))
        if data['grant_type'] == 'authorization_code':
            assert data['code'] == 'good-code'
            return self.respond(200, {'access_token': self.access, 'refresh_token': 'refresh-1',
                                      'expires_in': self.expires_in, 'scope': sp.SCOPES})
        if not self.refresh_ok:
            return self.respond(400, {'error': 'invalid_grant'})
        self.access = 'access-2'
        return self.respond(200, {'access_token': self.access, 'expires_in': 3600})

    def get(self, url, params=None, headers=None, timeout=None):
        assert headers['Authorization'] == f'Bearer {self.access}'
        path = url.replace(sp.API, '')
        self.gets.append((path, dict(params or {})))
        if not self.registered:
            return self.respond(403, None) if False else self._text(
                403, 'Check settings on developer.spotify.com/dashboard, the user may not be registered.')
        if path == '/me':
            return self.respond(200, {'id': 'dani', 'display_name': 'Dani M',
                                      'images': [{'url': 'https://i.scdn.co/me', 'width': 300}]})
        if path == '/me/playlists':
            return self.respond(200, {'items': [
                {'id': 'mine1', 'name': 'Road trip', 'owner': {'id': 'dani', 'display_name': 'Dani M'},
                 'images': [{'url': 'https://i.scdn.co/pl', 'width': 300}], 'items': {'total': 3}},
                {'id': 'theirs1', 'name': 'Afro Hits', 'owner': {'id': 'spotify', 'display_name': 'Spotify'},
                 'images': [], 'tracks': {'total': 50}},
            ], 'next': None})
        if path == '/playlists/mine1/items':
            return self.respond(200, {'items': [
                {'added_at': '2026-01-01T00:00:00Z', 'item': track(1)},
                {'added_at': '2026-01-02T00:00:00Z', 'item': {'type': 'episode', 'id': 'ep1'}},
                {'added_at': '2026-01-03T00:00:00Z', 'item': track(2, is_local=True)},
                {'added_at': '2026-01-04T00:00:00Z', 'item': track(3)},
            ], 'next': None})
        if path == '/playlists/theirs1/items':
            return self._text(403, 'Forbidden.')
        if path == '/me/tracks' or url.endswith('/me/tracks?offset=50&limit=50'):
            if 'offset=50' in url:
                return self.respond(200, {'items': [{'added_at': 'x', 'track': track(60)}], 'next': None})
            return self.respond(200, {'items': [{'added_at': 'x', 'track': track(n)} for n in range(50)],
                                      'next': sp.API + '/me/tracks?offset=50&limit=50'})
        if path == '/me/following' or 'after=' in url:
            if 'after=' in url:
                return self.respond(200, {'artists': {'items': [{'id': 'a2', 'name': 'Tems', 'images': []}],
                                                      'next': None}})
            return self.respond(200, {'artists': {'items': [
                {'id': 'a1', 'name': 'Sauti Sol', 'genres': ['afropop', 'kenyan pop', 'x', 'y'],
                 'images': [{'url': 'https://i.scdn.co/a1', 'width': 640}]}],
                'next': sp.API + '/me/following?type=artist&after=a1'}})
        if path == '/me/top/tracks':
            return self.respond(200, {'items': [track(7), track(8)]})
        if path == '/me/top/artists':
            return self.respond(200, {'items': [{'id': 'a1', 'name': 'Sauti Sol', 'images': []}]})
        if path == '/me/player/recently-played':
            return self.respond(200, {'items': [{'played_at': '2026-10-19T10:00:00Z', 'track': track(9)}]})
        if path == '/me/albums':
            return self.respond(200, {'items': [{'album': {
                'id': 'al1', 'name': 'Midnight Train', 'artists': [{'name': 'Sauti Sol'}], 'total_tracks': 12,
                'release_date': '2020-06-05', 'images': [{'url': 'https://i.scdn.co/al', 'width': 640}]}}],
                'next': None})
        if path == '/albums/al1':
            return self.respond(200, {'name': 'Midnight Train', 'artists': [{'name': 'Sauti Sol'}],
                                      'release_date': '2020-06-05', 'images': [{'url': 'https://i.scdn.co/al'}],
                                      'tracks': {'items': [{**track(11), 'album': None}]}})
        return self.respond(404, {'error': 'not here'})

    def _text(self, status, text):
        res = requests.Response()
        res.status_code = status
        res._content = text.encode()
        return res


@pytest.fixture
def fake(tmp_path, monkeypatch):
    spot = FakeSpotify()
    monkeypatch.setattr(sp, '_post', spot.post)
    monkeypatch.setattr(sp, '_get', spot.get)
    sp.init(tmp_path)
    yield spot
    sp.disconnect()


def visit(url):
    """Open the callback page the way the browser would: (status, page)."""

    try:
        with urllib.request.urlopen(url, timeout=5) as res:
            return res.status, res.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode('utf-8')


def sign_in(fake):
    sp.set_client_id(CLIENT)
    url = sp.begin()
    q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    status, page = visit(f"{q['redirect_uri']}?code=good-code&state={q['state']}")
    return q, status, page


# ---------------------------------------------------------------------------
# Signing in
# ---------------------------------------------------------------------------
def test_without_a_client_id_there_is_nothing_to_sign_in_with(fake):
    assert sp.status()['configured'] is False
    with pytest.raises(sp.SpotifyError) as err:
        sp.begin()
    assert err.value.reason == sp.NOT_CONFIGURED


def test_a_client_id_must_look_like_one_and_is_kept(fake, tmp_path):
    for bad in ('short', 'x' * 32, CLIENT + '0'):
        with pytest.raises(ValueError):
            sp.set_client_id(bad)
    assert sp.set_client_id(CLIENT.upper())['own_app'] is True
    sp.init(tmp_path)  # the next run
    assert sp.client_id() == CLIENT
    assert sp.status()['configured'] is True


def test_the_sign_in_page_is_spotifys_with_pkce_and_a_loopback_address(fake):
    sp.set_client_id(CLIENT)
    url = sp.begin()
    parts = urlsplit(url)
    assert f'{parts.scheme}://{parts.netloc}{parts.path}' == sp.AUTHORIZE_URL
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert q['client_id'] == CLIENT
    assert q['response_type'] == 'code'
    assert q['code_challenge_method'] == 'S256'
    assert q['redirect_uri'].startswith('http://127.0.0.1:') and q['redirect_uri'].endswith('/callback')
    assert set(q['scope'].split()) == set(sp.SCOPES.split())
    assert len(q['state']) >= 24
    assert sp.status()['signing_in'] is True
    # Coming back: the code is traded with the verifier the challenge was made from.
    status, page = visit(f"{q['redirect_uri']}?code=good-code&state={q['state']}")
    assert status == 200 and 'Connected to Spotify' in page
    sent = fake.token_posts[0]
    verifier = sent['code_verifier']
    assert 43 <= len(verifier) <= 128
    made = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    assert made == q['code_challenge']
    assert sent['redirect_uri'] == q['redirect_uri'] and sent['client_id'] == CLIENT
    assert 'client_secret' not in sent


def test_signed_in_the_account_is_shown_and_kept_sealed(fake, tmp_path):
    _, status, _ = sign_in(fake)
    assert status == 200
    now = sp.status()
    assert now['connected'] is True and now['error'] == ''
    assert now['user'] == {'id': 'dani', 'name': 'Dani M', 'image': 'https://i.scdn.co/me'}
    stored = (tmp_path / 'spotify.dat').read_bytes()
    assert b'refresh-1' not in stored and b'Dani' not in stored
    sp.init(tmp_path)  # the next run
    assert sp.status()['connected'] is True and sp.status()['user']['name'] == 'Dani M'


def test_a_page_with_the_wrong_state_signs_nobody_in_and_the_real_one_still_works(fake):
    sp.set_client_id(CLIENT)
    url = sp.begin()
    q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    status, page = visit(f"{q['redirect_uri']}?code=good-code&state=forged")
    assert status == 400 and 'expired' in page
    assert sp.status()['connected'] is False and fake.token_posts == []
    status, _ = visit(f"{q['redirect_uri']}?code=good-code&state={q['state']}")
    assert status == 200 and sp.status()['connected'] is True


def test_only_the_callback_page_is_answered(fake):
    sp.set_client_id(CLIENT)
    url = sp.begin()
    redirect = parse_qs(urlsplit(url).query)['redirect_uri'][0]
    status, _ = visit(redirect.replace('/callback', '/favicon.ico'))
    assert status == 404


def test_saying_no_on_spotifys_page_is_reported(fake):
    sp.set_client_id(CLIENT)
    q = {k: v[0] for k, v in parse_qs(urlsplit(sp.begin()).query).items()}
    status, page = visit(f"{q['redirect_uri']}?error=access_denied&state={q['state']}")
    assert status == 400 and 'Nothing was shared' in page
    assert sp.status()['error'] == sp.DENIED and sp.status()['connected'] is False


def test_the_one_time_page_closes_after_its_answer(fake):
    q, status, _ = sign_in(fake)
    assert status == 200
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            urllib.request.urlopen(q['redirect_uri'], timeout=1)
        except urllib.error.HTTPError:
            pass
        except (urllib.error.URLError, ConnectionError, OSError):
            return  # nobody listening any more
        time.sleep(0.1)
    pytest.fail('the sign-in page kept listening')


def test_an_account_spotify_does_not_list_is_told_so(fake):
    fake.registered = False
    _, status, page = sign_in(fake)
    assert status == 400 and 'not on the list' in page
    assert sp.status()['error'] == sp.NOT_ALLOWED and sp.status()['connected'] is False


def test_the_hourly_token_is_renewed_and_a_revoked_one_ends_the_sign_in(fake):
    sign_in(fake)
    sp._state['expires'] = time.time() - 1
    assert [s['song_id'] for s in sp.recent()]  # asked with a renewed token
    assert fake.token_posts[-1]['grant_type'] == 'refresh_token'
    assert fake.token_posts[-1]['client_id'] == CLIENT
    fake.refresh_ok = False
    sp._state['expires'] = time.time() - 1
    sp._cache.clear()
    with pytest.raises(sp.SpotifyError) as err:
        sp.liked()
    assert err.value.reason == sp.EXPIRED
    assert sp.status()['connected'] is False and sp.status()['error'] == sp.EXPIRED


def test_signing_out_forgets_the_sign_in_but_keeps_ones_own_app(fake, tmp_path):
    sign_in(fake)
    sp.disconnect()
    assert sp.status()['connected'] is False
    sp.init(tmp_path)
    assert sp.status()['connected'] is False and sp.client_id() == CLIENT


def test_another_app_cannot_use_this_ones_sign_in(fake):
    sign_in(fake)
    sp.set_client_id('f' * 32)
    assert sp.status()['connected'] is False


# ---------------------------------------------------------------------------
# What is read
# ---------------------------------------------------------------------------
def test_a_track_becomes_a_song_that_plays_by_its_spotify_address():
    song = sp.song_from_track(track(4), '2026-01-01')
    assert song == {
        'song_id': 'trk0000000000000000004', 'name': 'Song 4', 'artists': ['Sauti Sol', 'Nviiri'],
        'artist': 'Sauti Sol, Nviiri', 'album_name': 'Midnight Train', 'cover_url': 'https://i.scdn.co/big',
        'duration': 200, 'url': 'https://open.spotify.com/track/trk0000000000000000004', 'explicit': True,
        'release_date': '2020-06-05', 'year': '2020', 'source': 'spotify', 'isrc': 'KE0000000004',
        'added_at': '2026-01-01',
    }
    assert sp.song_from_track({'type': 'episode', 'id': 'e'}) is None
    assert sp.song_from_track(track(5, is_local=True)) is None
    assert sp.song_from_track(True) is None


def test_playlists_say_whose_they_are_and_how_many_songs(fake):
    sign_in(fake)
    mine, theirs = sp.playlists()
    assert mine['mine'] is True and mine['count'] == 3 and mine['image'] == 'https://i.scdn.co/pl'
    assert theirs['mine'] is False and theirs['count'] == 50 and theirs['owner'] == 'Spotify'


def test_ones_own_playlist_is_read_skipping_episodes_and_local_files(fake):
    sign_in(fake)
    p = sp.playlist('mine1')
    assert p['name'] == 'Road trip'
    assert [s['name'] for s in p['songs']] == ['Song 1', 'Song 3']


def test_someone_elses_playlist_is_read_the_way_a_pasted_link_is(fake, monkeypatch):
    from dannify import spotify

    monkeypatch.setattr(spotify, 'playlist_info_and_tracks', lambda pid: ('Afro Hits', [{'name': 'Public'}]))
    sign_in(fake)
    p = sp.playlist('theirs1')
    assert p['name'] == 'Afro Hits' and p['songs'] == [{'name': 'Public'}]


def test_liked_songs_and_followed_artists_are_read_page_by_page(fake):
    sign_in(fake)
    assert len(sp.liked()) == 51
    names = [a['name'] for a in sp.artists()]
    assert names == ['Sauti Sol', 'Tems']
    assert sp.artists()[0]['genres'] == ['afropop', 'kenyan pop', 'x']


def test_top_recent_and_albums(fake):
    sign_in(fake)
    assert [s['name'] for s in sp.top('tracks', 'short_term')] == ['Song 7', 'Song 8']
    assert sp.top('artists', 'long_term')[0]['name'] == 'Sauti Sol'
    with pytest.raises(ValueError):
        sp.top('tracks', 'forever')
    assert sp.recent()[0]['played_at'] == '2026-10-19T10:00:00Z'
    assert sp.albums()[0]['count'] == 12
    one = sp.album('al1')
    assert one['songs'][0]['album_name'] == 'Midnight Train' and one['songs'][0]['cover_url']


def test_what_was_read_is_kept_a_while(fake):
    sign_in(fake)
    sp.liked()
    asked = len(fake.gets)
    sp.liked()
    assert len(fake.gets) == asked


def test_nothing_is_read_signed_out(fake):
    with pytest.raises(sp.SpotifyError) as err:
        sp.playlists()
    assert err.value.reason == sp.EXPIRED


# ---------------------------------------------------------------------------
# Copying into Dannify
# ---------------------------------------------------------------------------
def test_a_spotify_playlist_is_copied_with_the_songs_youtube_has(fake, tmp_path, monkeypatch):
    from dannify import playlists, providers

    playlists.init(tmp_path / 'pl')
    matches = {'Song 1': 'aaaaaaaaaa1'}
    monkeypatch.setattr(providers, 'find_match', lambda song: (matches.get(song['name']), {}))
    sign_in(fake)
    job = sp.start_import('playlist', 'mine1')
    deadline = time.time() + 10
    while not sp.import_status(job)['finished'] and time.time() < deadline:
        time.sleep(0.05)
    done = sp.import_status(job)
    assert done['total'] == 2 and done['done'] == 2 and done['matched'] == 1 and done['error'] == ''
    made = playlists.get(done['playlist'])
    assert made['name'] == 'Road trip'
    assert [(t['video_id'], t['title']) for t in made['tracks']] == [('aaaaaaaaaa1', 'Song 1')]


def test_a_copy_with_nothing_found_makes_no_empty_playlist(fake, tmp_path, monkeypatch):
    from dannify import playlists, providers

    playlists.init(tmp_path / 'pl')
    monkeypatch.setattr(providers, 'find_match', lambda song: (None, None))
    sign_in(fake)
    job = sp.start_import('liked')
    deadline = time.time() + 20
    while not sp.import_status(job)['finished'] and time.time() < deadline:
        time.sleep(0.05)
    assert sp.import_status(job)['error'] == 'nothing_matched'
    assert playlists.all_playlists() == []


# ---------------------------------------------------------------------------
# The window's side
# ---------------------------------------------------------------------------
def test_answers_say_why_they_failed(fake):
    from fastapi import HTTPException

    from dannify.routes import spotify_account as routes

    with pytest.raises(HTTPException) as err:
        asyncio.run(routes.spotify_connect_endpoint())
    assert (err.value.status_code, err.value.detail) == (409, sp.NOT_CONFIGURED)
    with pytest.raises(HTTPException) as err:
        asyncio.run(routes.spotify_liked_endpoint())
    assert (err.value.status_code, err.value.detail) == (401, sp.EXPIRED)
    with pytest.raises(HTTPException) as err:
        asyncio.run(routes.spotify_app_endpoint({'client_id': 'nope'}))
    assert err.value.status_code == 400
    sign_in(fake)
    assert len(asyncio.run(routes.spotify_liked_endpoint())['songs']) == 51


def test_a_stand_in_spotify_can_only_be_on_this_computer(monkeypatch):
    monkeypatch.setenv('DANNIFY_X', 'http://127.0.0.1:8898/')
    assert sp._base('DANNIFY_X', 'https://real') == 'http://127.0.0.1:8898'
    for elsewhere in ('https://evil.example', 'http://127.0.0.1.evil.example', 'http://localhost:8898', ''):
        monkeypatch.setenv('DANNIFY_X', elsewhere)
        assert sp._base('DANNIFY_X', 'https://real') == 'https://real'


def test_a_copied_song_without_a_cover_takes_youtubes(monkeypatch):
    from dannify import providers

    monkeypatch.setattr(providers, 'find_match', lambda song: (
        'bbbbbbbbbb2', {'thumbnails': [{'url': 'https://yt/small'}, {'url': 'https://yt/big'}]}))
    got = sp._match({'name': 'X', 'artists': ['Y'], 'cover_url': '', 'duration': 3})
    assert got['cover_url'] == 'https://yt/big'
    got = sp._match({'name': 'X', 'artists': ['Y'], 'cover_url': 'https://i.scdn.co/a', 'duration': 3})
    assert got['cover_url'] == 'https://i.scdn.co/a'
