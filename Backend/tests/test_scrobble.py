"""Sending listens to ListenBrainz: only when connected, nothing lost offline,
and a token that stops working stops the sending without losing a listen."""

from __future__ import annotations

import json

import pytest
import requests

from dannify import listens, scrobble
from dannify.routes import listens as listens_routes

TOKEN = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
SONG = {
    'title': 'Suzanna', 'artists': ['Sauti Sol'], 'album': 'Midnight Train',
    'duration': 230, 'video_id': 'KNEd-OkExKY',
}


class FakeListenBrainz:
    """Answers the way api.listenbrainz.org does, and remembers what it got."""

    def __init__(self) -> None:
        self.valid = {TOKEN: 'danielmk'}
        self.down = 0  # how many requests in a row fail to connect
        self.status = None  # force an answer, e.g. 401 or 400
        self.received: list[dict] = []

    def __call__(self, method, path, token, body=None):
        if self.down:
            self.down -= 1
            raise requests.ConnectionError('offline')
        res = requests.Response()
        if path == '/1/validate-token':
            user = self.valid.get(token)
            res.status_code = 200
            res._content = json.dumps(
                {'valid': bool(user), 'user_name': user} if user else {'valid': False}
            ).encode()
            return res
        assert path == '/1/submit-listens' and method == 'POST'
        if self.status:
            res.status_code = self.status
            res._content = b'{"error": "no"}'
            return res
        if token not in self.valid:
            res.status_code = 401
            res._content = b'{"error": "Invalid authorization token."}'
            return res
        self.received.append(body)
        res.status_code = 200
        res._content = b'{"status": "ok"}'
        return res


@pytest.fixture
def lb(tmp_path, monkeypatch):
    fake = FakeListenBrainz()
    monkeypatch.setattr(scrobble, '_request', fake)
    monkeypatch.setattr(scrobble, '_RETRY_FIRST', 0.01)
    monkeypatch.setattr(scrobble, '_RETRY_MOST', 0.02)
    scrobble.init(tmp_path)
    yield fake, tmp_path
    scrobble.disconnect()
    scrobble.flush()


def sent(fake):
    return [listen for body in fake.received for listen in body['payload']]


def test_nothing_is_sent_until_an_account_is_connected(lb):
    fake, _ = lb
    assert scrobble.submit(SONG, 1760000000, 200) is False
    assert scrobble.status() == {'connected': False, 'user': '', 'waiting': 0, 'error': ''}
    assert fake.received == []


def test_connecting_checks_the_token_and_keeps_it_encrypted(lb):
    _, folder = lb
    assert scrobble.connect(f'  {TOKEN} ')['user'] == 'danielmk'
    stored = (folder / scrobble._FILE).read_bytes()
    assert TOKEN.encode() not in stored
    # The next start is still connected.
    scrobble.init(folder)
    assert scrobble.status()['connected'] and scrobble.status()['user'] == 'danielmk'


@pytest.mark.parametrize('token', ['', 'not a token', 'x' * 300, 'wrong-token'])
def test_a_token_listenbrainz_does_not_take_is_refused(lb, token):
    _, folder = lb
    with pytest.raises(ValueError):
        scrobble.connect(token)
    assert not scrobble.status()['connected']
    assert not (folder / scrobble._FILE).exists()


def test_listenbrainz_out_of_reach_is_not_mistaken_for_a_bad_token(lb):
    fake, _ = lb
    fake.down = 1
    with pytest.raises(ConnectionError):
        scrobble.connect(TOKEN)
    assert not scrobble.status()['connected']


def test_a_listen_goes_with_what_listenbrainz_needs(lb):
    fake, _ = lb
    scrobble.connect(TOKEN)
    assert scrobble.submit(SONG, 1760000000, 200)
    scrobble.flush()
    assert fake.received[0]['listen_type'] == 'single'
    [listen] = sent(fake)
    assert listen['listened_at'] == 1760000000
    meta = listen['track_metadata']
    assert (meta['artist_name'], meta['track_name'], meta['release_name']) == (
        'Sauti Sol', 'Suzanna', 'Midnight Train',
    )
    info = meta['additional_info']
    assert info['duration_ms'] == 230000
    assert info['origin_url'] == 'https://music.youtube.com/watch?v=KNEd-OkExKY'
    assert info['media_player'] == 'Dannify'
    assert scrobble.status()['waiting'] == 0


def test_a_song_with_no_artist_or_title_is_not_sent(lb):
    scrobble.connect(TOKEN)
    assert scrobble.submit({'title': 'Untitled', 'artists': []}, 1760000000, 60) is False
    assert scrobble.submit({'title': '', 'artists': ['A']}, 1760000000, 60) is False


def test_listens_played_offline_arrive_later_in_order(lb):
    fake, folder = lb
    scrobble.connect(TOKEN)
    fake.down = 3
    for i in range(3):
        scrobble.submit({**SONG, 'title': f'Song {i}'}, 1760000000 + i * 300, 200)
    scrobble.flush()
    assert [l['track_metadata']['track_name'] for l in sent(fake)] == ['Song 0', 'Song 1', 'Song 2']
    assert scrobble.status()['waiting'] == 0
    assert not (folder / scrobble._QUEUE).exists()


def test_listens_still_waiting_survive_a_restart(lb, monkeypatch):
    fake, folder = lb
    scrobble.connect(TOKEN)
    fake.down = 10**6  # offline for the rest of this run
    scrobble.submit(SONG, 1760000000, 200)
    scrobble.submit({**SONG, 'title': 'Melanin'}, 1760000300, 200)
    assert len(json.loads((folder / scrobble._QUEUE).read_text(encoding='utf-8'))) == 2

    # Quit, and start again with the connection back.
    with scrobble._lock:
        scrobble._state['token'] = ''
    scrobble._wake.set()
    scrobble.flush()
    fake.down = 0
    scrobble.init(folder)
    scrobble.flush()

    assert fake.received[-1]['listen_type'] == 'import'
    assert [l['track_metadata']['track_name'] for l in sent(fake)] == ['Suzanna', 'Melanin']


def test_a_token_that_stops_working_stops_the_sending_and_keeps_the_listens(lb):
    fake, _ = lb
    scrobble.connect(TOKEN)
    fake.valid = {}  # revoked on listenbrainz.org
    scrobble.submit(SONG, 1760000000, 200)
    scrobble.flush()
    assert scrobble.status()['error'] == scrobble.TOKEN
    assert scrobble.status()['waiting'] == 1

    fake.valid = {'new-token-0001': 'danielmk'}
    scrobble.connect('new-token-0001')
    scrobble.flush()
    assert scrobble.status() == {'connected': True, 'user': 'danielmk', 'waiting': 0, 'error': ''}
    assert len(sent(fake)) == 1


def test_listens_listenbrainz_will_never_take_do_not_block_the_rest(lb):
    fake, _ = lb
    scrobble.connect(TOKEN)
    fake.status = 400
    scrobble.submit(SONG, 1760000000, 200)
    scrobble.flush()
    fake.status = None
    scrobble.submit({**SONG, 'title': 'Melanin'}, 1760000300, 200)
    scrobble.flush()
    assert [l['track_metadata']['track_name'] for l in sent(fake)] == ['Melanin']


def test_disconnecting_forgets_the_token_and_the_listens_not_yet_sent(lb):
    fake, folder = lb
    scrobble.connect(TOKEN)
    fake.down = 10**6
    scrobble.submit(SONG, 1760000000, 200)
    scrobble.disconnect()
    assert scrobble.status() == {'connected': False, 'user': '', 'waiting': 0, 'error': ''}
    assert not (folder / scrobble._FILE).exists()
    assert not (folder / scrobble._QUEUE).exists()


# ---------------------------------------------------------------------------
# From the window
# ---------------------------------------------------------------------------
@pytest.fixture
def history(tmp_path, monkeypatch):
    monkeypatch.setattr(listens, '_path', None)
    listens.init(tmp_path / 'history')
    yield
    listens.init(tmp_path / 'history-after')


def payload(**extra):
    return {
        'track': {'title': 'Suzanna', 'artists': ['Sauti Sol'], 'video_id': 'KNEd-OkExKY', 'duration': 230},
        'seconds': 120, 'started': 1760000000, **extra,
    }


def test_a_kept_listen_is_sent_once(lb, history):
    fake, _ = lb
    scrobble.connect(TOKEN)
    assert listens_routes._take(payload()) is True
    # The window offers it again after a restart: kept already, not sent again.
    assert listens_routes._take(payload()) is False
    scrobble.flush()
    assert len(sent(fake)) == 1


def test_with_the_history_paused_listens_still_reach_listenbrainz(lb, history):
    fake, _ = lb
    scrobble.connect(TOKEN)
    assert listens_routes._take(payload(keep=False)) is False
    scrobble.flush()
    assert len(sent(fake)) == 1
    assert listens.history(10, 0)['total'] == 0


def test_a_skip_is_neither_kept_nor_sent(lb, history):
    fake, _ = lb
    scrobble.connect(TOKEN)
    assert listens_routes._take(payload(seconds=8)) is False
    scrobble.flush()
    assert fake.received == []
