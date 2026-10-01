"""Artists online: two with one name told apart, and a page that is not empty."""

from __future__ import annotations

from dannify import explorer, providers


def _card(bid, name='Mavokali'):
    return {'type': 'artist', 'browse_id': bid, 'name': name, 'cover_url': '', 'subscribers': ''}


def test_namesakes_are_told_apart_and_the_one_with_songs_goes_first(monkeypatch):
    briefs = {
        'UCvideos': {'subscribers': '380K', 'has_songs': False},
        'UCsongs': {'subscribers': '17K', 'has_songs': True},
    }
    monkeypatch.setattr(explorer, 'artist_brief', lambda bid: briefs[bid])
    cards = [_card('UCvideos'), _card('UCsongs'), _card('UCray', 'Rayvanny')]
    explorer._label_namesakes(cards)
    assert [c['browse_id'] for c in cards] == ['UCsongs', 'UCvideos', 'UCray']
    assert cards[0]['subscribers'] == '17K' and cards[1]['subscribers'] == '380K'
    assert cards[0]['namesake'] and cards[1]['namesake'] and 'namesake' not in cards[2]


def test_a_name_nobody_else_has_costs_nothing(monkeypatch):
    def never(bid):
        raise AssertionError('looked up an artist with no namesake')

    monkeypatch.setattr(explorer, 'artist_brief', never)
    cards = [_card('A', 'Sauti Sol'), _card('B', 'Bien')]
    explorer._label_namesakes(cards)
    assert [c['browse_id'] for c in cards] == ['A', 'B']


def test_a_namesake_that_cannot_be_looked_up_keeps_its_place(monkeypatch):
    def offline(bid):
        raise ConnectionError('no network')

    monkeypatch.setattr(explorer, 'artist_brief', offline)
    cards = [_card('UCvideos'), _card('UCsongs')]
    explorer._label_namesakes(cards)
    assert [c['browse_id'] for c in cards] == ['UCvideos', 'UCsongs']


class _Client:
    def __init__(self, page):
        self.page = page

    def get_artist(self, bid):
        return self.page


def test_an_artist_with_only_videos_has_them_to_play(monkeypatch):
    page = {
        'name': 'Mavokali',
        'channelId': 'UCx',
        'thumbnails': [],
        'videos': {'browseId': 'VLvideos', 'results': [
            {'videoId': 'qCPtQgVhVUE', 'title': 'Cheche (Official Music Video)',
             'artists': [{'name': 'Mavokali', 'id': 'UCsongs'}], 'thumbnails': []},
        ]},
        'singles': {'results': []},
    }
    explorer.forget_artist('UCvideos')
    monkeypatch.setattr(explorer, '_ytm', lambda: _Client(page))
    monkeypatch.setattr(explorer, '_playlist_songs', lambda bid, limit=200: [])
    out = explorer.artist('UCvideos')
    assert [s['video_id'] for s in out['songs']] == ['qCPtQgVhVUE']
    # The videos are there to play; the artist still has no songs, and search
    # goes on saying so once the page has been opened.
    assert out['has_songs'] is False
    assert explorer.artist_brief('UCvideos')['has_songs'] is False
    explorer.forget_artist('UCvideos')


def test_a_music_video_says_who_it_credits(monkeypatch):
    """get_watch_playlist gives up on a music video; the queue is read itself."""

    class Client:
        def _send_request(self, endpoint, body):
            assert endpoint == 'next' and body['videoId'] == 'v0bBHiz3Pds'
            return {'contents': {'singleColumnMusicWatchNextResultsRenderer': {'tabbedRenderer': {
                'watchNextTabbedResultsRenderer': {'tabs': [{'tabRenderer': {'content': {
                    'musicQueueRenderer': {'content': {'playlistPanelRenderer': {'contents': ['row']}}}}}}]}}}}}

        def get_watch_playlist(self, video_id, limit=1):
            raise KeyError('endpoint')

    import ytmusicapi.parsers.watch as watch

    monkeypatch.setattr(providers, '_ytm', lambda: Client())
    monkeypatch.setattr(watch, 'parse_watch_playlist', lambda rows: [{
        'videoId': 'v0bBHiz3Pds', 'title': 'MAPOPO remix', 'length': '2:49',
        'artists': [{'name': 'Mavokali', 'id': 'UCsongs'}], 'thumbnail': [{'url': 'u'}],
        'videoType': 'MUSIC_VIDEO_TYPE_OMV',
    }])
    track = providers.watch_track('v0bBHiz3Pds')
    assert track['artists'] == [{'name': 'Mavokali', 'id': 'UCsongs'}]
    assert track['thumbnails'] == [{'url': 'u'}] and track['album'] is None


def test_a_watch_page_that_cannot_be_read_is_no_answer(monkeypatch):
    class Client:
        def _send_request(self, endpoint, body):
            return {}

        def get_watch_playlist(self, video_id, limit=1):
            raise KeyError('endpoint')

    monkeypatch.setattr(providers, '_ytm', lambda: Client())
    assert providers.watch_track('zzzzzzzzzzz') is None


def test_no_network_is_said_not_swallowed(monkeypatch):
    class Client:
        def _send_request(self, endpoint, body):
            raise ConnectionError('offline')

    monkeypatch.setattr(providers, '_ytm', lambda: Client())
    try:
        providers.watch_track('zzzzzzzzzzz')
    except ConnectionError:
        pass
    else:
        raise AssertionError('an unreachable YouTube looked like an unreadable page')


def test_a_search_that_reaches_nothing_is_not_an_empty_result(monkeypatch):
    class Offline:
        def search(self, q, filter=None, limit=20):
            raise ConnectionError('no network')

    monkeypatch.setattr(explorer, '_ytm', lambda: Offline())
    try:
        explorer._search_uncached('nothing cached xyz', 5)
    except explorer.SearchUnavailable:
        pass
    else:
        raise AssertionError('offline came back as "no results"')


def test_one_part_failing_still_gives_the_rest(monkeypatch):
    class Half:
        def search(self, q, filter=None, limit=20):
            if filter == 'songs':
                raise ConnectionError('blip')
            return []

    monkeypatch.setattr(explorer, '_ytm', lambda: Half())
    out = explorer._search_uncached('half xyz', 5)
    assert out == {'songs': [], 'artists': [], 'albums': [], 'playlists': []}


def test_the_connection_check_asks_fresh_every_time(monkeypatch):
    import requests

    from dannify import api

    answers = iter([None, requests.ConnectionError('down'), None])
    calls = []

    def head(url, timeout=0, allow_redirects=True):
        calls.append(url)
        a = next(answers)
        if a:
            raise a
        return object()

    monkeypatch.setattr(requests, 'head', head)
    assert api._reachable() is True
    assert api._reachable() is False  # not the answer from before
    assert api._reachable() is True
    assert calls == ['https://music.youtube.com/'] * 3
