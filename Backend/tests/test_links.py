"""A pasted Spotify link: its page in one shape for every kind, and its songs
paired with the same songs on YouTube Music."""

from __future__ import annotations

import asyncio

import pytest

from dannify import explorer, links, providers, spotify
from dannify.routes import explore


def _payload(entity):
    return {'props': {'pageProps': {'state': {'data': {'entity': entity}, 'settings': {}}}}}


def _row(title, who, ms=200_000, tid='t1'):
    return {'uri': f'spotify:track:{tid}', 'title': title, 'subtitle': who, 'duration': ms}


ENTITIES = {
    ('artist', 'a1'): {
        'type': 'artist', 'name': 'Burna Boy', 'subtitle': 'Top tracks',
        'visualIdentity': {'image': [{'url': 'https://i/small', 'maxWidth': 160}, {'url': 'https://i/big', 'width': 640}]},
        'trackList': [_row('Last Last', 'Burna Boy', 172_342, 'x1'), _row('Dai Dai', 'Shakira, Burna Boy', 223_448, 'x2')],
    },
    ('playlist', 'p1'): {
        'type': 'playlist', 'name': 'Today’s Top Hits', 'subtitle': 'Spotify',
        'coverArt': {'sources': [{'url': 'https://i/cover'}]},
        'trackList': [_row('Housewife', 'Tate McRae', 208_810, 'y1')],
    },
    # A show's embed is its newest episode, the show's name under it.
    ('show', 's1'): {'type': 'episode', 'name': '#2570 - Mystery Boys', 'subtitle': 'The Joe Rogan Experience'},
    ('episode', 'e1'): {'type': 'episode', 'name': '#2570 - Mystery Boys', 'subtitle': 'The Joe Rogan Experience'},
}


class _YouTube:
    def __init__(self, rows):
        self.rows = rows

    def search(self, query, filter=None, limit=10):
        return self.rows.get(filter, [])


JRE = {
    'podcasts': [
        {'title': 'JRE Clips', 'browseId': 'MPSPclips'},
        {'title': 'The Joe Rogan Experience', 'browseId': 'MPSPPLjre'},
    ],
    'episodes': [
        {'title': 'Reacting to #2570', 'videoId': 'aaaaaaaaaaa', 'podcast': {'name': 'Cortado Joe'}},
        {
            'title': 'Joe Rogan Experience #2570 - Mystery Boys', 'videoId': 'rn6iW7XDEHc',
            'podcast': {'name': 'The Joe Rogan Experience'}, 'duration': '2 hr 43 min',
        },
    ],
}


@pytest.fixture
def embeds(monkeypatch):
    monkeypatch.setattr(spotify, '_fetch_embed_json', lambda kind, sid: _payload(ENTITIES[(kind, sid)]))


def test_an_artist_link_is_their_top_songs(embeds):
    page = spotify.link_page('https://open.spotify.com/intl-fr/artist/a1?si=xyz')
    assert page['kind'] == 'artist' and page['title'] == 'Burna Boy'
    assert page['subtitle'] == '', '"Top tracks" is not who they are by'
    assert page['cover'] == 'https://i/big'
    assert [t['name'] for t in page['tracks']] == ['Last Last', 'Dai Dai']
    assert page['tracks'][1]['artists'] == ['Shakira', 'Burna Boy']
    assert page['total'] == 2 and page['duration'] == 172 + 223
    assert page['url'] == 'https://open.spotify.com/artist/a1'


def test_a_playlist_link_says_whose_it_is(embeds):
    page = spotify.link_page('spotify:playlist:p1')
    assert (page['kind'], page['title'], page['subtitle']) == ('playlist', 'Today’s Top Hits', 'Spotify')
    assert page['cover'] == 'https://i/cover' and page['total'] == 1


def test_a_podcast_opens_as_the_same_one_on_youtube_music(embeds, monkeypatch):
    monkeypatch.setattr(explorer, '_ytm', lambda: _YouTube(JRE))
    show = spotify.link_page('https://open.spotify.com/show/s1')
    assert show['title'] == 'The Joe Rogan Experience'
    assert show['open'] == {'kind': 'podcast', 'id': 'MPSPPLjre'}
    episode = spotify.link_page('https://open.spotify.com/episode/e1')['open']
    assert episode['kind'] == 'episode' and episode['song']['video_id'] == 'rn6iW7XDEHc'
    assert episode['song']['duration'] == 2 * 3600 + 43 * 60
    # Not on YouTube Music: said so, not opened as something else.
    monkeypatch.setattr(explorer, '_ytm', lambda: _YouTube({}))
    with pytest.raises(spotify.Unsupported):
        spotify.link_page('https://open.spotify.com/show/s1')
    with pytest.raises(ValueError):
        spotify.link_page('https://example.com/playlist/abc')


def test_a_podcast_page_is_its_episodes(monkeypatch):
    class Podcasts:
        def get_playlist(self, pid, limit=200):
            raise KeyError('contents')

        def get_podcast(self, bid, limit=100):
            assert bid == 'MPSPPLjre'
            return {
                'title': 'The Joe Rogan Experience', 'author': {'name': 'PowerfulJRE'},
                'episodes': [{'title': '#2570', 'videoId': 'rn6iW7XDEHc', 'duration': '1 hr 5 min'}, {'title': 'no video'}],
            }

    monkeypatch.setattr(explorer, '_ytm', lambda: Podcasts())
    monkeypatch.setattr(explorer, '_cache_get', lambda key, refresh=None: None)
    monkeypatch.setattr(explorer, '_cache_put', lambda key, value: None)
    # A youtube.com link has the episodes' playlist alone.
    for bid in ('MPSPPLjre', 'PLjre'):
        page = explorer.playlist(bid)
        assert page['podcast'] and page['name'] == 'The Joe Rogan Experience'
        assert [(t['video_id'], t['artists'], t['duration']) for t in page['tracks']] == [
            ('rn6iW7XDEHc', ['The Joe Rogan Experience'], 3900)
        ]


@pytest.mark.parametrize('said, seconds', [('2 hr 43 min', 9780), ('45 min', 2700), ('1:02:03', 3723), ('', 0), (None, 0)])
def test_an_episode_length_as_it_is_said(said, seconds):
    assert explorer._spoken_seconds(said) == seconds


def test_the_route_says_what_went_wrong(embeds, monkeypatch):
    monkeypatch.setattr(explorer, '_ytm', lambda: _YouTube({}))
    with pytest.raises(explore.HTTPException) as exc:
        asyncio.run(explore.spotify_link_endpoint('https://example.com/x'))
    assert exc.value.status_code == 400
    with pytest.raises(explore.HTTPException) as exc:
        asyncio.run(explore.spotify_link_endpoint('https://open.spotify.com/episode/e1'))
    assert exc.value.status_code == 422
    assert asyncio.run(explore.spotify_link_endpoint('https://open.spotify.com/artist/a1'))['total'] == 2


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


@pytest.fixture
def youtube(monkeypatch):
    asked = []

    def find_match(track):
        asked.append(track['name'])
        if track['name'] == 'Nowhere':
            return None, None
        vid = ('v' + track['name'].replace(' ', ''))[:11].ljust(11, '0')
        return vid, {'videoId': vid, 'title': track['name'], 'artists': [{'name': a} for a in track['artists']]}

    monkeypatch.setattr(providers, 'find_match', find_match)
    links._cache.clear()
    yield asked
    links._cache.clear()


def test_each_song_gets_its_youtube_music_pair_in_order(youtube):
    out = links.match([
        {'song_id': 's1', 'name': 'Last Last', 'artists': ['Burna Boy'], 'duration': 172},
        {'song_id': 's2', 'name': 'Nowhere', 'artists': ['Nobody']},
        {'song_id': 's3', 'name': 'Dai Dai', 'artists': ['Shakira', 'Burna Boy']},
    ])
    assert [o and o['name'] for o in out] == ['Last Last', None, 'Dai Dai']
    assert out[0]['video_id'] == out[0]['song_id'] and out[0]['spotify_id'] == 's1'


def test_a_pair_found_is_not_searched_for_again_and_one_not_found_is(youtube):
    tracks = [{'song_id': 's1', 'name': 'Last Last', 'artists': ['Burna Boy']},
              {'song_id': 's2', 'name': 'Nowhere', 'artists': ['Nobody']}]
    links.match(tracks)
    links.match(tracks)
    assert youtube.count('Last Last') == 1
    assert youtube.count('Nowhere') == 2, 'offline, everything is "not found": that must not stick'


def test_a_few_at_a_time(youtube):
    many = [{'song_id': f's{n}', 'name': f'Song {n}', 'artists': ['A']} for n in range(60)]
    assert len(links.match(many)) == links.MATCH_BATCH


def test_the_route_takes_a_list_only(youtube):
    with pytest.raises(explore.HTTPException):
        asyncio.run(explore.link_match_endpoint({'tracks': 'Last Last'}))
    out = asyncio.run(explore.link_match_endpoint({'tracks': [{'song_id': 's1', 'name': 'Ye', 'artists': 'Burna Boy'}]}))
    assert out['matches'][0]['name'] == 'Ye'
