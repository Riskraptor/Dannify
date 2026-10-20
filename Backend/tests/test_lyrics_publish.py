"""Sharing lyrics: what happens when the catalogue fails, and what the
window is told. Nothing here reaches the network."""

import asyncio

import pytest
import requests

from dannify import lyrics_publish
from dannify.routes import lyrics as lyrics_routes


class _Resp:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.text = str(self._body)

    def json(self):
        return self._body


@pytest.fixture
def offline_catalogue(monkeypatch):
    """A catalogue that answers with whatever the test lines up."""

    answers = []
    sleeps = []
    monkeypatch.setattr(lyrics_publish, 'request_challenge', lambda: {'prefix': 'p', 'target': 'ff' * 32})
    monkeypatch.setattr(lyrics_publish, 'make_publish_token', lambda challenge: 'p:1')
    monkeypatch.setattr(lyrics_publish, '_sleep', sleeps.append)

    def post(url, **kwargs):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(lyrics_publish._session, 'post', post)
    return answers, sleeps


def _publish():
    return lyrics_publish.publish(
        track_name='Hebu Nieleze', artist_name='CJs', album_name='',
        duration=200, synced_lyrics='[00:12.00] Hebu nieleze',
    )


def test_a_fault_of_the_catalogue_s_own_is_tried_again(offline_catalogue):
    answers, sleeps = offline_catalogue
    answers += [_Resp(500, {'message': 'Something bad happened'}), _Resp(201)]
    assert _publish() == {'published': True}
    assert sleeps == [2.0]


def test_it_gives_up_after_three_tries_and_says_busy(offline_catalogue):
    answers, sleeps = offline_catalogue
    answers += [_Resp(500), _Resp(502), requests.Timeout('slow')]
    with pytest.raises(lyrics_publish.PublishError) as caught:
        _publish()
    assert caught.value.kind == 'busy'
    assert sleeps == [2.0, 5.0]


def test_lyrics_turned_down_are_not_sent_again(offline_catalogue):
    answers, sleeps = offline_catalogue
    answers += [_Resp(400, {'message': 'Invalid publish token'})]
    with pytest.raises(lyrics_publish.PublishError) as caught:
        _publish()
    assert caught.value.kind == 'refused'
    assert sleeps == []


def test_no_connection_says_offline(offline_catalogue):
    answers, _ = offline_catalogue
    answers += [requests.ConnectionError('no route')]
    with pytest.raises(lyrics_publish.PublishError) as caught:
        _publish()
    assert caught.value.kind == 'offline'


class _Request:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def test_the_window_is_told_the_kind_and_never_the_catalogue_s_words(monkeypatch):
    def refuse(**kwargs):
        raise lyrics_publish.PublishError('lrclib rejected publish (HTTP 500): Something bad', 'busy')

    monkeypatch.setattr(lyrics_publish, 'publish', refuse)
    body = {'track': 'Hebu Nieleze', 'artist': 'CJs', 'duration': 200, 'synced': '[00:12.00] Hebu'}
    answer = asyncio.run(lyrics_routes.lyrics_publish_endpoint(_Request(body)))
    assert answer == {'published': False, 'reason': 'busy'}
    assert 'lrclib' not in str(answer)


def test_something_missing_is_said_without_sending(monkeypatch):
    sent = []
    monkeypatch.setattr(lyrics_publish, 'publish', lambda **kw: sent.append(kw))
    answer = asyncio.run(lyrics_routes.lyrics_publish_endpoint(_Request({'track': 'x', 'artist': ''})))
    assert answer == {'published': False, 'reason': 'invalid'}
    assert sent == []
