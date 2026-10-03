"""The YouTube Music account, used for more than likes: following artists,
adding to its playlists, its listening history. Against a stand-in client:
nothing here touches a real account."""

from __future__ import annotations

import pytest

from dannify import account

CHANNEL = 'UC' + 'a' * 22


class FakeYT:
    def __init__(self):
        self.calls = []

    def get_library_subscriptions(self, limit=25):
        return [{'browseId': CHANNEL, 'artist': 'Bensoul', 'subscribers': '375K',
                 'thumbnails': [{'url': 'https://lh3.googleusercontent.com/x=w60-h60'}]},
                {'nothing': True}]

    def subscribe_artists(self, ids):
        self.calls.append(('follow', ids))

    def unsubscribe_artists(self, ids):
        self.calls.append(('unfollow', ids))

    def get_history(self):
        song = {'videoId': 'QtrUp3-HLkw', 'title': 'Inauma', 'artists': [{'name': 'Bien', 'id': 'UCb'}],
                'album': {'name': 'Inauma', 'id': 'MPRE1'}, 'duration': '3:30',
                'thumbnails': [{'url': 'https://i.ytimg.com/a.jpg'}]}
        return [song, dict(song)]  # the same song twice in the history

    def add_playlist_items(self, pid, ids, duplicates=False):
        self.calls.append(('add', pid, ids, duplicates))
        return {'status': 'STATUS_SUCCEEDED'}

    def get_song(self, vid):
        return {'playbackTracking': {'videostatsPlaybackUrl': {'baseUrl': 'https://x'}}}

    def add_history_item(self, song):
        self.calls.append(('history', song['playbackTracking']['videostatsPlaybackUrl']['baseUrl']))

        class R:
            status_code = 204
        return R()


@pytest.fixture
def yt(monkeypatch):
    fake = FakeYT()
    monkeypatch.setattr(account, 'client', lambda require_auth=False: fake)
    return fake


def test_following(yt):
    artists = account.subscriptions()
    assert [a['name'] for a in artists] == ['Bensoul'] and artists[0]['browse_id'] == CHANNEL
    assert account.follow(CHANNEL, True) == {'channel_id': CHANNEL, 'following': True}
    account.follow(CHANNEL, False)
    assert yt.calls == [('follow', [CHANNEL]), ('unfollow', [CHANNEL])]
    with pytest.raises(ValueError):
        account.follow('not-a-channel', True)


def test_history_has_each_song_once(yt):
    songs = account.history()
    assert len(songs) == 1 and songs[0]['song_id'] == 'QtrUp3-HLkw'


def test_adding_to_a_playlist_of_the_account(yt):
    out = account.add_to_playlist('VLPLabc', ['QtrUp3-HLkw', 'bad id', 'aaaaaaaaaaa'])
    assert out == {'playlist_id': 'PLabc', 'added': 2}
    assert yt.calls[-1] == ('add', 'PLabc', ['QtrUp3-HLkw', 'aaaaaaaaaaa'], False)
    with pytest.raises(ValueError):
        account.add_to_playlist('LM', ['QtrUp3-HLkw'])  # Liked Music is filled by liking
    with pytest.raises(ValueError):
        account.add_to_playlist('PLabc', ['nope'])


def test_a_play_reaches_the_account_history(yt):
    assert account.add_history('QtrUp3-HLkw') is True
    assert yt.calls[-1] == ('history', 'https://x')
    assert account.add_history('bad') is False
