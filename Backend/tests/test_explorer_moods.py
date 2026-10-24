"""Moods and genres for Search: shaped for the window, cached, and gentle
with what YouTube Music sends back."""

from __future__ import annotations

from dannify import explorer


def _two_row(title, browse_id=None, *, video_id=None, subtitle='Easy songs'):
    """One item of a mood page, as YouTube Music sends it."""

    run = {'text': title}
    if browse_id:
        run['navigationEndpoint'] = {'browseEndpoint': {'browseId': browse_id}}
    data = {
        'title': {'runs': [run]},
        'subtitle': {'runs': [{'text': subtitle}]},
        'thumbnailRenderer': {'musicThumbnailRenderer': {'thumbnail': {'thumbnails': [{'url': 'https://x/1.jpg'}]}}},
    }
    if video_id:
        data['navigationEndpoint'] = {'watchEndpoint': {'videoId': video_id}}
    return {'musicTwoRowItemRenderer': data}


def _page(*sections):
    return {'contents': {'singleColumnBrowseResultsRenderer': {'tabs': [{'tabRenderer': {'content': {
        'sectionListRenderer': {'contents': list(sections)},
    }}}]}}}


def _carousel(*items):
    return {'musicCarouselShelfRenderer': {'contents': list(items)}}


class _Fake:
    calls = 0
    page = None

    def get_mood_categories(self):
        type(self).calls += 1
        return {
            'Moods & moments': [{'title': 'Chill', 'params': 'p1'}, {'title': '', 'params': 'x'}],
            'Genres': [{'title': 'African', 'params': 'p2'}, 'not a card'],
            'Empty': [],
        }

    def _send_request(self, endpoint, body):
        type(self).calls += 1
        assert endpoint == 'browse' and body['browseId'] == 'FEmusic_moods_and_genres_category'
        return type(self).page or _page(_carousel(_two_row('Hits Café', 'VLRDCLAK1')))


def test_moods_and_their_playlists(monkeypatch):
    fake = _Fake()
    _Fake.page = None
    monkeypatch.setattr(explorer, '_ytm', lambda: fake)
    explorer.clear_cache()
    sections = explorer.moods()
    assert [s['title'] for s in sections] == ['Moods & moments', 'Genres']
    assert sections[0]['items'] == [{'title': 'Chill', 'params': 'p1'}]
    cards = explorer.mood_playlists('p1')
    assert cards == [{
        'type': 'playlist', 'browse_id': 'RDCLAK1', 'name': 'Hits Café',
        'cover_url': cards[0]['cover_url'], 'description': 'Easy songs',
    }]
    assert cards[0]['cover_url']
    # Asked again: from the cache.
    before = _Fake.calls
    explorer.moods()
    explorer.mood_playlists('p1')
    assert _Fake.calls == before
    explorer.clear_cache()


def test_a_genre_page_with_songs_videos_and_albums_still_opens(monkeypatch):
    # The shape of a genre page since YouTube Music put songs, music videos
    # and albums beside the playlists: the first song used to stop the whole
    # page, and "Family", "Pop" and 21 more would not open.
    _Fake.page = _page(
        _carousel(
            _two_row('Runaway', video_id='abc123'),  # a song: no browse id
            _two_row('Afrobeats Hits', 'VLRDCLAK5uy_afro'),
        ),
        {'musicImmersiveCarouselShelfRenderer': {'contents': [_two_row('Golden', 'MPREb_album1')]}},  # an album
        {'gridRenderer': {'items': [
            _two_row('Family Singalong', 'VLPLfamily'),
            _two_row('An episode', 'MPEDepisode'),
            {'musicResponsiveListItemRenderer': {}},  # a row of a song list
        ]}},
        {'musicDescriptionShelfRenderer': {}},
    )
    monkeypatch.setattr(explorer, '_ytm', lambda: _Fake())
    explorer.clear_cache()
    cards = explorer.mood_playlists('p2')
    assert [(c['name'], c['browse_id']) for c in cards] == [
        ('Afrobeats Hits', 'RDCLAK5uy_afro'),
        ('Family Singalong', 'PLfamily'),
    ]
    _Fake.page = None
    explorer.clear_cache()


def test_a_page_without_any_sections_is_empty_not_an_error(monkeypatch):
    _Fake.page = {'contents': {}}
    monkeypatch.setattr(explorer, '_ytm', lambda: _Fake())
    explorer.clear_cache()
    assert explorer.mood_playlists('p3') == []
    _Fake.page = None
    explorer.clear_cache()
